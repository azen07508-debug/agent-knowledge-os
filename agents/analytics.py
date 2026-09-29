"""Analytics Agent（Phase 17）。

流程：Analytics → Pattern Detection → Insight Candidate → Evidence Check → Memory → Strategy Candidate。

只做分析与提案：
- 通过证据闸门的候选写成 pending「观察」，等 Memory Review 才能升级为已验证 Insight；
- 策略侧只产出 PROPOSED 候选，**本 Agent 不修改 Strategy、不把一次数据写成长期规则**。
"""

from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent
from runtime.analytics_agent import (
    MIN_SAMPLES,
    build_insight_candidates,
    detect_patterns,
    evidence_check,
    propose_strategy,
    record_to_memory,
)
from runtime.analytics_store import AnalyticsStore
from runtime.memory_api import MemoryAPI


class AnalyticsAgent(BaseAgent):
    """从表现数据里找模式，输出「候选」，把结论权留给人。"""

    def __init__(
        self,
        memory: MemoryAPI | None = None,
        store: AnalyticsStore | None = None,
        *,
        limit: int = 50,
        min_samples: int = MIN_SAMPLES,
    ) -> None:
        super().__init__("Analytics Agent", "表现分析", 2500)
        self._memory = memory
        self._store = store
        self._limit = limit
        self._min_samples = min_samples

    @property
    def memory(self) -> MemoryAPI:
        if self._memory is None:
            self._memory = MemoryAPI()
        return self._memory

    @property
    def store(self) -> AnalyticsStore:
        if self._store is None:
            self._store = AnalyticsStore()
        return self._store

    def run(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        store = context.get("store") or self.store
        limit = int(context.get("limit", self._limit))

        patterns = detect_patterns(store, limit=limit)
        if not patterns:
            failure = self.build_result(
                task=task,
                summary="没有可分析的表现数据",
                details=(
                    "AnalyticsStore 里读不到快照：先按 Phase 16 采集发布后的指标，再回来找模式。"
                    "没有数据时不生成任何洞察或策略候选。"
                ),
                errors=["patterns 为空：AnalyticsStore 里没有可用快照"],
                next_actions=["先按 Phase 16 采集：AnalyticsCollector.collect_published() 或 collect_content()"],
            )
            failure.update(
                patterns=[], insights=[], strategy_candidates=[], memory_writes=[], warnings=[]
            )
            return failure

        candidates = [
            evidence_check(candidate, min_samples=int(context.get("min_samples", self._min_samples)))
            for candidate in build_insight_candidates(patterns)
        ]
        passed = [candidate for candidate in candidates if candidate.ready]
        blocked = [candidate for candidate in candidates if not candidate.ready]

        memory_writes, warnings = self._remember(passed, enabled=bool(context.get("write_memory", True)))
        strategy_candidates = [propose_strategy(candidate) for candidate in passed]

        result = self.build_result(
            task=task,
            summary=(
                f"{len(patterns)} 类内容：候选洞察 {len(passed)} 条，"
                f"被证据闸门拦下 {len(blocked)} 条"
            ),
            details=_render(patterns, candidates),
            knowledge_points=sorted({candidate.subject for candidate in passed}) or ["无可用分组"],
            errors=[],
            next_actions=_next_actions(passed, blocked, memory_writes),
        )
        result["patterns"] = [pattern.to_dict() for pattern in patterns]
        result["insights"] = [candidate.to_dict() for candidate in candidates]
        result["strategy_candidates"] = [item.to_dict() for item in strategy_candidates]
        result["memory_writes"] = memory_writes
        result["warnings"] = warnings
        return result

    # ── Memory 步骤：只写 pending 观察 ──────────────────────────────────

    def _remember(self, candidates: list[Any], *, enabled: bool) -> tuple[list[dict], list[str]]:
        writes: list[dict] = []
        warnings: list[str] = []
        if not enabled:
            return writes, ["本次未写记忆（write_memory=False）：只出报告。"]
        for candidate in candidates:
            try:
                record = record_to_memory(candidate, self.memory)
            except Exception as exc:  # 记忆层不可用不该让分析结果丢失
                warnings.append(f"洞察写入记忆失败（{candidate.subject}）：{exc}")
                continue
            writes.append({"ok": True, "subject": candidate.subject, "record": record})
        return writes, warnings


def _next_actions(passed: list[Any], blocked: list[Any], writes: list[dict]) -> list[str]:
    actions: list[str] = []
    if writes:
        actions.append("候选洞察已写成「观察」（pending）：要升级为已验证 Insight 必须走 Memory Review")
    elif passed:
        actions.append("候选洞察本次未落记忆，先看报告再决定是否复核入库")
    actions.append("策略候选默认未生效：人工确认后才改 Strategy，并 recordDecision 写清变更原因")
    if blocked:
        actions.append("被拦分组补齐样本量或 content_type 标注后再分析")
    return actions


def _render(patterns: list[Any], candidates: list[Any]) -> str:
    lines = ["## 分组事实", ""]
    for pattern in patterns:
        rate = "算不出率" if pattern.avg_engagement_rate is None else f"{pattern.avg_engagement_rate:.2%}"
        lines.append(
            f"- 「{pattern.key}」：{pattern.samples} 条（有 views {pattern.rated_samples} 条），"
            f"平均互动率 {rate}，平均曝光 {pattern.avg_views or 0:.0f}"
            f"，采集窗口 {pattern.first_seen} ~ {pattern.last_seen}"
        )
    lines += ["", "## 候选洞察", ""]
    for candidate in candidates:
        mark = "通过" if candidate.ready else "拦下"
        lines.append(f"- [{mark}] {candidate.statement}")
        lines.append(f"  - 置信度：{candidate.confidence}；样本 {candidate.rated_samples} 条有 views")
        for blocker in candidate.blockers:
            lines.append(f"  - 拦下原因：{blocker}")
    return "\n".join(lines)
