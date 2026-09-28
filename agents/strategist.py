"""Strategy Agent（Phase 7）。

流程：Research ↓ Account Memory ↓ 历史内容 ↓ 历史表现 ↓ Strategy ↓ Topic Recommendation。

只读记忆，不写任何笔记；历史表现只作观察引用，不参与评分、不直接改策略。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.base_agent import BaseAgent
from runtime.memory_api import MemoryAPI
from runtime.strategy import VERDICTS, MemoryContext, build_briefs
from runtime.topic_engine import TopicEngine


class StrategyAgent(BaseAgent):
    """回答「这个选题为什么适合这个账号」。"""

    def __init__(self, memory: MemoryAPI | None = None, engine: TopicEngine | None = None) -> None:
        super().__init__("Strategy Agent", "策略判断", 2500)
        self._memory = memory
        self._engine = engine

    @property
    def memory(self) -> MemoryAPI:
        if self._memory is None:
            self._memory = MemoryAPI()
        return self._memory

    @property
    def engine(self) -> TopicEngine:
        if self._engine is None:
            self._engine = TopicEngine(memory=self.memory)
        return self._engine

    def run(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        recommendations = context.get("recommendations")
        warnings: list[str] = []

        if recommendations is None:
            candidates = context.get("candidates")
            if candidates is None:
                failure = self.build_result(
                    task=task,
                    summary="缺少输入：需要 candidates（Phase 5）或 recommendations（Phase 6）",
                    details="策略判断不凭空开始：先跑 Research Agent 产出候选选题，或直接传入 Topic Engine 的推荐结果。",
                    errors=["context 里没有 candidates 也没有 recommendations"],
                    next_actions=["先运行 ResearchAgent 得到候选选题", "或传 recommendations 跳过评分环节"],
                )
                failure["strategies"] = []
                failure["recommendations"] = []
                failure["warnings"] = []
                return failure
            engine_result = self.engine.recommend(candidates, top_k=int(context.get("top_k", 5)))
            recommendations = engine_result["recommendations"]
            warnings = engine_result["warnings"]

        context_snapshot = self.memory_context()
        briefs = build_briefs(list(recommendations), context_snapshot)

        counts = {verdict: 0 for verdict in VERDICTS}
        for brief in briefs:
            counts[brief.verdict] += 1
        summary = "、".join(f"{verdict} {count}" for verdict, count in counts.items() if count)

        result = self.build_result(
            task=task,
            summary=f"{len(briefs)} 个选题：" + (summary or "无可判断项"),
            details=_render(briefs),
            knowledge_points=sorted({brief.verdict for brief in briefs}),
            next_actions=[
                "「推荐」进入内容生产，「需人工判断」先补证据或换角度",
                "要据此调整策略先走 Memory Review，不要直接改 Strategy",
            ],
        )
        result["strategies"] = [brief.to_dict() for brief in briefs]
        result["recommendations"] = list(recommendations)
        result["warnings"] = warnings
        return result

    # ── 记忆快照（全部只读） ─────────────────────────────────────────────

    def memory_context(self) -> MemoryContext:
        account: dict[str, str] = {}
        strategy_sections: dict[str, str] = {}
        try:
            account = self.engine.account_profile()
            found = self.memory.get("strategy")
            if found["ok"]:
                strategy_sections = dict(found["sections"])
        except Exception:
            pass  # 记忆层不可用时仍给出可解释的 UNKNOWN 判断

        return MemoryContext(
            account=account,
            strategy_sections=strategy_sections,
            strategy_status=str(strategy_sections.get("状态") or ""),
            history=self._notes("content"),
            analytics=self._notes("analytics"),
            insights=self._notes("insight"),
        )

    def _notes(self, category: str) -> list[dict[str, Any]]:
        notes: list[dict[str, Any]] = []
        try:
            paths = self.memory.list_notes(category)
        except Exception:
            return notes
        for path in paths:
            found = self.memory.get(category, Path(path).stem)
            if found["ok"]:
                notes.append({"title": found["title"], "sections": dict(found["sections"])})
        return notes


def _render(briefs: list[Any]) -> str:
    if not briefs:
        return "没有可判断的选题。"
    blocks = []
    for index, brief in enumerate(briefs, start=1):
        lines = [f"### {index}. {brief.topic} — {brief.verdict}"]
        lines += [f"- 为什么适合：{line}" for line in brief.answer]
        lines += [f"- 策略依据：{line}" for line in brief.strategy_basis]
        lines += [f"- 历史内容：{line}" for line in brief.history]
        lines += [f"- 观察：{line}" for line in brief.observations]
        lines += [f"- 注意：{line}" for line in brief.caveats]
        blocks.append("\n".join(lines))
    return "## 策略判断\n\n" + "\n\n".join(blocks)
