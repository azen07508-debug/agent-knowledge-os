"""Phase 14：CanonicalPost —— 平台无关的内容规范模型。

CanonicalPost → PlatformFormatter → FormattedPayload（见 runtime/platform_formatter.py）。
一个 CanonicalPost 可以喂给任意平台 Formatter；本模型不含任何平台规则。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CanonicalPost:
    """平台无关的内容表示（标题/正文/标签/媒体/来源链接）。"""

    body: str
    title: str = ""
    tags: list[str] = field(default_factory=list)
    media: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    content_id: str = ""  # 关联的 ContentObject id（进 fingerprint 幂等键）

    def __post_init__(self) -> None:
        self.title = (self.title or "").strip()
        self.body = (self.body or "").strip()
        if not self.body:
            raise ValueError("CanonicalPost 必须有正文。")
        seen: set[str] = set()
        cleaned: list[str] = []
        for tag in self.tags or []:
            tag = str(tag).strip().lstrip("#")
            if tag and tag not in seen:
                seen.add(tag)
                cleaned.append(tag)
        self.tags = cleaned
        self.media = [str(item).strip() for item in (self.media or []) if str(item).strip()]
        self.links = [str(item).strip() for item in (self.links or []) if str(item).strip()]

    @classmethod
    def from_content_object(cls, obj: Any) -> CanonicalPost:
        """从 ContentObject 桥接（title=topic，body=core_content，links=sources）。"""
        return cls(
            title=getattr(obj, "topic", "") or "",
            body=getattr(obj, "core_content", "") or "",
            media=list(getattr(obj, "media", []) or []),
            links=list(getattr(obj, "sources", []) or []),
            content_id=getattr(obj, "id", "") or "",
        )
