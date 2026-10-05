"""从公开帖子提炼创作者结构观察，不复制原文。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CreatorProfile:
    author: str
    source_urls: tuple[str, ...]
    topic_patterns: tuple[str, ...]
    title_pattern: str
    hook_pattern: str
    paragraph_length: str
    emotional_intensity: str
    cta_pattern: str
    samples: int
    engagement: str
    status: str


def extract_creator_profile(items: list[Mapping[str, Any]]) -> CreatorProfile:
    """从帖子文本提取结构特征；不把原文写入 Profile。"""
    if not items:
        return CreatorProfile("UNKNOWN", (), (), "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", 0, "UNKNOWN", "HYPOTHESIS")
    author = str(items[0].get("author") or "UNKNOWN")
    source_urls = tuple(dict.fromkeys(str(item.get("url") or "").strip() for item in items if str(item.get("url") or "").strip()))
    texts = [str(item.get("text") or "") for item in items]
    titles = [str(item.get("title") or "") for item in items]
    avg_paragraph = sum(len(p) for text in texts for p in re.split(r"\n\s*\n", text) if p.strip()) / max(1, sum(1 for text in texts for p in re.split(r"\n\s*\n", text) if p.strip()))
    scores = [float(item["likes"]) for item in items if isinstance(item.get("likes"), (int, float))]
    views = [float(item["views"]) for item in items if isinstance(item.get("views"), (int, float))]
    engagement = f"likes_avg={sum(scores)/len(scores):.1f}" if scores else "UNKNOWN"
    if views:
        engagement += f";views_avg={sum(views)/len(views):.1f}"
    return CreatorProfile(
        author=author,
        source_urls=source_urls,
        topic_patterns=("工具/资源",) if any(k in " ".join(texts).lower() for k in ("工具", "github", "传送门")) else ("UNKNOWN",),
        title_pattern="反差/痛点 + 结果" if any(t for t in titles) else "UNKNOWN",
        hook_pattern="个人发现/真实痛点" if any(k in " ".join(texts) for k in ("我发现", "我本来", "痛点")) else "结果先行",
        paragraph_length="短段落" if avg_paragraph < 80 else "长段落",
        emotional_intensity="高" if any(k in " ".join(texts) for k in ("卧槽", "离谱", "狠货", "🚨")) else "中",
        cta_pattern="传送门/链接" if any(k in " ".join(texts) for k in ("传送门", "https://")) else "无明显 CTA",
        samples=len(items),
        engagement=engagement,
        status="CONFIRMED" if len(items) >= 10 else "OBSERVED" if len(items) >= 3 else "HYPOTHESIS",
    )
