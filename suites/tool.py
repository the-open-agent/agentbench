from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from ..benchcore.http_client import post_json
from ..benchcore.models import RunRecord
from ..benchcore.utils import now_ms, read_json, try_parse_json
from .base import SuiteBase


def _resolve_tool_assets_root(root: Path) -> Path:
    canonical = root / "datasets" / "tool"
    if (canonical / "dataset.jsonl").is_file() or (canonical / "tasks_index.json").is_file():
        return canonical
    for name in ("benchmark-tool", "openagenttool"):
        p = root / name
        ds = p / "datasets"
        if (ds / "dataset.jsonl").is_file() or (ds / "tasks_index.json").is_file():
            return p
    return canonical


def _canonical_tool_name(raw: str) -> str:
    """Normalize tool labels from JSON (OpenAI-style function.name, dotted ids, etc.)."""
    s = (raw or "").strip()
    if not s:
        return ""
    if "." in s:
        s = s.rsplit(".", 1)[-1]
    return s.replace("-", "_").lower()


def _names_from_tool_call_entry(entry: Any) -> list[str]:
    if not isinstance(entry, dict):
        return []
    out: list[str] = []
    for key in ("name", "tool"):
        v = entry.get(key)
        if isinstance(v, str) and v.strip():
            out.append(_canonical_tool_name(v))
    fn = entry.get("function")
    if isinstance(fn, dict) and isinstance(fn.get("name"), str) and fn["name"].strip():
        out.append(_canonical_tool_name(fn["name"]))
    return [n for n in out if n]


def _collect_declared_tool_names(output_json: dict[str, Any]) -> set[str]:
    """Gather tool names from evidence.tool_calls and optional top-level tool_calls."""
    raw: list[Any] = []
    ev = output_json.get("evidence")
    if isinstance(ev, dict):
        tc = ev.get("tool_calls")
        if isinstance(tc, list):
            raw.extend(tc)
    tc2 = output_json.get("tool_calls")
    if isinstance(tc2, list):
        raw.extend(tc2)
    names: set[str] = set()
    for item in raw:
        for n in _names_from_tool_call_entry(item):
            names.add(n)
    return names


def _tool_requirement_met(required: str, declared: set[str]) -> bool:
    req = _canonical_tool_name(required)
    return bool(req) and req in declared


class ToolSuite(SuiteBase):
    name = "tool"

    def __init__(self, root: Path) -> None:
        self.root = root
        self._tool_root = _resolve_tool_assets_root(root)
        self._log_verify_fn = self._load_log_verify()

    def _load_log_verify(self):
        module_path = Path(__file__).resolve().parent / "openagent_log_verify.py"
        if not module_path.exists():
            return None
        spec = importlib.util.spec_from_file_location("legacy_log_verify", module_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, "verify_openagent_logs", None)

    def load_tasks(self) -> list[dict[str, Any]]:
        jsonl_path = self._tool_root / "dataset.jsonl"
        if jsonl_path.is_file():
            tasks: list[dict[str, Any]] = []
            for line in jsonl_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    tasks.append(json.loads(line))
            return tasks
        index_path = self._tool_root / "tasks_index.json"
        base = self._tool_root / "tasks"
        index = read_json(index_path)
        merged: list[dict[str, Any]] = []
        for item in index.get("tasks", []):
            merged.append(read_json(base / f"{item['id']}.json"))
        return merged

    def _validate(self, task: dict[str, Any], output_json: Any) -> list[str]:
        req = task.get("output_requirements", {})
        errors: list[str] = []
        if not isinstance(output_json, dict):
            return ["output_not_json_object"]
        for field in req.get("must_include_fields", []):
            cur = output_json
            ok = True
            for part in field.split("."):
                if not isinstance(cur, dict) or part not in cur:
                    ok = False
                    break
                cur = cur[part]
            if not ok:
                errors.append(f"missing_field:{field}")
        required_tools = req.get("must_include_tool_calls", [])
        declared = _collect_declared_tool_names(output_json)
        for name in required_tools:
            if not _tool_requirement_met(str(name), declared):
                errors.append(f"missing_tool_call:{name}")
        min_sources = req.get("min_sources")
        if isinstance(min_sources, int):
            sources = ((output_json.get("evidence") or {}).get("sources")) or []
            if not isinstance(sources, list) or len(sources) < min_sources:
                errors.append(f"min_sources_not_met:{min_sources}")
        return errors

    def run_task(
        self,
        task: dict[str, Any],
        round_index: int,
        attempt: int,
        base_url: str,
        model: str,
        provider_key: str,
        timeout_s: int,
    ) -> RunRecord:
        url = base_url.rstrip("/") + "/api/chat/completions"
        payload = {
            "model": model,
            "stream": False,
            "messages": [{"role": "user", "content": task["prompt"]}],
        }
        t0 = now_ms()
        result = post_json(url, payload, {"Authorization": f"Bearer {provider_key}"}, timeout_s)
        t1 = now_ms()
        parsed, parse_error = try_parse_json(result.text)
        usage = {}
        assistant_text = ""
        output_json = None
        output_parse_error = None
        if isinstance(parsed, dict):
            usage = parsed.get("usage") or {}
            try:
                assistant_text = parsed["choices"][0]["message"]["content"] or ""
            except Exception:  # noqa: BLE001
                assistant_text = ""
        if assistant_text:
            output_json, output_parse_error = try_parse_json(assistant_text)
        else:
            output_parse_error = "assistant_text_missing"
        validation_errors = self._validate(task, output_json) if output_json is not None else [f"output_parse:{output_parse_error}"]
        evidence: dict[str, Any] = {}
        if self._log_verify_fn is not None:
            try:
                verify = self._log_verify_fn(
                    t0,
                    t1,
                    task,
                    self.root / "openagent" / "logs" / "openagent.log",
                    [],
                )
                evidence["log_verification"] = verify
            except Exception:  # noqa: BLE001
                evidence["log_verification"] = {"error": "log_verify_failed"}
        ok = result.ok and parse_error is None and len(validation_errors) == 0
        return RunRecord(
            suite=self.name,
            task_id=task["id"],
            category=task.get("category", "tool"),
            round_index=round_index,
            attempt=attempt,
            ok=ok,
            latency_ms=t1 - t0,
            total_tokens=usage.get("total_tokens"),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            response_text=assistant_text,
            response_status=result.status,
            api_error=result.error,
            parse_error=parse_error,
            validation_errors=validation_errors,
            evidence=evidence,
            extra={"output_json": output_json},
        )
