from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .models import RunRecord
from .stats import bootstrap_ci, mean, std
from .utils import write_json, write_jsonl


def record_to_row(r: RunRecord) -> dict[str, Any]:
    return {
        "suite": r.suite,
        "task_id": r.task_id,
        "category": r.category,
        "round": r.round_index,
        "attempt": r.attempt,
        "ok": r.ok,
        "latency_ms": r.latency_ms,
        "total_tokens": r.total_tokens,
        "prompt_tokens": r.prompt_tokens,
        "completion_tokens": r.completion_tokens,
        "response_status": r.response_status,
        "api_error": r.api_error,
        "parse_error": r.parse_error,
        "validation_errors": r.validation_errors,
        "response_text": r.response_text,
        "evidence": r.evidence,
        "extra": r.extra,
    }


def summarize_records(records: list[RunRecord]) -> dict[str, Any]:
    by_suite: dict[str, list[RunRecord]] = {}
    for rec in records:
        by_suite.setdefault(rec.suite, []).append(rec)

    suite_summary: dict[str, Any] = {}
    for suite, rows in by_suite.items():
        success = [1.0 if r.ok else 0.0 for r in rows]
        lat = [float(r.latency_ms) for r in rows]
        tok = [float(r.total_tokens or 0) for r in rows if r.total_tokens is not None]
        failures = Counter()
        for r in rows:
            for err in r.validation_errors:
                failures[err] += 1
            if r.api_error:
                failures["api_error"] += 1
            if r.parse_error:
                failures["parse_error"] += 1
        ci_lo, ci_hi = bootstrap_ci(success) if success else (0.0, 0.0)
        suite_summary[suite] = {
            "rounds": len(rows),
            "success_rate": round(mean(success), 4),
            "success_rate_ci95": [round(ci_lo, 4), round(ci_hi, 4)],
            "latency_ms_mean": round(mean(lat), 2),
            "latency_ms_std": round(std(lat), 2),
            "worst_latency_ms": int(max(lat) if lat else 0),
            "tokens_mean": round(mean(tok), 2) if tok else 0.0,
            "tokens_std": round(std(tok), 2) if tok else 0.0,
            "failures_top": failures.most_common(10),
        }
    return {"suites": suite_summary, "total_records": len(records)}


def write_artifacts(
    session_dir: Path,
    records: list[RunRecord],
    summary: dict[str, Any],
    *,
    session_id: str,
    base_url: str,
) -> None:
    rows = [record_to_row(r) for r in records]
    write_jsonl(session_dir / "details.jsonl", rows)
    write_json(session_dir / "summary.json", summary)

    by_suite: dict[str, list[RunRecord]] = {}
    for r in records:
        by_suite.setdefault(r.suite, []).append(r)

    for suite_name, suite_records in by_suite.items():
        suite_dir = session_dir / suite_name
        suite_dir.mkdir(parents=True, exist_ok=True)
        suite_rows = [record_to_row(r) for r in suite_records]
        sub_summary = summarize_records(suite_records)
        write_jsonl(suite_dir / "details.jsonl", suite_rows)
        write_json(suite_dir / "summary.json", sub_summary)
        suite_report = build_markdown_report(
            session_id,
            sub_summary,
            base_url,
            report_title_suffix=suite_name,
        )
        (suite_dir / "report.md").write_text(suite_report, encoding="utf-8")


def build_markdown_report(
    session_id: str,
    summary: dict[str, Any],
    base_url: str,
    *,
    report_title_suffix: str | None = None,
    suite_subdirs: list[str] | None = None,
) -> str:
    lines: list[str] = []
    title = "# AgentBench session report"
    if report_title_suffix:
        title = f"# AgentBench suite report — `{report_title_suffix}`"
    lines.append(title)
    lines.append("")
    lines.append(f"- Session: `{session_id}`")
    lines.append(f"- OpenAgent Endpoint: `{base_url}`")
    lines.append("")
    if suite_subdirs:
        lines.append("## Per-suite outputs")
        lines.append("")
        lines.append(
            "Each suite writes its own subdirectory with `details.jsonl`, `summary.json`, and `report.md`."
        )
        lines.append("")
        for name in sorted(suite_subdirs):
            lines.append(f"- `{name}/`")
        lines.append("")
    lines.append("## Overview")
    lines.append("")
    for suite, data in (summary.get("suites") or {}).items():
        lines.append(f"### {suite}")
        if suite == "baseperf":
            lines.append("- Goal: baseline performance and availability (latency, tokens, stability)")
        elif suite == "dialogue":
            lines.append("- Goal: dialogue quality (format checks, factual match, instruction following)")
        elif suite == "hardchat":
            lines.append("- Goal: multi-stage structured output (collect / normalize / summarize)")
        elif suite == "memory":
            lines.append("- Goal: memory and context handling (short/medium/long context stability)")
        elif suite == "reliability":
            lines.append("- Goal: reliability and consistency (repeatable correct answers, format stability)")
        elif suite == "startup":
            lines.append("- Goal: health-check latency baseline (first check vs warm path, already-running service)")
        elif suite == "throughput":
            lines.append("- Goal: throughput under concurrency (requests per second, latency degradation)")
        elif suite == "tool":
            lines.append("- Goal: tool-use evidence and output shape checks (required_tools)")
        lines.append(f"- Rounds: `{data['rounds']}`")
        lines.append(f"- Success rate: `{data['success_rate']}` (95% CI: {data['success_rate_ci95']})")
        lines.append(
            f"- Latency (ms) mean: `{data['latency_ms_mean']}`, std: `{data['latency_ms_std']}`, worst: `{data['worst_latency_ms']}`"
        )
        lines.append(f"- Tokens mean: `{data['tokens_mean']}`, std: `{data['tokens_std']}`")
        lines.append(f"- Top failure reasons: `{data['failures_top']}`")
        lines.append("")
    return "\n".join(lines) + "\n"
