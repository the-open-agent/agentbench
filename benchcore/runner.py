from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from .http_client import health_check
from .models import RunRecord
from .reporting import build_markdown_report, summarize_records, write_artifacts
from .utils import write_json


def run_benchmark(
    root: Path,
    suites: list[Any],
    base_url: str,
    provider_key: str,
    model: str,
    rounds: int,
    max_attempts: int,
    timeout_s: int,
) -> Path:
    health = health_check(base_url, timeout_s=5)
    if not health.ok:
        raise RuntimeError(f"OpenAgent health check failed: {health.error or health.text}")

    session_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    session_dir = root / "results" / f"session-{session_id}"
    session_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        session_dir / "meta.json",
        {
            "session_id": session_id,
            "base_url": base_url,
            "model": model,
            "rounds": rounds,
            "max_attempts": max_attempts,
            "timeout_s": timeout_s,
            "suites": [s.name for s in suites],
            "health": {"ok": health.ok, "status": health.status, "latency_ms": health.latency_ms},
        },
    )

    records: list[RunRecord] = []
    for suite in suites:
        tasks = suite.load_tasks()
        for task in tasks:
            for round_idx in range(1, rounds + 1):
                best: RunRecord | None = None
                for attempt in range(1, max_attempts + 1):
                    rec = suite.run_task(
                        task=task,
                        round_index=round_idx,
                        attempt=attempt,
                        base_url=base_url,
                        model=model,
                        provider_key=provider_key,
                        timeout_s=timeout_s,
                    )
                    if rec.ok:
                        best = rec
                        break
                    if best is None:
                        best = rec
                if best is not None:
                    records.append(best)
                    print(
                        f"[{suite.name}] {best.task_id} round {round_idx}/{rounds} "
                        f"ok={best.ok} latency_ms={best.latency_ms} attempt={best.attempt}"
                    )

    summary = summarize_records(records)
    write_artifacts(
        session_dir,
        records,
        summary,
        session_id=session_id,
        base_url=base_url,
    )
    suite_names = sorted((summary.get("suites") or {}).keys())
    report = build_markdown_report(
        session_id,
        summary,
        base_url,
        suite_subdirs=suite_names,
    )
    (session_dir / "report.md").write_text(report, encoding="utf-8")
    return session_dir
