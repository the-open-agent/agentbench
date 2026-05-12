from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..benchcore.models import RunRecord
from .base import SuiteBase
from .easychat_common import load_dialogue_dataset, run_chat_once


class DialogueSuite(SuiteBase):
    name = "dialogue"

    def __init__(self, root: Path) -> None:
        self.root = root

    def load_tasks(self) -> list[dict[str, Any]]:
        # Canonical data: datasets/dialogue/dataset.jsonl (split from baseperf).
        return load_dialogue_dataset(self.root)

    def _evaluate(self, case: dict[str, Any], text: str, success: bool) -> list[str]:
        errors: list[str] = []
        if not success or not text.strip():
            errors.append("completion_failed")
            return errors
        stripped = text.strip()
        ft = case.get("format_type")
        if ft == "json_keys":
            try:
                obj = json.loads(stripped)
                if not isinstance(obj, dict):
                    errors.append("json_object_expected")
                else:
                    for key in case.get("expected_keys", []):
                        if key not in obj:
                            errors.append(f"missing_key:{key}")
            except Exception:  # noqa: BLE001
                errors.append("json_format_invalid")
        elif ft == "json_array":
            try:
                obj = json.loads(stripped)
                if not isinstance(obj, list):
                    errors.append("json_array_expected")
            except Exception:  # noqa: BLE001
                errors.append("json_format_invalid")
        if case.get("expected_answer_regex"):
            if re.search(case["expected_answer_regex"], text, flags=re.I) is None:
                errors.append("factual_mismatch")
        for pattern in case.get("fact_patterns", []):
            if re.search(pattern, text, flags=re.I) is None:
                errors.append(f"fact_pattern_missing:{pattern}")
        for pattern in case.get("must_patterns", []):
            if re.search(pattern, text, flags=re.I) is None:
                errors.append(f"must_pattern_missing:{pattern}")
        for pattern in case.get("forbid_patterns", []):
            if re.search(pattern, text, flags=re.I):
                errors.append(f"forbidden_pattern_hit:{pattern}")
        min_c = case.get("min_chars")
        if min_c is not None and len(stripped) < int(min_c):
            errors.append("min_chars_not_met")
        max_c = case.get("max_chars")
        if max_c is not None and len(stripped) > int(max_c):
            errors.append("max_chars_exceeded")
        max_w = case.get("max_words")
        if max_w is not None and len(stripped.split()) > int(max_w):
            errors.append("max_words_exceeded")
        line_prefix = case.get("line_prefix")
        item_count = case.get("item_count")
        if line_prefix is not None and item_count is not None:
            lines = [ln for ln in stripped.splitlines() if ln.strip()]
            if len(lines) < int(item_count):
                errors.append("item_count_lines_not_met")
            else:
                for ln in lines[: int(item_count)]:
                    if not ln.startswith(str(line_prefix)):
                        errors.append(f"line_prefix_mismatch:{line_prefix!r}")
                        break
        elif item_count is not None and line_prefix is None:
            if any(p == "," for p in case.get("must_patterns", [])):
                parts = [p.strip() for p in stripped.split(",") if p.strip()]
                if len(parts) < int(item_count):
                    errors.append("comma_separated_item_count_not_met")
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
        result = run_chat_once(
            base_url=base_url,
            provider_key=provider_key,
            model=model,
            prompt=task["prompt"],
            timeout_s=timeout_s,
        )
        validation_errors = self._evaluate(task, result["assistant_text"], bool(result["ok_http_parse"]))
        ok = bool(result["ok_http_parse"]) and len(validation_errors) == 0
        return RunRecord(
            suite=self.name,
            task_id=task["id"],
            category=task.get("category", "dialogue"),
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
            extra={"dialogue_mode": True},
        )
