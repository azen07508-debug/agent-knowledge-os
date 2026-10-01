"""Phase 18：核心闭环编排 FeedbackLoop。

PLAN 的闭环：`Research ↓ Strategy ↓ Content ↓ Publish ↓ Analytics ↓ Insight ↓ Memory ↓ Strategy`。

规则：
- 每个阶段只有四种结果：`ran`（真跑了）、`gated`（有输入但被人审/证据闸门挡住）、
  `skipped`（缺输入或缺能力，写清缺什么）、`failed`（异常，如实报错）。
  绝不把没跑的阶段写成成功。
- 人审闸门原样保留：Content 最多到 REVIEW、Publish 只发 APPROVED、
  洞察只写 pending 观察、策略候选永远 PROPOSED。
- 本层只读 Strategy 记忆，不写它，也不替人做任何决定。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.analytics import AnalyticsAgent
from agents.content import ContentAgent
from agents.researcher import ResearcherAgent
from agents.strategist import StrategyAgent
from runtime.analytics_store import AnalyticsStore
from runtime.memory_api import MemoryAPI

STAGES = ("research", "strategy", "content", "publish", "analytics", "insight", "memory", "strategy")

RAN = "ran"
GATED = "gated"
SKIPPED = "skipped"
FAILED = "failed"

# 内容状态里属于「还没过人审」的那些
UNAPPROVED = ("IDEA", "RESEARCHED", "DRAFT", "REVIEW")


def _safe(fn, default):
    """单个 store/后端出问题不该让整段阶段异常中断。"""
    try:
        return fn()
    except Exception:
        return default


@dataclass
class StageResult:
    """一个阶段的执行结果：状态 + 一句话结论 + 结构化数据。"""

    name: str
    status: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status,
                "summary": self.summary, "data": self.data}


class FeedbackLoop:
    """把 Phases 5→17 串成一圈；每个阶段缺什么就说什么，不做假成功。"""

    def __init__(
        self,
        *,
        memory: MemoryAPI | None = None,
        analytics_store: AnalyticsStore | None = None,
        researcher: ResearcherAgent | None = None,
        strategy_agent: StrategyAgent | None = None,
        content_agent: ContentAgent | None = None,
        analytics_agent: AnalyticsAgent | None = None,
        collector: Any | None = None,       # Phase 16 AnalyticsCollector
        worker: Any | None = None,          # Phase 15 PublishWorker
    ) -> None:
        self._memory = memory
        self._analytics_store = analytics_store
        self._researcher = researcher
        self._strategy_agent = strategy_agent
        self._content_agent = content_agent
        self._analytics_agent = analytics_agent
        self._collector = collector
        self._worker = worker

    @property
    def memory(self) -> MemoryAPI:
        if self._memory is None:
            self._memory = MemoryAPI()
        return self._memory

    @property
    def analytics_store(self) -> AnalyticsStore:
        if self._analytics_store is None:
            self._analytics_store = AnalyticsStore()
        return self._analytics_store

    @property
    def strategy_agent(self) -> StrategyAgent:
        if self._strategy_agent is None:
            self._strategy_agent = StrategyAgent(memory=self.memory)
        return self._strategy_agent

    @property
    def content_agent(self) -> ContentAgent:
        if self._content_agent is None:
            self._content_agent = ContentAgent(memory=self.memory)
        return self._content_agent

    @property
    def analytics_agent(self) -> AnalyticsAgent:
        if self._analytics_agent is None:
            self._analytics_agent = AnalyticsAgent(memory=self.memory, store=self.analytics_store)
        return self._analytics_agent

    # ── 主循环 ──────────────────────────────────────────────────────────

    def run(self, task: str = "本轮闭环", context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        steps: list[StageResult] = []

        research = self._step(STAGES[0], lambda: self._research(task, context))
        steps.append(research)
        candidates = list(research.data.get("candidates") or context.get("candidates") or [])

        strategy = self._step(STAGES[1], lambda: self._strategy(task, context, candidates))
        steps.append(strategy)
        recommendations = list(
            strategy.data.get("recommendations") or context.get("recommendations") or []
        )
        briefs = list(strategy.data.get("briefs") or [])

        content = self._step(STAGES[2], lambda: self._content(task, context, recommendations, briefs))
        steps.append(content)
        steps.append(self._step(STAGES[3], lambda: self._publish(context, content)))
        steps.append(self._step(STAGES[4], lambda: self._analytics(context)))
        steps.append(self._step(STAGES[5], lambda: self._insight(task, context)))
        memory_step = self._step(STAGES[6], self._memory_stage)
        steps.append(memory_step)
        steps.append(self._step(STAGES[7], lambda: self._strategy_feedback(memory_step)))

        insights = list(steps[5].data.get("insights") or [])
        strategy_candidates = list(steps[5].data.get("strategy_candidates") or [])
        pending = list(memory_step.data.get("pending") or [])

        counts = {status: sum(1 for step in steps if step.status == status)
                  for status in (RAN, GATED, SKIPPED, FAILED)}
        return {
            "ok": counts[FAILED] == 0,
            "task": task,
            "steps": [step.to_dict() for step in steps],
            "counts": counts,
            "content": dict(content.data),
            "insights": insights,
            "strategy_candidates": strategy_candidates,
            "pending_review": pending,
            "next_actions": self._next_actions(content, memory_step, strategy_candidates),
        }

    # ── 各阶段 ──────────────────────────────────────────────────────────

    def _research(self, task: str, context: dict[str, Any]) -> StageResult:
        materials, channel = context.get("materials"), context.get("channel")
        if materials is None and not channel:
            return StageResult("research", SKIPPED,
                               "缺外部输入：调研要联网抓材料，本轮不自动发起（提供 materials 或 channel 才跑）。")
        result = self._researcher_or_default().run(
            task, {key: value for key, value in context.items()
                   if key in ("materials", "channel", "limit", "topic")}
        )
        candidates = list(result.get("candidates") or [])
        return StageResult("research", RAN,
                           f"产出 {len(candidates)} 个候选选题（{result.get('material_count', 0)} 条材料）。",
                           {"candidates": candidates, "errors": list(result.get("errors") or [])})

    def _strategy(
        self,
        task: str,
        context: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> StageResult:
        recommendations = context.get("recommendations")
        if recommendations is None and candidates:
            engine_result = self.strategy_agent.engine.recommend(
                candidates, top_k=int(context.get("top_k", 5))
            )
            recommendations = engine_result["recommendations"]
        if not recommendations:
            return StageResult("strategy", SKIPPED, "缺选题：没有 candidates/recommendations，策略判断无从谈起。")

        result = self.strategy_agent.run(task, {"recommendations": recommendations})
        return StageResult("strategy", RAN,
                           f"{len(recommendations)} 个选题完成策略判断。",
                           {"recommendations": list(recommendations),
                            "briefs": list(result.get("strategies") or [])})

    def _content(
        self,
        task: str,
        context: dict[str, Any],
        recommendations: list[dict[str, Any]],
        briefs: list[dict[str, Any]],
    ) -> StageResult:
        selected = context.get("recommendation")
        brief = None
        if selected is None:
            picked = next((item for item in briefs if item.get("verdict") == "推荐"), None)
            if picked is None:
                # 人可以指定「今天就做这题」：本质是人工拍板，绕开 verdict 闸门但要留痕
                topic = str(context.get("topic") or "")
                picked = next((item for item in briefs
                               if topic and item.get("topic") == topic), None)
                if picked is None:
                    verdicts = "、".join(f"{item.get('topic')}→{item.get('verdict')}"
                                         for item in briefs) or "没有可判断的选题"
                    return StageResult("content", SKIPPED,
                                       f"没有 verdict=推荐 的选题（{verdicts}）："
                                       "起草前需要人工指定 recommendation 或 topic。")
            selected = picked.get("recommendation")
            brief = picked
        else:
            brief = next((item for item in briefs
                          if item.get("topic") == (selected or {}).get("topic")), None)

        result = self.content_agent.run(task, {"recommendation": selected, "brief": brief})
        content = result.get("content")
        if not content:
            return StageResult("content", SKIPPED, str(result.get("summary") or "没有生成内容。"))
        return StageResult(
            "content", RAN,
            f"{result['summary']}",
            {"content_id": content.get("id"), "status": content.get("status"),
             "pending_human_review": bool(result.get("pending_human_review")),
             "posts": len(result.get("posts") or [])},
        )

    def _publish(self, context: dict[str, Any], content: StageResult) -> StageResult:
        """发布阶段：先处理「已过审」的存量内容，再看今天新内容是否被人审拦住。

        注入 `x_workflow` 即代表「允许真实发送」（传 dry_run=False，不走演练，
        避免演练把内容标成 PUBLISHED）；六平台走注入的 `worker`（CONTRACT_ONLY 只演练）。
        """
        contents = _safe(lambda: self.content_agent.store.list(), [])
        approved = [item for item in contents if item.get("status") == "APPROVED"]
        status = str(content.data.get("status") or "")
        x_workflow = context.get("x_workflow")
        worker = context.get("worker") or self._worker

        if approved:
            if x_workflow is None and worker is None:
                return StageResult(
                    "publish", SKIPPED,
                    f"{len(approved)} 条内容已过审待发布，但没有注入发布能力"
                    "（X：context['x_workflow']，由 DailyPipeline --publish-x --send 打开；"
                    "六平台：context['worker']，且为 CONTRACT_ONLY 演练）。",
                    {"approved": [item.get("id") for item in approved],
                     "content_status": status},
                )
            return self._dispatch(approved, x_workflow, worker, context)

        if status in UNAPPROVED:
            return StageResult("publish", GATED,
                               f"内容停在 {status}：Phase 12 人审未通过，本轮不发布。",
                               {"content_status": status})
        if not status and not context.get("content_id"):
            return StageResult("publish", SKIPPED, "本轮没有可发布内容。")
        if worker is None and x_workflow is None:
            return StageResult("publish", SKIPPED,
                               "缺发布能力：context['worker'] / context['x_workflow'] 需显式注入。")
        outcome = worker.run_once() if worker is not None else None
        if outcome is None:
            return StageResult("publish", SKIPPED, "队列里没有到期 job。")
        return StageResult("publish", RAN,
                           f"发布 job {outcome.get('status')}：{outcome.get('message') or ''}".strip(),
                           {"outcome": outcome})

    @staticmethod
    def _dispatch(approved: list[dict[str, Any]], x_workflow: Any, worker: Any,
                  context: dict[str, Any]) -> StageResult:
        """真发：全部成功→ran；有失败→如实列原因；全失败→failed。"""
        del context
        outcomes: list[dict[str, Any]] = []
        if x_workflow is not None:
            for item in approved:
                content_id = str(item.get("id") or "")
                try:
                    result = x_workflow.publish(content_id, dry_run=False)
                except Exception as exc:  # 异常原因必须原样带回去，否则没法排查
                    result = {"ok": False, "message": f"XWorkflow.publish 异常：{exc}"}
                outcomes.append({"content_id": content_id, **dict(result)})
        if worker is not None:
            job = worker.run_once()
            if job is not None:
                outcomes.append({"job": job.get("id"), "status": job.get("status"),
                                 "ok": bool(job.get("ok")), "message": job.get("message", "")})

        done = [item for item in outcomes if item.get("ok")]
        failed = [item for item in outcomes if not item.get("ok")]
        messages = [f"{item.get('content_id') or item.get('job')}："
                    f"{item.get('message') or item.get('status') or '未知'}" for item in failed]
        data = {"approved": len(approved),
                "published": [item.get("content_id") or item.get("job") for item in done],
                "failed": messages}
        if done and not failed:
            return StageResult("publish", RAN, f"发布成功 {len(done)} 条。", data)
        if done:
            return StageResult("publish", RAN,
                               f"发布成功 {len(done)} 条，失败 {len(failed)} 条：" + "；".join(messages),
                               data)
        if failed:
            return StageResult("publish", FAILED,
                               f"{len(failed)} 条发布全部失败：" + "；".join(messages), data)
        return StageResult("publish", SKIPPED,
                           "发布能力已注入，但没有执行任何发布（队列无到期 job）。", data)

    def _analytics(self, context: dict[str, Any]) -> StageResult:
        collector = context.get("collector") or self._collector
        if collector is None:
            return StageResult("analytics", SKIPPED,
                               "缺采集器：Phase 16 AnalyticsCollector（要 X 后端与发布记录）未注入。")
        outcome = collector.collect_published(limit=int(context.get("collect_limit", 20)))
        return StageResult("analytics", RAN,
                           f"采集 {outcome.get('collected', 0)} 条，失败 {outcome.get('failed', 0)} 条。",
                           {"outcome": outcome})

    def _insight(self, task: str, context: dict[str, Any]) -> StageResult:
        result = self.analytics_agent.run(
            task,
            {"store": self.analytics_store,
             "write_memory": bool(context.get("write_memory", True)),
             "limit": int(context.get("limit", 50))},
        )
        if not result.get("patterns"):
            return StageResult("insight", SKIPPED,
                               f"{result.get('summary', '没有可分析的表现数据')}：先跑 Phase 16 采集。",
                               {"errors": list(result.get("errors") or [])})
        return StageResult(
            "insight", RAN,
            f"{result['summary']}；写入观察 {len(result.get('memory_writes') or [])} 条。",
            {"insights": list(result.get("insights") or []),
             "strategy_candidates": list(result.get("strategy_candidates") or []),
             "memory_writes": len(result.get("memory_writes") or []),
             "warnings": list(result.get("warnings") or [])},
        )

    def _memory_stage(self) -> StageResult:
        pending: list[dict[str, Any]] = []
        active: list[dict[str, Any]] = []
        other: list[dict[str, Any]] = []
        for path in self.memory.list_notes("insight"):
            title = Path(path).stem
            found = self.memory.get("insight", title)
            if not found["ok"]:
                continue
            entry = {
                "title": title,
                "status": str(found["frontmatter"].get("status") or ""),
                "confidence": str(found["frontmatter"].get("confidence") or ""),
                "topic": str(found["sections"].get("主题") or ""),
            }
            (pending if entry["status"] == "pending"
             else active if entry["status"] == "active" else other).append(entry)
        return StageResult("memory", RAN,
                           f"记忆里 {len(pending)} 条观察待 Memory Review，{len(active)} 条已验证洞察。",
                           {"pending": pending, "active": active, "other": other,
                            "total": len(pending) + len(active) + len(other)})

    def _strategy_feedback(self, memory_step: StageResult) -> StageResult:
        """闭环回到 Strategy：确认新一轮策略判断读得到刚写进去的记忆。"""
        snapshot = self.strategy_agent.memory_context()
        titles = [str(note.get("title") or "") for note in snapshot.insights]
        pending_titles = [entry["title"] for entry in memory_step.data.get("pending") or []]
        return StageResult(
            "strategy", RAN,
            f"下一轮 Strategy 会读到 {len(titles)} 条 insight 记忆（其中 {len(pending_titles)} 条待复核）——闭环回到 Strategy。",
            {"insight_notes": titles, "pending_titles": pending_titles,
             "analytics_notes": len(snapshot.analytics)},
        )

    # ── 人审入口 ────────────────────────────────────────────────────────

    def review_insight(self, title: str, approved: bool, reason: str = "") -> dict[str, Any]:
        """Memory Review 闸门：通过 → active（已验证）；驳回 → 归档，理由必须写清。"""
        result = self.memory.review("insight", title, approved, reason or None)
        return {"ok": bool(result.get("ok", True)), "title": title,
                "approved": approved, "result": result}

    # ── 辅助 ────────────────────────────────────────────────────────────

    def _researcher_or_default(self) -> ResearcherAgent:
        if self._researcher is None:
            self._researcher = ResearcherAgent()
        return self._researcher

    @staticmethod
    def _step(name: str, fn: Callable[[], StageResult]) -> StageResult:
        try:
            return fn()
        except Exception as exc:  # 一个阶段炸了不能让整圈信息丢失
            return StageResult(name, FAILED, f"阶段异常中止：{type(exc).__name__}: {exc}")

    @staticmethod
    def _next_actions(content: StageResult, memory_step: StageResult,
                      strategy_candidates: list[dict[str, Any]]) -> list[str]:
        actions: list[str] = []
        if content.status == RAN and content.data.get("pending_human_review"):
            content_id = content.data.get("content_id")
            actions.append(
                f"人审：runtime.human_review.approve(store, '{content_id}', ...) "
                "之后才进发布队列"
            )
        if content.status == GATED:
            actions.append(content.summary)
        pending = memory_step.data.get("pending") or []
        if pending:
            actions.append(
                f"复核观察：FeedbackLoop.review_insight('{pending[0]['title']}', approved=True) "
                "才会升级为已验证洞察"
            )
        if strategy_candidates:
            actions.append("策略候选仍是 PROPOSED：人工确认后才改 Strategy，并 recordDecision 写清原因")
        actions.append("下一轮 run() 会把这次的记忆当作输入（Research → … → Strategy 重来一遍）")
        return actions
