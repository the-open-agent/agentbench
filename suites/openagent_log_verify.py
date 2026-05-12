"""
Server-side log evidence for OpenAgent (aligned with HTTP round timestamps).

Notes:
- Beego access logs in logs/openagent.log often include lines like server.go with POST /api/chat/completions.
- Tool Call lines from model/mcp.go use fmt.Printf to stdout and may not appear in openagent.log;
  redirect the exe console to a file and pass --openagent-console-log / OPENAGENT_CONSOLE_LOG for stronger evidence.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

BELOG_TS_RE = re.compile(r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3})")
POST_CHAT_COMPLETIONS_RE = re.compile(r"POST\s+.*/api/chat/completions\b", re.IGNORECASE)
TOOL_CALL_PRINTF_RE = re.compile(r"Tool\s+Call:\s*\[([^\]]*)\]")


def _ts_to_epoch_ms(ts: str) -> Optional[int]:
    try:
        dt = datetime.strptime(ts, "%Y/%m/%d %H:%M:%S.%f")
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def read_tail_lines(path: Path, max_bytes: int = 12_000_000) -> List[str]:
    if not path.exists():
        return []
    try:
        size = path.stat().st_size
    except OSError:
        return []
    try:
        with path.open("rb") as f:
            if size > max_bytes:
                f.seek(-max_bytes, 2)
                f.readline()
            raw = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    return raw.splitlines()


def _line_time_ms(line: str) -> Optional[int]:
    m = BELOG_TS_RE.match(line.strip())
    if not m:
        return None
    return _ts_to_epoch_ms(m.group(1))


def _tool_family_match(observed: str, required: str) -> bool:
    observed = (observed or "").strip()
    required = (required or "").strip()
    if observed == required:
        return True
    if required.startswith("browser_use") and (
        observed == "browser_use" or observed.startswith("browser_use")
    ):
        return True
    if required.startswith("local_") and observed.startswith("local_"):
        return True
    return False


def _required_satisfied(required: List[str], observed_names: Set[str]) -> Tuple[bool, List[str]]:
    missing: List[str] = []
    for req in required:
        ok_one = False
        for obs in observed_names:
            if _tool_family_match(obs, req):
                ok_one = True
                break
        if not ok_one:
            missing.append(req)
    return len(missing) == 0, missing


def log_tail_time_range_ms(lines: List[str]) -> Tuple[Optional[int], Optional[int]]:
    ts_list: List[int] = []
    for ln in lines:
        t = _line_time_ms(ln)
        if t is not None:
            ts_list.append(t)
    if not ts_list:
        return None, None
    return min(ts_list), max(ts_list)


def verify_openagent_logs(
    start_ms: int,
    end_ms: int,
    task: Dict[str, Any],
    access_log_path: Path,
    console_log_paths: List[Path],
    pad_before_ms: int = 15000,
    pad_after_ms: int = 5000,
) -> Dict[str, Any]:
    required = task.get("required_tools") or []
    if not isinstance(required, list):
        required = []

    win_lo = start_ms - pad_before_ms
    win_hi = end_ms + pad_after_ms

    paths_checked: List[str] = []
    chat_hits: List[str] = []
    tool_calls_window: Set[str] = set()
    tool_calls_console: Set[str] = set()

    def scan_lines(lines: List[str], source_tag: str) -> None:
        nonlocal chat_hits
        for ln in lines:
            t_ms = _line_time_ms(ln)
            in_win = t_ms is not None and win_lo <= t_ms <= win_hi

            if in_win and POST_CHAT_COMPLETIONS_RE.search(ln):
                chat_hits.append(ln[:500])

            if in_win:
                for m in TOOL_CALL_PRINTF_RE.finditer(ln):
                    name = (m.group(1) or "").strip()
                    if name and name.lower() != "none":
                        tool_calls_window.add(name)

            # Console logs may lack Beego timestamps; scan whole line when source is console (limit file to one session).
            if t_ms is None and source_tag.startswith("console:"):
                for m in TOOL_CALL_PRINTF_RE.finditer(ln):
                    name = (m.group(1) or "").strip()
                    if name and name.lower() != "none":
                        tool_calls_console.add(name)

    access_lines = read_tail_lines(access_log_path)
    paths_checked.append(str(access_log_path))
    tail_min_ms, tail_max_ms = log_tail_time_range_ms(access_lines)
    scan_lines(access_lines, "access")

    for cp in console_log_paths:
        if not cp:
            continue
        paths_checked.append(str(cp))
        scan_lines(read_tail_lines(cp), f"console:{cp}")

    observed_union = set(tool_calls_window) | set(tool_calls_console)
    req_ok, missing = _required_satisfied(required, observed_union)

    chat_seen = len(chat_hits) > 0

    notes: List[str] = []
    if tail_max_ms is not None and tail_max_ms < win_lo:
        notes.append(
            f"Access log tail max timestamp is before this round's padded window "
            f"(log max_ts≈{tail_max_ms} < window_lo≈{win_lo}): "
            f"check that --openagent-log points at the live log, not a rotated copy or another binary."
        )
    if not chat_seen:
        notes.append(
            "No POST /api/chat/completions match in Beego access log within the window "
            "(wrong log path, rotation, or clock skew)."
        )
    if not tool_calls_window and not tool_calls_console:
        notes.append(
            "No Tool Call: [...] lines detected; openagent.log often omits them (fmt.Printf goes to stdout). "
            "Redirect console to a file and set --openagent-console-log to strengthen verification."
        )

    # Log-side tool completeness: if Tool Call lines exist, check required_tools; else verdict unknown.
    tools_verdict: str
    if observed_union:
        tools_verdict = "complete" if req_ok else "incomplete"
    else:
        tools_verdict = "unknown"

    return {
        "window_ms": {
            "request_start": start_ms,
            "request_end": end_ms,
            "padded_lo": win_lo,
            "padded_hi": win_hi,
            "pad_before_ms": pad_before_ms,
            "pad_after_ms": pad_after_ms,
        },
        "log_paths_checked": paths_checked,
        "access_log_tail_time_range_ms": {
            "min": tail_min_ms,
            "max": tail_max_ms,
            "line_count_scanned": len(access_lines),
        },
        "chat_completions_post_seen": chat_seen,
        "chat_completions_post_sample_lines": chat_hits[:5],
        "tool_calls_in_window": sorted(tool_calls_window),
        "tool_calls_console_untimed": sorted(tool_calls_console),
        "tool_calls_observed_union": sorted(observed_union),
        "required_tools": required,
        "required_tools_satisfied_by_tool_log": req_ok,
        "missing_tools_in_tool_log": missing,
        "tools_log_verdict": tools_verdict,
        "notes": notes,
    }


def default_console_log_candidates(cli_path: str) -> List[Path]:
    paths: List[Path] = []
    if cli_path.strip():
        paths.append(Path(cli_path))
    envp = os.environ.get("OPENAGENT_CONSOLE_LOG", "").strip()
    if envp:
        paths.append(Path(envp))
    env_fallback = os.environ.get("AGENTBENCH_CONSOLE_LOG_FALLBACK", "").strip()
    if env_fallback:
        pfb = Path(env_fallback)
        if pfb.exists():
            paths.append(pfb)
    # Optional local redirect next to cwd (no machine-specific defaults)
    for rel in ("logs/openagent_console.log", "openagent_console.log"):
        cand = Path(rel)
        if cand.exists():
            paths.append(cand)
            break
    # Dedupe while preserving order
    seen = set()
    out: List[Path] = []
    for p in paths:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out
