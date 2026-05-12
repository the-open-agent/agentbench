from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..benchcore.http_client import post_json
from ..benchcore.models import RunRecord
from ..benchcore.utils import now_ms, try_parse_json
from .base import SuiteBase


class HardChatSuite(SuiteBase):
    name = "hardchat"

    def __init__(self, root: Path) -> None:
        self.root = root

    def load_tasks(self) -> list[dict[str, Any]]:
        jsonl = self.root / "datasets" / "hardchat" / "tasks.jsonl"
        if jsonl.exists():
            tasks: list[dict[str, Any]] = []
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                tasks.append(json.loads(line))
            return tasks
        preferred_yaml = self.root / "datasets" / "hardchat" / "tasks.yaml"
        legacy_yaml = self.root / "openagenthardchatbench" / "benchmarknew" / "tasks.yaml"
        src = preferred_yaml if preferred_yaml.exists() else legacy_yaml
        if not src.exists():
            raise RuntimeError(
                f"hardchat task file not found (expected {jsonl}, {preferred_yaml}, or {legacy_yaml})"
            )
        import yaml  # noqa: PLC0415 — lazy import when JSONL is absent (legacy layouts)

        data = yaml.safe_load(src.read_text(encoding="utf-8"))
        defaults = data.get("defaults") or {}
        out: list[dict[str, Any]] = []
        for t in data.get("tasks", []):
            row = dict(t)
            for k, v in defaults.items():
                row.setdefault(k, v)
            out.append(row)
        return out

    def _parse_json_block(self, text: str) -> Any | None:
        text = (text or "").strip()
        direct, _ = try_parse_json(text)
        if direct is not None:
            return direct
        a = text.find("{")
        b = text.rfind("}")
        if a >= 0 and b > a:
            obj, _ = try_parse_json(text[a : b + 1])
            return obj
        return None

    def _score(self, task: dict[str, Any], content: str) -> list[str]:
        parsed = self._parse_json_block(content)
        errors: list[str] = []
        if not isinstance(parsed, dict):
            return ["response_not_json_object"]
        for stage in ("collect", "normalize", "summarize"):
            if stage not in parsed:
                errors.append(f"missing_stage:{stage}")
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
            "temperature": float(task.get("temperature", 0)),
            "max_tokens": int(task.get("max_tokens", 12000)),
            "messages": [{"role": "user", "content": task["prompt"]}],
        }
        t0 = now_ms()
        result = post_json(url, payload, {"Authorization": f"Bearer {provider_key}"}, timeout_s)
        t1 = now_ms()
        parsed, parse_error = try_parse_json(result.text)
        usage = {}
        assistant_text = ""
        if isinstance(parsed, dict):
            usage = parsed.get("usage") or {}
            try:
                assistant_text = parsed["choices"][0]["message"]["content"] or ""
            except Exception:  # noqa: BLE001
                assistant_text = result.text
        validation_errors = self._score(task, assistant_text)
        ok = result.ok and parse_error is None and len(validation_errors) == 0
        return RunRecord(
            suite=self.name,
            task_id=task["id"],
            category=task.get("category", "hardchat"),
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
            evidence={},
            extra={},
        )
