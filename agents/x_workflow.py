"""Phase 11：X 内容工作流（参考 x-post-scheduler 的工作方式）。

支持：
    文章 URL → Research → 摘要 → 核心观点 → X Post → Thread → 人工修改 → 发布
    Topic → Thread
    Research（11-Research 结论） → Original Post

边界：
    摘要/观点是规则式抽取（可注入 content_agent 换更强生成器）
    发布前必须 APPROVED（Phase 12 强制人审），且走 XAdapter（X API 不散落）
"""

from __future__ import annotations

import re
from typing import Any

from agents.content import ContentAgent
from runtime.content_store import ContentStore
from runtime.memory_api import MemoryAPI
from runtime.reach_research import ReachResearch
from runtime.topics import classify, extract
from runtime.x_adapter import XAdapter, default_x_adapter


class XWorkflow:
    """三条工作流 + 一个受人审闸门约束的发布出口。"""

    def __init__(
        self,
        reach: ReachResearch | None = None,
        store: ContentStore | None = None,
        memory: MemoryAPI | None = None,
        x: XAdapter | None = None,
        content_agent: ContentAgent | None = None,
    ) -> None:
        self._reach = reach
        self._store = store
        self._memory = memory
        self._x = x
        self._content_agent = content_agent

    @property
    def reach(self) -> ReachResearch:
        if self._reach is None:
            self._reach = ReachResearch()
        return self._reach

    @property
    def store(self) -> ContentStore:
        if self._store is None:
            self._store = ContentStore()
        return self._store

    @property
    def memory(self) -> MemoryAPI:
        if self._memory is None:
            self._memory = MemoryAPI()
        return self._memory

    @property
    def x(self) -> XAdapter:
        if self._x is None:
            self._x = default_x_adapter()
        return self._x

    @property
    def content_agent(self) -> ContentAgent:
        if self._content_agent is None:
            self._content_agent = ContentAgent(store=self.store, memory=self.memory)
        return self._content_agent

    # ── 工作流 ──────────────────────────────────────────────────────────

    def url_to_draft(self, url: str, topic: str = "") -> dict[str, Any]:
        """文章 URL → 抓取 → 摘要/核心观点 → 待人工修改的 X Thread 草稿。"""
        fetched = self.reach.fetch(url, channel="page")
        if not fetched["ok"]:
            return self._failure(f"URL → Thread：{url}", fetched.get("message", "抓取失败。"),
                                 ["确认 URL 可访问，或改用其他通道"])
        candidate = candidate_from_page(url, fetched["digest"], topic)
        return self.content_agent.run(f"URL → Thread：{url}", {"recommendation": candidate})

    def topic_to_thread(self, candidate: dict[str, Any], brief: dict[str, Any] | None = None) -> dict[str, Any]:
        """Topic → Thread（复用 Content Agent 的三道检查）。"""
        return self.content_agent.run(f"Topic → Thread：{candidate.get('topic', '')}",
                                      {"recommendation": candidate, "brief": brief})

    def research_to_post(self, research_topic: str) -> dict[str, Any]:
        """11-Research 的结论 → 原帖（Original Post）草稿。"""
        found = self.memory.get("research", f"研究-{research_topic}")
        if not found["ok"]:
            return self._failure(f"Research → Post：{research_topic}", found.get("message", "找不到研究记忆。"),
                                 ["先用 ReachResearch.research() 写入结论"])
        sections = found["sections"]
        conclusions = _lines(sections.get("关键结论"))
        sources = _lines(sections.get("重要来源"))
        quote = "；".join(conclusions)
        candidate = {
            "topic": sections.get("主题") or research_topic,
            "angle": conclusions[0] if conclusions else "",
            "angles": conclusions[:1],
            "audience": "",
            "category": classify(sections.get("主题") or research_topic),
            "sources": sources,
            "evidence": [{"url": url, "quote": quote} for url in sources[:3]],
            "facts": conclusions,
            "opinions": [],
        }
        return self.content_agent.run(f"Research → Post：{research_topic}", {"recommendation": candidate})

    # ── 发布出口（受 Phase 12 人审闸门约束） ─────────────────────────────

    def publish(self, content_id: str, dry_run: bool | None = None) -> dict[str, Any]:
        """发布已 APPROVED 的内容：XAdapter.thread → SCHEDULED → PUBLISHED。

        演练（dry_run=True）没有真实发送，绝不改状态；只有真实发送成功才推进。
        """
        obj = self.store.get(content_id)
        if obj is None:
            raise FileNotFoundError(f"内容对象不存在：{content_id}")
        if obj.status != "APPROVED":
            return {
                "ok": False,
                "content_id": content_id,
                "status": obj.status,
                "message": f"未通过人审：当前 {obj.status}，只有 APPROVED 才能发布（Phase 12 强制人审）。",
            }
        posts = [line for line in obj.core_content.splitlines() if line.strip()]
        if not posts:
            return {"ok": False, "content_id": content_id, "status": obj.status, "message": "没有可发布的正文。"}

        result = self.x.thread(posts, dry_run=dry_run)
        if not result.get("ok"):
            return {
                "ok": False,
                "content_id": content_id,
                "status": obj.status,
                "message": result.get("message", "X 发送失败。"),
                "posted": result.get("posted", 0),
            }
        if result.get("dry_run"):  # 演练：没真发，就不能把没发生的事写成已发生
            return {
                "ok": True,
                "content_id": content_id,
                "status": obj.status,
                "dry_run": True,
                "message": "演练完成，未真实发送：内容保持 APPROVED；真实发送要 dry_run=False。",
            }

        if not obj.platform_versions:
            obj.fill({"platform_versions": {"X": "Thread"}})  # 本工作流只发 X
        obj.transition("SCHEDULED")
        obj.transition("PUBLISHED")
        self.store.save(obj)
        return {
            "ok": True,
            "content_id": content_id,
            "status": obj.status,
            "dry_run": bool(result.get("dry_run")),
            "ids": result.get("ids", []),
            "platform_versions": dict(obj.platform_versions),
        }

    # ── 失败输出 ────────────────────────────────────────────────────────

    @staticmethod
    def _failure(task: str, message: str, next_actions: list[str]) -> dict[str, Any]:
        return {
            "agent": "X Workflow",
            "task": task,
            "summary": f"工作流失败：{message}",
            "details": message,
            "knowledge_points": [],
            "errors": [message],
            "next_actions": next_actions,
            "content": None,
            "posts": [],
            "checks": {},
            "pending_human_review": False,
        }


def candidate_from_page(url: str, digest: str, topic: str = "") -> dict[str, Any]:
    """规则式：页面首行当 Hook 素材，事实/观点沿用 topics.extract 的启发式。"""
    lines = [line.strip() for line in digest.splitlines() if line.strip()]
    title = topic or next((line.lstrip("# ").strip() for line in lines if line), url)
    excerpt = lines[0].lstrip("# ").strip() if lines else ""
    extracted = extract({"url": url, "content": digest, "title": title})
    evidence = extracted["evidence"] or ([{"url": url, "quote": excerpt[:80]}] if excerpt else [])
    return {
        "topic": title[:60],
        "angle": excerpt[:60] or title[:60],
        "angles": [excerpt[:60] or title[:60]],
        "audience": "",
        "category": classify(f"{title} {digest}"),
        "sources": [url],
        "evidence": evidence,
        "facts": extracted["facts"],
        "opinions": extracted["opinions"],
    }


def _lines(text: str | None) -> list[str]:
    """按行取出并清掉 markdown 列表/标题前缀（save_research 存的是 '- xxx' 格式）。"""
    cleaned = []
    for line in str(text or "").splitlines():
        line = re.sub(r"^[|\-*>#\s]+", "", line).strip()
        if line:
            cleaned.append(line)
    return cleaned
