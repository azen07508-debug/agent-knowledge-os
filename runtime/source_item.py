"""统一外部来源材料的最小字段。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceItem:
    source: str
    title: str
    url: str
    published_at: str = ""
    content: str = ""
    author: str = ""
    source_type: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_aihot(cls, raw: Mapping[str, Any]) -> SourceItem:
        links_raw = raw.get("links")
        source_raw = raw.get("source")
        links: Mapping[str, Any] = links_raw if isinstance(links_raw, Mapping) else {}
        source: Mapping[str, Any] = source_raw if isinstance(source_raw, Mapping) else {}
        url = str(links.get("original") or links.get("aihot") or "").strip()
        if not url:
            raise ValueError("SourceItem 必须有来源 URL")
        return cls(
            source=str(source.get("name") or "AIHOT"),
            title=str(raw.get("title") or raw.get("originalTitle") or "").strip(),
            url=url,
            published_at=str(raw.get("publishedAt") or ""),
            content=str(raw.get("summary") or ""),
            author=str(raw.get("author") or ""),
            source_type="aihot",
            raw_metadata=dict(raw),
        )
