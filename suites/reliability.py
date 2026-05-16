from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..benchcore.http_client import post_json
from ..benchcore.models import RunRecord
from ..benchcore.utils import now_ms
from .base import SuiteBase


class ReliabilitySuite(SuiteBase):
    name = "reliability"

    def __init__(self, root: Path) -> None:
        self.root = root

    def load_tasks(self) -> list[dict[str, Any]]:
        dataset_path = self.root / "datasets" / "reliability" / "dataset.jsonl"
        tasks: list[dict[str, Any]] = []
        if dataset_path.exists():
            with open(dataset_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        tasks.append(json.loads(line))
        return tasks

    def _run_once(
        self,
        task: dict[str, Any],
        base_url: str,
        model: str,
        provider_key: str,
        timeout_s: int,
    ) -> dict[str, Any]:
        url = base_url.rstrip("/") + "/api/chat/completions"
        payload = {
            "model": model,
            "stream": False,
            "messages": [{"role": "user", "content": task["prompt"]}],
        }
        t0 = now_ms()
        result = post_json(url, payload, {"Authorization": f"Bearer {provider_key}"}, timeout_s)
        t1 = now_ms()

        parsed = None
        parse_error = None
        assistant_text = ""
        usage = {}
        try:
            parsed = json.loads(result.text)
            usage = parsed.get("usage") or {}
            assistant_text = parsed["choices"][0]["message"]["content"] or ""
        except Exception as exc:
            parse_error = str(exc)

        return {
            "latency_ms": t1 - t0,
            "ok": result.ok and parse_error is None,
            "status": result.status,
            "error": result.error,
            "parse_error": parse_error,
            "assistant_text": assistant_text,
            "usage": usage,
        }

    def _evaluate_single(self, task: dict[str, Any], text: str, success: bool) -> list[str]:
        errors: list[str] = []
        if not success or not text.strip():
            errors.append("completion_failed")
            return errors

        stripped = text.strip()
        ft = task.get("format_type")
        if ft == "json_keys":
            try:
                obj = json.loads(stripped)
                if not isinstance(obj, dict):
                    errors.append("json_object_expected")
                else:
                    for key in task.get("expected_keys", []):
                        if key not in obj:
                            errors.append(f"missing_key:{key}")
            except Exception:
                errors.append("json_format_invalid")

        if task.get("expected_answer_regex"):
            if re.search(task["expected_answer_regex"], text, flags=re.I) is None:
                errors.append("factual_mismatch")

        min_c = task.get("min_chars")
        if min_c is not None and len(stripped) < int(min_c):
            errors.append("min_chars_not_met")

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
        repeat_count = int(task.get("repeat_count", 1))
        results: list[dict[str, Any]] = []
        all_texts: list[str] = []
        all_errors: list[str] = []
        ok_count = 0
        consistent_count = 0

        for i in range(repeat_count):
            res = self._run_once(task, base_url, model, provider_key, timeout_s)
            results.append(res)
            all_texts.append(res["assistant_text"])
            if res["ok"]:
                ok_count += 1
                eval_errors = self._evaluate_single(task, res["assistant_text"], True)
                if not eval_errors:
                    consistent_count += 1
                else:
                    all_errors.extend([f"run_{i}_{e}" for e in eval_errors])
            else:
                if res["error"]:
                    all_errors.append(f"run_{i}_api_error:{res['error']}")
                if res["parse_error"]:
                    all_errors.append(f"run_{i}_parse_error:{res['parse_error']}")

        validation_errors: list[str] = []
        if ok_count < repeat_count:
            validation_errors.append(f"partial_failure:{ok_count}/{repeat_count}")
        if consistent_count < repeat_count:
            validation_errors.append(f"inconsistent:{consistent_count}/{repeat_count}")

        latencies = [r["latency_ms"] for r in results if r["ok"]]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        tokens = [r["usage"].get("total_tokens", 0) for r in results if r["ok"] and r["usage"]]
        avg_tokens = sum(tokens) / len(tokens) if tokens else 0

        return RunRecord(
            suite=self.name,
            task_id=task["id"],
            category=task.get("category", "reliability"),
            round_index=round_index,
            attempt=attempt,
            ok=(ok_count == repeat_count and consistent_count == repeat_count),
            latency_ms=int(avg_latency),
            total_tokens=int(avg_tokens) if avg_tokens else None,
            prompt_tokens=None,
            completion_tokens=None,
            response_text=all_texts[0] if all_texts else "",
            response_status=200 if ok_count == repeat_count else 500,
            api_error=";".join(all_errors) if all_errors else None,
            parse_error=None,
            validation_errors=validation_errors,
            evidence={
                "repeat_count": repeat_count,
                "ok_count": ok_count,
                "consistent_count": consistent_count,
                "all_latencies_ms": [r["latency_ms"] for r in results],
                "all_texts_preview": [t[:100] for t in all_texts],
            },
            extra={
                "reliability_mode": True,
                "consistency_rate": consistent_count / repeat_count if repeat_count else 0,
            },
        )
