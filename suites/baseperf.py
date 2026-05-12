from __future__ import annotations

from pathlib import Path
from typing import Any

from ..benchcore.models import RunRecord
from .base import SuiteBase
from .easychat_common import load_baseperf_dataset, run_chat_once


class BasePerfSuite(SuiteBase):
    name = "baseperf"

    def __init__(self, root: Path) -> None:
        self.root = root

    def load_tasks(self) -> list[dict[str, Any]]:
        return load_baseperf_dataset(self.root)

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
        result = run_chat_once(
            base_url=base_url,
            provider_key=provider_key,
            model=model,
            prompt=task["prompt"],
            timeout_s=timeout_s,
        )
        # Base performance suite focuses on availability/latency/token collection.
        validation_errors: list[str] = []
        if not result["assistant_text"].strip():
            validation_errors.append("empty_response")
        ok = bool(result["ok_http_parse"]) and len(validation_errors) == 0
        return RunRecord(
            suite=self.name,
            task_id=task["id"],
            category=task.get("category", "baseperf"),
            round_index=round_index,
            attempt=attempt,
            ok=ok,
            latency_ms=int(result["latency_ms"]),
            total_tokens=result["usage"].get("total_tokens"),
            prompt_tokens=result["usage"].get("prompt_tokens"),
            completion_tokens=result["usage"].get("completion_tokens"),
            response_text=result["assistant_text"],
            response_status=int(result["status"]),
            api_error=result["api_error"],
            parse_error=result["parse_error"],
            validation_errors=validation_errors,
            evidence={},
            extra={"perf_mode": True},
        )
