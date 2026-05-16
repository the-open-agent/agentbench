from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..benchcore.http_client import health_check
from ..benchcore.models import RunRecord
from ..benchcore.utils import now_ms
from .base import SuiteBase


class StartupSuite(SuiteBase):
    name = "startup"

    def __init__(self, root: Path) -> None:
        self.root = root

    def load_tasks(self) -> list[dict[str, Any]]:
        dataset_path = self.root / "datasets" / "startup" / "dataset.jsonl"
        tasks: list[dict[str, Any]] = []
        if dataset_path.exists():
            with open(dataset_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        tasks.append(json.loads(line))
        return tasks

    def _measure_health_latency(self, base_url: str, timeout_s: int) -> dict[str, Any]:
        t0 = now_ms()
        health = health_check(base_url, timeout_s=timeout_s)
        t1 = now_ms()
        return {
            "latency_ms": t1 - t0,
            "ok": health.ok,
            "status": health.status,
            "error": health.error,
        }

    def _measure_warm_check(self, base_url: str, timeout_s: int) -> dict[str, Any]:
        health = health_check(base_url, timeout_s=timeout_s)
        if not health.ok:
            return {
                "latency_ms": health.latency_ms,
                "ok": False,
                "status": health.status,
                "error": health.error or "warm_pre_check_failed",
            }
        t0 = now_ms()
        health2 = health_check(base_url, timeout_s=timeout_s)
        t1 = now_ms()
        return {
            "latency_ms": t1 - t0,
            "ok": health2.ok,
            "status": health2.status,
            "error": health2.error,
        }

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
        mode = task.get("mode", "first")
        if mode == "first":
            result = self._measure_health_latency(base_url, timeout_s)
        elif mode == "warm":
            result = self._measure_warm_check(base_url, timeout_s)
        else:
            result = {
                "latency_ms": 0,
                "ok": False,
                "status": 0,
                "error": f"unknown_mode:{mode}",
            }

        validation_errors: list[str] = []
        if not result["ok"]:
            validation_errors.append(f"startup_failed:{result.get('error')}")

        return RunRecord(
            suite=self.name,
            task_id=task["id"],
            category=task.get("category", "startup"),
            round_index=round_index,
            attempt=attempt,
            ok=result["ok"],
            latency_ms=int(result["latency_ms"]),
            total_tokens=None,
            prompt_tokens=None,
            completion_tokens=None,
            response_text="",
            response_status=int(result["status"]),
            api_error=result.get("error"),
            parse_error=None,
            validation_errors=validation_errors,
            evidence={"mode": mode, "startup_latency_ms": result["latency_ms"]},
            extra={"startup_mode": mode},
        )
