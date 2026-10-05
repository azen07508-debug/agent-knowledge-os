"""Performance Memory：表现数据的多维度候选洞察。

硬边界（PLAN Phase 17 / 原则 10）：
- 只产出 PENDING / CANDIDATE 候选，模块不提供任何修改 Strategy 的能力；
- 样本不足只标 PENDING，不进 Memory Review；
- 聚合维度：content_type（采集时标注）、title_structure（标题结构）、
  creator_reference（正文里引用的创作者 @handle）。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from runtime.memory_api import MemoryAPI

MIN_SAMPLES = 3
DIMENSIONS = ("content_type", "title_structure", "creator_reference")


@dataclass(frozen=True)
class PerformanceInsight:
    dimension: str
    key: str
    samples: int
    avg_engagement_rate: float | None
    status: str  # PENDING=样本不足 / CANDIDATE=可进 Memory Review
    evidence: list[str] = field(default_factory=list)


def classify_title(title: str) -> str:
    """标题结构分类（规则式，只分形不改写）。"""
    if re.search(r"\d+\s*[个条项招步]", title):
        return "数字清单"
    if "？" in title or "?" in title or title.startswith(("为什么", "如何", "怎样", "怎么")):
        return "疑问"
    if any(word in title for word in ("别再", "不要", "警惕", "避坑", "误区")):
        return "反差警告"
    return "陈述"


def creator_reference(row: Mapping[str, Any]) -> str:
    """正文/主题里引用的创作者（@handle）；没有就如实记未引用。"""
    text = " ".join(str(row.get(key) or "") for key in ("topic", "hook", "core_content"))
    found = re.search(r"@([A-Za-z0-9_]{2,30})", text)
    return found.group(1) if found else "未引用"


def _first_title(row: Mapping[str, Any]) -> str:
    raw = row.get("title_candidates") or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = [raw]
    for title in raw:
        if str(title).strip():
            return str(title).strip()
    return str(row.get("hook") or "")


def build_insights(
    analytics: Any,
    contents: Sequence[Mapping[str, Any]],
    *,
    limit: int = 200,
) -> list[PerformanceInsight]:
    """最新快照（默认排除转发）× 内容对象，按三个维度分组统计。纯计算，不写记忆。"""
    by_id = {str(row.get("id") or ""): row for row in contents}
    groups: dict[tuple[str, str], dict[str, Any]] = {}

    for snap in analytics.recent(limit=limit):
        row = by_id.get(snap.content_id or "")
        if row is not None:
            keys = (
                ("content_type", snap.content_type or "未标注"),
                ("title_structure", classify_title(_first_title(row))),
                ("creator_reference", creator_reference(row)),
            )
        else:
            keys = (
                ("content_type", snap.content_type or "未标注"),
                ("title_structure", "未关联"),
                ("creator_reference", "未关联"),
            )
        for dimension, key in keys:
            group = groups.setdefault((dimension, key), {"rates": [], "posts": []})
            group["rates"].append(snap.engagement_rate)
            group["posts"].append(snap.post_id)

    insights: list[PerformanceInsight] = []
    for (dimension, key), group in groups.items():
        rates = [rate for rate in group["rates"] if rate is not None]
        samples = len(group["posts"])
        insights.append(
            PerformanceInsight(
                dimension=dimension,
                key=key,
                samples=samples,
                avg_engagement_rate=sum(rates) / len(rates) if rates else None,
                status="CANDIDATE" if samples >= MIN_SAMPLES else "PENDING",
                evidence=[
                    f"dimension={dimension}:{key}",
                    f"post_ids={','.join(group['posts'])}",
                    f"samples={samples}",
                ],
            )
        )
    order = {name: index for index, name in enumerate(DIMENSIONS)}
    insights.sort(key=lambda i: (order[i.dimension], -i.samples, i.key))
    return insights


def record_insight(insight: PerformanceInsight, memory: MemoryAPI) -> dict[str, Any]:
    """把 CANDIDATE 候选写成 pending 观察等 Memory Review；PENDING 一律拒绝。"""
    if insight.status != "CANDIDATE":
        raise ValueError(f"样本不足的 {insight.status} insight 不能进 Memory Review。")
    rate = "互动率缺 views 数据" if insight.avg_engagement_rate is None else f"平均互动率 {insight.avg_engagement_rate:.2%}"
    return memory.recordObservation(
        topic=f"{insight.dimension}:{insight.key}",
        observation=f"「{insight.key}」维度最近 {insight.samples} 条内容{rate}（候选，待复核，不改策略）。",
        evidence="；".join(insight.evidence),
        confidence="低",
        source="performance-memory",
    )


def tool_post_check(text: str) -> dict[str, Any]:
    """工具帖四要素：痛点、官方链接、适用人群、避坑（账号画像规则）。"""
    missing: list[str] = []
    if not any(word in text for word in ("痛点", "麻烦", "困扰", "重复", "浪费", "手动")):
        missing.append("pain_point")
    if not re.search(r"https?://", text):
        missing.append("official_url")
    if not any(word in text for word in ("适合", "适用", "人群", "如果你", "推荐给")):
        missing.append("audience")
    if not any(word in text for word in ("注意", "避坑", "限制", "风险", "缺点", "免费版", "付费", "局限")):
        missing.append("caveats")
    return {"ok": not missing, "missing": missing}
