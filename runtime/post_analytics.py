"""Phase 16：PostAnalytics——发布之后收集的表现指标（平台无关模型）。

PLAN 收集项：Views / Likes / Comments / Reposts / Bookmarks / Followers /
Engagement / Publish Time / Content Type。

原则：
- 只存拿到的指标（backend 缺 views 就不填，engagement_rate 老实为 None，不编数）；
- `replies` 归一成 `comments`（backend 字段差异在这一层抹平）；
- 转发（is_retweet=True）的互动指标属于原作者内容，`attributed=False`，
  默认不计入自己内容的表现（聚合/趋势查询自动排除）；
- 不存帖子原文。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# PLAN 口径的指标全集；存的只是其中 backend 实际给的子集
METRIC_KEYS = ("views", "likes", "comments", "reposts", "bookmarks", "followers")

# backend 字段 → PLAN 口径（如 opencli 的 replies）
_METRIC_ALIASES = {
    "replies": "comments",
    "reply_count": "comments",
    "retweets": "reposts",
    "retweet_count": "reposts",
    "favorite_count": "likes",
    "like_count": "likes",
    "impression_count": "views",
    "view_count": "views",
    "bookmark_count": "bookmarks",
    "follower_count": "followers",
}

TS = "%Y-%m-%d %H:%M:%S"


def normalize_metrics(raw: Mapping[str, Any]) -> dict[str, int | float]:
    """归一字段名 + 数值类型；解析不了的丢弃（不猜）。"""
    metrics: dict[str, int | float] = {}
    for key, value in dict(raw).items():
        canonical = _METRIC_ALIASES.get(str(key), str(key))
        if canonical not in METRIC_KEYS:
            continue
        number: int | float | None = None
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            number = value
        else:
            try:
                number = float(str(value).replace(",", ""))
            except (TypeError, ValueError):
                continue
        if number is None:
            continue
        if isinstance(number, float) and number.is_integer():
            number = int(number)
        metrics[canonical] = number
    return metrics


def engagement_of(metrics: Mapping[str, int | float]) -> tuple[int, float | None]:
    """返回 (互动总数, 互动率)。views 缺失或为 0 → 率为 None（不算，也不编）。

    率保留完整精度不截断：四舍五入留给展示层，存储层不做有损舍入。
    """
    interactions = sum(
        int(metrics.get(key, 0) or 0)
        for key in ("likes", "comments", "reposts", "bookmarks")
    )
    views = metrics.get("views")
    if not isinstance(views, (int, float)) or views <= 0:
        return interactions, None
    return interactions, interactions / int(views)


@dataclass
class PostAnalytics:
    """一条内容在一次采集时刻的表现快照。"""

    post_id: str
    platform: str
    collected_at: str = ""
    content_id: str = ""          # 关联的 ContentObject（可空：平台侧独立数据）
    publish_time: str = ""        # PLAN: Publish Time（backend 给才有）
    content_type: str = ""        # PLAN: Content Type（post/thread/video…，上层标注）
    is_retweet: bool = False      # 转发：指标归原作者
    attributed: bool = True       # is_retweet=False 才算自己内容的表现
    metrics: dict[str, int | float] = field(default_factory=dict)
    engagement: int = 0
    engagement_rate: float | None = None
    source: str = ""              # 数据来源（backend 名，方便回溯）

    def __post_init__(self) -> None:
        if not (self.post_id or "").strip():
            raise ValueError("PostAnalytics 必须有 post_id。")
        if not (self.platform or "").strip():
            raise ValueError("PostAnalytics 必须有 platform。")
        if not self.collected_at:
            self.collected_at = datetime.now().strftime(TS)
        self.attributed = not self.is_retweet
        self.engagement, self.engagement_rate = engagement_of(self.metrics)

    @classmethod
    def from_backend(
        cls,
        post_id: str,
        platform: str,
        result: Mapping[str, Any],
        *,
        content_id: str = "",
        content_type: str = "",
        source: str = "",
    ) -> PostAnalytics:
        """从 backend analytics 返回构造（要求 ok=True 且带 metrics）。"""
        if not result.get("ok"):
            raise ValueError(f"backend analytics 未成功：{result.get('message')}")
        raw_metrics = result.get("metrics")
        if not isinstance(raw_metrics, Mapping) or not raw_metrics:
            raise ValueError("backend analytics 没有 metrics，构造不了 PostAnalytics。")
        return cls(
            post_id=str(post_id),
            platform=str(platform),
            content_id=content_id,
            content_type=content_type,
            publish_time=str(result.get("publish_time") or ""),
            is_retweet=bool(result.get("is_retweet")),
            metrics=normalize_metrics(raw_metrics),
            source=source or str(result.get("action") or ""),
        )
