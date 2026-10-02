"""Phase 22：最终能力——早报 / 多平台生成 / 发布回执 / 晚报。

PLAN Phase 22 的四件事：
- 早上：告诉你「今天值得关注的 10 个话题」，再告诉你「其中 3 个最符合当前账号定位」；
- 生成 X Post / X Thread / 小红书 / 抖音 / B站 内容，你审核、修改一次；
- 系统发布到对应平台；
- 晚上：Analytics 分析今天内容表现；Memory 只把真正有价值的经验写入长期记忆。

边界（与全项目一致）：
- `generate` 只做本地渲染，不外发、不改内容状态；
- `publish` 必须 APPROVED；X 要显式注入 `x_workflow`（Phase 21 --publish-x --send）才真发，
  六平台走 CONTRACT_ONLY 适配器，如实返回「未接入真实发布」；
- `evening` 的洞察走 Phase 17 证据闸门，写进去的是 pending「观察」，
  升级为已验证洞察必须人复核（Memory Review）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.analytics import AnalyticsAgent
from runtime.canonical_post import CanonicalPost
from runtime.content_store import ContentStore
from runtime.memory_api import MemoryAPI
from runtime.platform_formatter import get_formatter
from runtime.publish_adapters import get_publish_adapter
from runtime.topic_engine import TopicEngine

MORNING_TOPICS = 10      # 早上给几个话题
MORNING_FIT = 3          # 其中几个「最符合当前账号定位」
DEFAULT_PLATFORMS = ("x", "xiaohongshu", "douyin", "bilibili")

_FIT_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "UNKNOWN": 3}


class Briefing:
    """Phase 22 的四个能力；每个方法独立可用，缺输入就如实说缺什么。"""

    def __init__(
        self,
        *,
        memory: MemoryAPI | None = None,
        store: ContentStore | None = None,
        analytics_store: Any | None = None,
        analytics_agent: AnalyticsAgent | None = None,
    ) -> None:
        self._memory = memory
        self._store = store
        self._analytics_store = analytics_store
        self._analytics_agent = analytics_agent

    @property
    def memory(self) -> MemoryAPI:
        if self._memory is None:
            self._memory = MemoryAPI()
        return self._memory

    @property
    def store(self) -> ContentStore:
        if self._store is None:
            self._store = ContentStore()
        return self._store

    @property
    def analytics_agent(self) -> AnalyticsAgent:
        if self._analytics_agent is None:
            self._analytics_agent = AnalyticsAgent(memory=self.memory, store=self._analytics_store)
        return self._analytics_agent

    # ── 早上：今天值得关注什么 ────────────────────────────────────────────

    def morning(self, candidates: list[dict[str, Any]] | None, *,
                limit: int = MORNING_TOPICS, top: int = MORNING_FIT) -> dict[str, Any]:
        """今天值得关注的 limit 个话题 + 其中 top 个最符合当前账号定位。"""
        items = [dict(item) for item in (candidates or [])]
        if not items:
            return {
                "ok": False,
                "topics": [],
                "top_fit": [],
                "warnings": [],
                "summary": "缺候选选题：早报要先有 Research 结果（materials 或 channel），本轮没有输入。",
            }

        ranked = TopicEngine(memory=self.memory).recommend(items, top_k=limit)
        topics = list(ranked.get("recommendations") or [])
        # 「最符合账号定位」= 账号契合 HIGH，按总分排序；不足 top 个不凑数
        high = sorted((item for item in topics if item.get("account_fit") == "HIGH"),
                      key=lambda item: -int(item.get("score") or 0))
        top_fit = high[:top]
        if len(top_fit) >= top:
            suffix = "。"
        else:
            suffix = f"（HIGH 契合只有 {len(high)} 个，不足 {top} 个不凑数）。"
        return {
            "ok": True,
            "topics": topics,
            "top_fit": top_fit,
            "account": ranked.get("account") or {},
            "warnings": list(ranked.get("warnings") or []),
            "summary": (f"今日值得关注 {len(topics)} 个话题；其中 {len(top_fit)} 个最符合当前账号定位"
                        f"{suffix}"),
        }

    # ── 白天：生成多平台内容，交人审核 ────────────────────────────────────

    def generate(self, content_id: str,
                 platforms: tuple[str, ...] | list[str] = DEFAULT_PLATFORMS) -> dict[str, Any]:
        """把一条内容渲染成各平台版本（只生成、不外发、不改状态）。"""
        obj = self.store.get(content_id)
        if obj is None:
            return {"ok": False, "content_id": content_id, "versions": [],
                    "summary": f"内容对象不存在：{content_id}"}
        if not (obj.core_content or "").strip():
            return {"ok": False, "content_id": content_id, "versions": [],
                    "summary": "没有可生成的正文：先过 Phase 9 起草。"}

        post = CanonicalPost.from_content_object(obj)
        versions: list[dict[str, Any]] = []
        for platform in platforms:
            try:
                formatted = get_formatter(platform).format(post, dry_run=True)
            except ValueError as exc:  # 未知平台要指名道姓，别整批失败
                versions.append({"platform": platform, "ok": False, "message": str(exc)})
                continue
            versions.append({
                "platform": platform,
                "label": str(formatted.metadata.get("label") or formatted.platform),
                "ok": True,
                "valid": bool(formatted.valid),
                "errors": list(formatted.errors),
                "warnings": list(formatted.warnings),
                "preview": formatted.preview(),
                "fingerprint": formatted.fingerprint,
            })

        ready = [item for item in versions if item.get("ok") and item.get("valid")]
        summary = (f"生成 {len(ready)}/{len(versions)} 个平台版本（内容状态 {obj.status}，"
                   "只生成不发布；人审核改一次后才谈发布）。")
        return {"ok": bool(ready), "content_id": content_id, "status": obj.status,
                "versions": versions, "summary": summary}

    # ── 发布：只有 APPROVED 才发，平台如实回执 ────────────────────────────

    def publish(self, content_id: str,
                platforms: tuple[str, ...] | list[str] = DEFAULT_PLATFORMS,
                *, x_workflow: Any | None = None) -> dict[str, Any]:
        """按平台发布一条已过审内容，逐平台回执（与队列语义的 FeedbackLoop 不同）。"""
        obj = self.store.get(content_id)
        if obj is None:
            return {"ok": False, "content_id": content_id, "results": [],
                    "summary": f"内容对象不存在：{content_id}"}
        if obj.status != "APPROVED":
            return {"ok": False, "content_id": content_id, "status": obj.status, "results": [],
                    "summary": f"未过人审：当前 {obj.status}，只有 APPROVED 才能发布（Phase 12 强制人审）。"}

        post = CanonicalPost.from_content_object(obj)
        results: list[dict[str, Any]] = []
        for platform in platforms:
            if platform == "x":
                results.append(self._publish_x(content_id, x_workflow))
                continue
            try:
                adapter = get_publish_adapter(platform)
                payload = get_formatter(platform).format(post, dry_run=True)
                outcome = adapter.publish(payload)
            except ValueError as exc:
                results.append({"platform": platform, "ok": False, "message": str(exc)})
                continue
            results.append({
                "platform": platform,
                "ok": bool(outcome.get("ok")),
                "message": str(outcome.get("error_message") or outcome.get("message")
                               or ("已发布" if outcome.get("ok") else "发布失败")),
            })

        done = [item for item in results if item.get("ok")]
        failed = [item for item in results if not item.get("ok")]
        if failed:
            detail = "；".join(f"{item['platform']}：{item['message']}" for item in failed)
            summary = f"发布成功 {len(done)} 个平台，失败 {len(failed)} 个：{detail}"
        elif done:
            summary = f"发布成功 {len(done)} 个平台。"
        else:
            summary = f"{len(platforms)} 个平台都没有执行发布。"
        return {"ok": bool(done), "content_id": content_id, "status": obj.status,
                "results": results, "summary": summary}

    @staticmethod
    def _publish_x(content_id: str, x_workflow: Any | None) -> dict[str, Any]:
        if x_workflow is None:
            return {"platform": "x", "ok": False,
                    "message": "缺 X 发布能力：需注入 x_workflow（Phase 21 --publish-x --send）。"}
        try:
            outcome = x_workflow.publish(content_id, dry_run=False)   # 注入即代表允许真实发送
        except Exception as exc:
            return {"platform": "x", "ok": False, "message": f"XWorkflow.publish 异常：{exc}"}
        return {"platform": "x", "ok": bool(outcome.get("ok")),
                "message": str(outcome.get("message") or ("已发布" if outcome.get("ok") else "发布失败"))}

    # ── 晚上：表现分析 + 记忆 ─────────────────────────────────────────────

    def evening(self, *, collector: Any | None = None, limit: int = 50,
                write_memory: bool = True) -> dict[str, Any]:
        """采集（可选）→ 表现分析 → 记忆写入情况；写入的是 pending 观察，不替人复核。"""
        warnings: list[str] = []
        collected: dict[str, Any] | None = None
        if collector is None:
            warnings.append("缺采集器：本次不采集（Phase 16 AnalyticsCollector 要 X 后端与发布记录）。")
        else:
            try:
                collected = collector.collect_published(limit=limit)
            except Exception as exc:
                collected = {"ok": False, "message": str(exc)}
                warnings.append(f"采集异常：{exc}")

        analysis = self.analytics_agent.run("晚报：今日表现分析",
                                            {"limit": limit, "write_memory": write_memory})
        pending = self._pending_insights()
        patterns = list(analysis.get("patterns") or [])
        return {
            "ok": True,
            "has_data": bool(patterns),
            "summary": str(analysis.get("summary") or ""),
            "collected": collected,
            "patterns": patterns,
            "insights": list(analysis.get("insights") or []),
            "strategy_candidates": list(analysis.get("strategy_candidates") or []),
            "memory_writes": len(analysis.get("memory_writes") or []),
            "pending_review": pending,
            "warnings": warnings + list(analysis.get("warnings") or []),
            "next_actions": list(analysis.get("next_actions") or []),
        }

    def _pending_insights(self) -> list[dict[str, str]]:
        """等着 Memory Review 的观察（pending），晚报要写清还欠人什么事。"""
        pending: list[dict[str, str]] = []
        for path in self.memory.list_notes("insight"):
            title = Path(path).stem
            found = self.memory.get("insight", title)
            if not found["ok"]:
                continue
            status = str(found["frontmatter"].get("status") or "")
            if status == "pending":
                pending.append({
                    "title": title,
                    "confidence": str(found["frontmatter"].get("confidence") or ""),
                    "topic": str(found["sections"].get("主题") or ""),
                })
        return pending
