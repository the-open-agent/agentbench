from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..benchcore.http_client import chat_completion
from ..benchcore.models import RunRecord
from ..benchcore.utils import now_ms
from .base import SuiteBase


class MemorySuite(SuiteBase):
    name = "memory"

    def __init__(self, root: Path) -> None:
        self.root = root

    def load_tasks(self) -> list[dict[str, Any]]:
        dataset_path = self.root / "datasets" / "memory" / "dataset.jsonl"
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
        repeat_count = task.get("repeat_count", 1)
        latencies: list[int] = []
        tokens_list: list[int] = []
        all_texts: list[str] = []
        errors: list[str] = []
        ok_count = 0

        for i in range(repeat_count):
            res = chat_completion(base_url, model, task["prompt"], provider_key, timeout_s)
            latencies.append(res["latency_ms"])
            tokens_list.append(res["usage"].get("total_tokens") or 0)
            all_texts.append(res["assistant_text"])
            if res["ok"]:
                ok_count += 1
            if res["error"]:
                errors.append(f"repeat_{i}_api_error:{res['error']}")
            if res["parse_error"]:
                errors.append(f"repeat_{i}_parse_error:{res['parse_error']}")

        validation_errors: list[str] = []
        if ok_count < repeat_count:
            validation_errors.append(f"partial_failure:{ok_count}/{repeat_count}")

        expected_keywords = task.get("expected_keywords", [])
        if expected_keywords and all_texts:
            for kw in expected_keywords:
                if not any(kw.lower() in t.lower() for t in all_texts if t):
                    validation_errors.append(f"missing_keyword:{kw}")

        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        avg_tokens = sum(tokens_list) / len(tokens_list) if tokens_list else 0

        return RunRecord(
            suite=self.name,
            task_id=task["id"],
            category=task.get("category", "memory"),
            round_index=round_index,
            attempt=attempt,
            ok=(ok_count == repeat_count and len(validation_errors) == 0),
            latency_ms=int(avg_latency),
            total_tokens=int(avg_tokens) if avg_tokens else None,
            prompt_tokens=None,
            completion_tokens=None,
            response_text=all_texts[0] if all_texts else "",
            response_status=200 if (ok_count == repeat_count and len(validation_errors) == 0) else 500,
            api_error=";".join(errors) if errors else None,
            parse_error=None,
            validation_errors=validation_errors,
            evidence={
                "latencies_ms": latencies,
                "tokens_per_run": tokens_list,
                "context_tokens_approx": task.get("context_tokens_approx"),
                "repeat_count": repeat_count,
                "prompt_length_chars": len(task["prompt"]),
            },
            extra={
                "memory_mode": True,
                "all_responses": all_texts,
            },
        )
