from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunContext:
    suite: str
    task_id: str
    round_index: int
    attempt: int
    timeout_seconds: int


@dataclass
class RunRecord:
    suite: str
    task_id: str
    category: str
    round_index: int
    attempt: int
    ok: bool
    latency_ms: int
    total_tokens: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    response_text: str
    response_status: int
    api_error: str | None
    parse_error: str | None
    validation_errors: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SuiteResult:
    suite: str
    task_count: int
    records: list[RunRecord]
