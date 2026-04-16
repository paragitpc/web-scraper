from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.storage import LocalStorage


@dataclass
class ScrapeResult:
    key: str
    status: str
    url: str = ""
    relative_path: str = ""
    size_bytes: int = 0
    sha256: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class SourceBase(ABC):
    name: str = ""
    country: str = ""

    def __init__(self, base_dir: str | Path, delay: float = 1.5) -> None:
        if not self.name:
            raise ValueError("subclass must set 'name'")
        self.delay = delay
        self.storage = LocalStorage(base_dir)
        self._index_keys: set[str] | None = None

    @property
    def index_keys(self) -> set[str]:
        if self._index_keys is None:
            self._index_keys = self.storage.load_index_keys(self.name)
        return self._index_keys

    def is_done(self, key: str) -> bool:
        return key in self.index_keys

    def mark_done(self, result: ScrapeResult) -> None:
        self.storage.append_index_record(
            source=self.name,
            key=result.key,
            url=result.url,
            relative_path=result.relative_path,
            size_bytes=result.size_bytes,
            sha256=result.sha256,
            extra=result.extra or None,
        )
        self.index_keys.add(result.key)

    @abstractmethod
    async def run(self, **kwargs: Any) -> dict[str, int]:
        ...
