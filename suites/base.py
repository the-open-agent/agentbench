from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..benchcore.models import RunRecord


class SuiteBase(ABC):
    name: str

    @abstractmethod
    def load_tasks(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
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
        ...
