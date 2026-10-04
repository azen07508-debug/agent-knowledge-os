"""AIHOT → CreatorOS 的本地研究输入桥。

只读取 AIHOT 的公开 v1 精选快照，不把 AIHOT 的评分当成事实，也不自动发布。
导入后材料进入 ResearchStore，后续仍须经过账号契合、内容检查和人工审核。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any
from urllib.request import Request, urlopen

from runtime.research_store import ResearchItem, ResearchStore


def fetch_selected_snapshot(base_url: str, opener: Callable[..., Any] | None = None) -> dict[str, Any]:
    """读取 AIHOT 精选快照；失败直接抛出，避免把空结果冒充成功。"""
    url = f"{base_url.rstrip('/')}/api/v1/selected/snapshot"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "CreatorOSResearch/1.0"})
    read = opener or urlopen
    with read(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("AIHOT 精选快照格式不正确：缺少 items 数组")
    return payload


def import_selected_snapshot(
    payload: Mapping[str, Any],
    store: ResearchStore,
    *,
    query: str = "AIHOT selected",
    topic: str = "aihot-selected",
) -> dict[str, Any]:
    """把 AIHOT 精选条目导入 ResearchStore，保留原文与 AIHOT 证据链接。"""
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("AIHOT 精选快照格式不正确：items 不是数组")
    items: list[ResearchItem] = []
    skipped = 0
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            skipped += 1
            continue
        original = _text(_mapping(raw.get("links")).get("original"))
        aihot = _text(_mapping(raw.get("links")).get("aihot"))
        url = original or aihot
        if not url:
            skipped += 1
            continue
        title = _text(raw.get("title")) or _text(raw.get("originalTitle"))
        summary = _text(raw.get("summary"))
        source = _text(_mapping(raw.get("source")).get("name")) or "AIHOT"
        published = _text(raw.get("publishedAt"))
        score = raw.get("score")
        evidence = json.dumps(
            {
                "aihot_url": aihot,
                "original_url": original,
                "score": score,
                "reason": _text(raw.get("reason")),
                "attribution": _mapping(raw.get("attribution")),
            },
            ensure_ascii=False,
        )
        items.append(
            ResearchItem(
                source=source,
                url=url,
                title=title,
                timestamp=published,
                content=summary,
                topic=topic,
                evidence=evidence,
                query=query,
                fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                engagement={"aihot_score": score} if score is not None else {},
            )
        )
    result = store.save_many(items)
    return {**result, "skipped": skipped, "as_of": payload.get("asOf"), "cursor": payload.get("cursor")}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
