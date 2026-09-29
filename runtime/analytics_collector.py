"""Phase 16：AnalyticsCollector——发布之后按 job/内容采集表现指标。

数据来源：
- X：XAdapter.analytics(post_id)（真实读路径，opencli/twitter-cli 后端）；
- 六个国内平台：CONTRACT_ONLY，没有真实读 API → 诚实返回 NOT_IMPLEMENTED。

采集来源优先用 Phase 15 PublishJob 已成功发布的 attempt（published_post_id），
保证「发布记录 ↔ 表现数据」能对上；也支持直接传 post_id 单采。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from runtime.analytics_store import AnalyticsStore
from runtime.post_analytics import PostAnalytics
from runtime.publish_queue import PublishJobStore

# 六平台当前只有发布契约，读指标的 API 还没接
CONTRACT_ONLY_PLATFORMS = ("xiaohongshu", "douyin", "bilibili", "wechat_mp", "weibo", "channels")


class AnalyticsCollector:
    """把平台指标收进 AnalyticsStore；采集失败如实返回，不写空快照。"""

    def __init__(
        self,
        store: AnalyticsStore,
        x: Any | None = None,                 # XAdapter
        publish_store: PublishJobStore | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.x = x
        self.publish_store = publish_store
        self._clock = clock or datetime.now

    # ── 单条采集 ──────────────────────────────────────────────────────────

    def collect(
        self,
        post_id: str,
        platform: str = "x",
        *,
        content_id: str = "",
        content_type: str = "",
    ) -> dict[str, Any]:
        """采集一条 post 的指标 → 存快照。失败返回 ok=False，不写任何行。"""
        if not (post_id or "").strip():
            return {"ok": False, "platform": platform, "message": "缺少 post_id。"}
        if platform in CONTRACT_ONLY_PLATFORMS:
            return {
                "ok": False,
                "platform": platform,
                "error_code": "NOT_IMPLEMENTED",
                "message": f"{platform} 为 CONTRACT_ONLY：未接入指标读 API，采集不了（不编数）。",
            }
        if platform != "x":
            return {"ok": False, "platform": platform,
                    "message": f"未知平台：{platform}，没有对应的指标来源。"}
        if self.x is None or not getattr(self.x, "configured", False):
            return {"ok": False, "platform": "x", "message": "X 后端未配置，采集不了指标。"}

        result = self.x.analytics(post_id)
        if not result.get("ok"):
            return {"ok": False, "platform": "x",
                    "message": str(result.get("message") or "X analytics 失败。")}
        try:
            snap = PostAnalytics.from_backend(
                post_id, "x", result,
                content_id=content_id, content_type=content_type,
                source="x_backend",
            )
        except ValueError as exc:
            return {"ok": False, "platform": "x", "message": str(exc)}
        row_id = self.store.record(snap)
        return {"ok": True, "platform": "x", "row_id": row_id, "post_id": post_id,
                "metrics": snap.metrics, "engagement": snap.engagement,
                "engagement_rate": snap.engagement_rate,
                "attributed": snap.attributed, "is_retweet": snap.is_retweet}

    # ── 批量采集 ──────────────────────────────────────────────────────────

    def collect_content(self, content_id: str, post_ids: list[str] | None = None,
                        platform: str = "x", content_type: str = "") -> dict[str, Any]:
        """按内容采集：默认从 Phase 15 成功 job 的 attempt 里取 published_post_id。"""
        if post_ids is None:
            if self.publish_store is None:
                return {"ok": False, "content_id": content_id,
                        "message": "没传 post_ids 且未配置 PublishJobStore，找不到发布记录。"}
            post_ids = self.published_post_ids(content_id, platform=platform)
        if not post_ids:
            return {"ok": False, "content_id": content_id, "platform": platform,
                    "collected": 0, "failed": 0, "results": [],
                    "message": f"内容 {content_id} 在 {platform} 上没有成功发布的 post，无可采集。"}
        collected: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for post_id in post_ids:
            outcome = self.collect(post_id, platform, content_id=content_id,
                                   content_type=content_type)
            (collected if outcome["ok"] else failures).append(outcome)
        return {
            "ok": not failures,
            "content_id": content_id,
            "platform": platform,
            "collected": len(collected),
            "failed": len(failures),
            "results": collected + failures,
        }

    def collect_published(self, limit: int = 20) -> dict[str, Any]:
        """采集最近成功发布的所有 job（Phase 15 → Phase 16 的自动衔接）。"""
        if self.publish_store is None:
            return {"ok": False, "message": "未配置 PublishJobStore。"}
        jobs = self.publish_store.list_jobs()
        done = [job for job in jobs
                if job.status in ("SUCCEEDED", "FAILED")
                and self.published_post_ids(job.content_id, platform=job.platform, job_id=job.id)]
        done = done[-limit:]
        outcomes = []
        for job in done:
            for post_id in self.published_post_ids(job.content_id, platform=job.platform,
                                                   job_id=job.id):
                outcomes.append(self._collect_job_post(job, post_id))
        ok = sum(1 for item in outcomes if item["ok"])
        return {"ok": True, "scanned": len(jobs), "collected": ok,
                "failed": len(outcomes) - ok, "results": outcomes}

    def _collect_job_post(self, job: Any, post_id: str) -> dict[str, Any]:
        content_type = "thread" if job.platform == "x" else job.platform
        outcome = self.collect(post_id, job.platform, content_id=job.content_id,
                               content_type=content_type)
        outcome["job_id"] = job.id
        return outcome

    # ── 发布记录 → post_id ────────────────────────────────────────────────

    def published_post_ids(self, content_id: str, platform: str = "",
                           job_id: str = "") -> list[str]:
        """从 SUCCEEDED job 的 attempt 取 published_post_id（去重、保序）。"""
        if self.publish_store is None:
            return []
        jobs = [self.publish_store.get(job_id)] if job_id else self.publish_store.list_jobs(
            content_id=content_id, platform=platform)
        ids: list[str] = []
        for job in jobs:
            if job is None or job.status != "SUCCEEDED":
                continue
            if platform and job.platform != platform:
                continue
            for attempt in self.publish_store.attempts(job.id):
                if attempt.status in ("SUCCEEDED", "RECONCILED_SUCCESS") and attempt.published_post_id:
                    if attempt.published_post_id not in ids:
                        ids.append(attempt.published_post_id)
        return ids

    def snapshots(self) -> Mapping[str, int]:
        return self.store.counts()
