from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class Document(BaseModel):
    country: str
    source: str
    doc_type: str
    number: str | None = None
    year: int | None = None
    title: str | None = None
    issued_at: date | None = None
    published_at: date | None = None
    summary: str | None = None
    text: str | None = None
    text_method: str | None = None
    source_url: str
    file_paths: list[str] = Field(default_factory=list)
    sha256: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    scraped_at: datetime = Field(default_factory=datetime.utcnow)


def to_record(doc: Document) -> dict[str, Any]:
    data = doc.model_dump(mode="json")
    return data
