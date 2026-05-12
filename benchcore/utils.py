from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def now_ms() -> int:
    return int(time.time() * 1000)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def try_parse_json(text: str) -> tuple[Any | None, str | None]:
    raw = (text or "").strip()
    if not raw:
        return None, "empty response"
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        return json.loads(raw), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
