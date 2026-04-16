from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


class LocalStorage:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.index_dir = self.base_dir / "_index"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)

    def save_bytes(self, relative_path: str | Path, content: bytes) -> Path:
        target = self.base_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def save_text(self, relative_path: str | Path, content: str) -> Path:
        target = self.base_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def save_json(self, relative_path: str | Path, data: Any) -> Path:
        target = self.base_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target

    def exists(self, relative_path: str | Path) -> bool:
        return (self.base_dir / relative_path).exists()

    def index_path(self, source: str) -> Path:
        return self.index_dir / f"{source}.jsonl"

    def load_index_keys(self, source: str) -> set[str]:
        path = self.index_path(source)
        if not path.exists():
            return set()
        keys: set[str] = set()
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if "key" in record:
                        keys.add(record["key"])
                except json.JSONDecodeError:
                    continue
        return keys

    def iter_index(self, source: str) -> Iterator[dict[str, Any]]:
        path = self.index_path(source)
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def append_index_record(
        self,
        source: str,
        key: str,
        url: str,
        relative_path: str | Path,
        size_bytes: int,
        sha256: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "key": key,
            "url": url,
            "path": str(relative_path),
            "size_bytes": size_bytes,
            "sha256": sha256,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            record["extra"] = extra
        with self.index_path(source).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
