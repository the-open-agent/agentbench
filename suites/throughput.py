from __future__ import annotations

import concurrent.futures
import json
import traceback
from pathlib import Path
from typing import Any

from ..benchcore.http_client import chat_completion
from ..benchcore.models import RunRecord
from ..benchcore.utils import now_ms
from .base import SuiteBase


class ThroughputSuite(SuiteBase):
    name = "throughput"

    def __init__(self, root: Path) -> None:
        self.root = root

    def load_tasks(self) -> list[dict[str, Any]]:
        dataset_path = self.root / "datasets" / "throughput" / "dataset.jsonl"
        tasks: list[dict[str, Any]] = []
        if dataset_path.exists():
            with open(dataset_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        tasks.append(json.loads(line))
        return tasks

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
        concurrency = int(task.get("concurrency", 1))
        requests_per_concurrency = int(task.get("requests_per_concurrency", 1))
        total_requests = concurrency * requests_per_concurrency
        prompt = task["prompt"]

        overall_t0 = now_ms()
        results: list[dict[str, Any]] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(
                    chat_completion, base_url, model, prompt, provider_key, timeout_s
                )
                for _ in range(total_requests)
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    error_detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
                    results.append({
                        "latency_ms": 0,
                        "ok": False,
                        "status": 0,
                        "error": error_detail,
                        "parse_error": None,
                        "assistant_text": "",
                        "usage": {},
                    })
        overall_t1 = now_ms()

        ok_count = sum(1 for r in results if r["ok"])
        latencies = [r["latency_ms"] for r in results if r["ok"]]
        tokens = [r["usage"].get("total_tokens", 0) for r in results if r["ok"] and r["usage"]]

        total_time_ms = overall_t1 - overall_t0
        throughput_rps = (ok_count / (total_time_ms / 1000.0)) if total_time_ms > 0 else 0.0

        validation_errors: list[str] = []
        if ok_count < total_requests:
            validation_errors.append(f"partial_failure:{ok_count}/{total_requests}")

        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        max_latency = max(latencies) if latencies else 0
        min_latency = min(latencies) if latencies else 0
        avg_tokens = sum(tokens) / len(tokens) if tokens else 0

        return RunRecord(
            suite=self.name,
            task_id=task["id"],
            category=task.get("category", "throughput"),
            round_index=round_index,
            attempt=attempt,
            ok=(ok_count == total_requests),
            latency_ms=int(avg_latency),
            total_tokens=int(avg_tokens) if avg_tokens else None,
            prompt_tokens=None,
            completion_tokens=None,
            response_text=results[0]["assistant_text"] if results else "",
            response_status=200 if ok_count == total_requests else 500,
            api_error=None,
            parse_error=None,
            validation_errors=validation_errors,
            evidence={
                "concurrency": concurrency,
                "total_requests": total_requests,
                "successful_requests": ok_count,
                "total_time_ms": total_time_ms,
                "throughput_rps": round(throughput_rps, 2),
                "avg_latency_ms": round(avg_latency, 2),
                "min_latency_ms": min_latency,
                "max_latency_ms": max_latency,
                "latencies_ms": [r["latency_ms"] for r in results],
            },
            extra={
                "throughput_mode": True,
                "all_results": results,
            },
        )
