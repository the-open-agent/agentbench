from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..benchcore.http_client import post_json
from ..benchcore.utils import now_ms, try_parse_json


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def load_baseperf_dataset(root: Path) -> list[dict[str, Any]]:
    """Performance suite only: canonical file under datasets/baseperf."""
    candidates = [
        root / "datasets" / "baseperf" / "dataset.jsonl",
        root / "openagenttest+easychatbench" / "bench" / "token_effect_compare" / "dataset.jsonl",
    ]
    for p in candidates:
        rows = _load_jsonl(p)
        if rows:
            return rows
    raise RuntimeError(f"baseperf dataset not found (tried: {[str(c) for c in candidates]})")


def load_dialogue_dataset(root: Path) -> list[dict[str, Any]]:
    """Dialogue quality suite only: single canonical JSONL under datasets/dialogue."""
    candidates = [
        root / "datasets" / "dialogue" / "dataset.jsonl",
    ]
    for p in candidates:
        rows = _load_jsonl(p)
        if rows:
            return rows
    raise RuntimeError(f"dialogue dataset not found (tried: {[str(c) for c in candidates]})")


def run_chat_once(
    *,
    base_url: str,
    provider_key: str,
    model: str,
    prompt: str,
    timeout_s: int,
    temperature: float = 0.2,
    top_p: float = 1.0,
    max_tokens: int = 256,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/api/chat/completions"
    payload = {
        "model": model,
        "stream": False,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
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
            assistant_text = ""
    return {
        "latency_ms": t1 - t0,
        "status": result.status,
        "api_error": result.error,
        "parse_error": parse_error,
        "assistant_text": assistant_text,
        "usage": usage,
        "ok_http_parse": result.ok and parse_error is None,
    }
