"""Phase 17：Analytics Agent 的核心——从表现数据里找模式，产出「候选」而不是结论。

流程（PLAN Phase 17）：
    Analytics → Pattern Detection → Insight Candidate → Evidence Check → Memory → Strategy Candidate

硬边界：
- 不直接修改策略：策略侧只产出 `StrategyCandidate(status=PROPOSED, applied=False)`，
  改 Strategy 必须人工确认后走 Memory API（PLAN Phase 0 原则 9/10、Phase 12 人审闸门）。
- 说事实不说指令：「最近 N 条里 X 类平均互动率 y%，其余 z%」，
  不是「以后全做 X」（PLAN Phase 17 的正反例）。
- 样本不足 / 没有对比组 / 低于基线 / 分组未标注 → 只报告被拦原因，不写记忆、不产候选。
- 只看自己内容：转发快照 `attributed=False` 由 AnalyticsStore 默认查询排除，这里不重复处理。
- 只按 content_type 分组：六平台指标读 API 还没接，按平台分组必然只有一类，算了也没有参照。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from runtime.analytics_store import AnalyticsStore
from runtime.memory_api import MemoryAPI
from runtime.post_analytics import PostAnalytics

MIN_SAMPLES = 3          # 有 views 的样本少于 3 条，不下候选
CONFIDENT_SAMPLES = 10   # 达到 10 条才给「中」；一次偶然的好数据永远到不了「高」
UNRATED = "未标注"

DIMENSION = "content_type"


# ── 数据结构 ────────────────────────────────────────────────────────────


@dataclass
class Pattern:
    """一个分组的事实统计（只算不算判）。"""

    key: str
    samples: int
    rated_samples: int = 0                  # 有 views、因而算得出互动率的样本
    avg_engagement_rate: float | None = None
    avg_views: float | None = None
    total_engagement: int = 0
    post_ids: list[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InsightCandidate:
    """一条候选洞察：观察式陈述 + 证据 + 证据闸门结论。"""

    subject: str
    statement: str
    samples: int = 0
    rated_samples: int = 0
    avg_engagement_rate: float | None = None
    baseline_rate: float | None = None      # 其余可比类型的合并平均
    lift: float | None = None               # 与基线的绝对差
    confidence: str = "低"                  # 只用「低 / 中」，不产生「高」
    evidence: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StrategyCandidate:
    """策略候选：默认不生效，等人工确认。本模块不提供任何「应用」方法。"""

    subject: str
    proposal: str
    rationale: str
    insight_topic: str
    status: str = "PROPOSED"
    applied: bool = False
    requires_review: bool = True
    next_step: str = (
        "人工确认后用 MemoryAPI 更新 strategy 并 recordDecision 写清变更原因；"
        "在此之前 Strategy 保持原样。"
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── 步骤 1：Pattern Detection ───────────────────────────────────────────


def detect_patterns(store: AnalyticsStore, *, limit: int = 50) -> list[Pattern]:
    """按 content_type 分组统计（`recent()` 已是每 post 最新一条、且排除转发）。

    只算事实不设闸门：拦不拦是 Evidence Check 的事，分组保留全量样本。
    """
    snaps = store.recent(limit=limit)
    groups: dict[str, list[PostAnalytics]] = {}
    for snap in snaps:
        key = (snap.content_type or "").strip() or UNRATED
        groups.setdefault(key, []).append(snap)

    patterns: list[Pattern] = []
    for key, items in groups.items():
        rates = [s.engagement_rate for s in items if s.engagement_rate is not None]
        views = [
            value
            for s in items
            if isinstance((value := s.metrics.get("views")), (int, float)) and not isinstance(value, bool)
        ]
        collected = [s.collected_at for s in items]
        patterns.append(
            Pattern(
                key=key,
                samples=len(items),
                rated_samples=len(rates),
                avg_engagement_rate=sum(rates) / len(rates) if rates else None,
                avg_views=sum(views) / len(views) if views else None,
                total_engagement=sum(s.engagement for s in items),
                post_ids=[s.post_id for s in items],
                first_seen=min(collected),
                last_seen=max(collected),
            )
        )
    # 互动率高的在前；算不出率的排最后；同率比样本量
    patterns.sort(
        key=lambda p: (p.avg_engagement_rate is None, -(p.avg_engagement_rate or 0.0), -p.samples, p.key)
    )
    return patterns


# ── 步骤 2：Insight Candidate ───────────────────────────────────────────


def build_insight_candidates(patterns: list[Pattern]) -> list[InsightCandidate]:
    """每个分组出一条候选：自己 vs 其余可比类型合并基线。"""
    rated = [p for p in patterns if p.avg_engagement_rate is not None and p.rated_samples > 0]
    total_samples = sum(p.samples for p in patterns)

    candidates: list[InsightCandidate] = []
    for pattern in patterns:
        others = [p for p in rated if p.key != pattern.key]
        baseline = _pooled_rate(others)
        lift = (
            pattern.avg_engagement_rate - baseline
            if pattern.avg_engagement_rate is not None and baseline is not None
            else None
        )
        candidates.append(
            InsightCandidate(
                subject=pattern.key,
                statement=_statement(pattern, baseline, lift, total_samples),
                samples=pattern.samples,
                rated_samples=pattern.rated_samples,
                avg_engagement_rate=pattern.avg_engagement_rate,
                baseline_rate=baseline,
                lift=lift,
                confidence=(
                    "中" if pattern.rated_samples >= CONFIDENT_SAMPLES else "低"
                ),  # 一次偶然表现到不了「高」
                evidence=[
                    f"维度={DIMENSION}:{pattern.key}",
                    f"post_ids={','.join(pattern.post_ids)}",
                    f"采集窗口={pattern.first_seen} ~ {pattern.last_seen}",
                ],
            )
        )
    return candidates


def _pooled_rate(patterns: list[Pattern]) -> float | None:
    """按 rated_samples 加权的合并平均互动率（没有可比样本 → None）。"""
    total_rate = 0.0
    total = 0
    for pattern in patterns:
        if pattern.avg_engagement_rate is None or pattern.rated_samples <= 0:
            continue
        total_rate += pattern.avg_engagement_rate * pattern.rated_samples
        total += pattern.rated_samples
    if total <= 0:
        return None
    return total_rate / total


def _statement(
    pattern: Pattern,
    baseline: float | None,
    lift: float | None,
    total_samples: int,
) -> str:
    """观察式陈述：带样本量与窗口，不用「应该/以后/全部」这类指令词。"""
    rate = pattern.avg_engagement_rate
    if rate is None:
        return (
            f"最近采集的 {total_samples} 条内容里，「{pattern.key}」类 {pattern.samples} 条"
            f"没有 views 数据，互动率算不出来。"
        )
    head = (
        f"最近采集的 {total_samples} 条内容里，「{pattern.key}」类 {pattern.samples} 条"
        f"平均互动率 {rate:.2%}"
    )
    if baseline is None or lift is None:
        return head + "，没有可比类型作参照。"
    return head + f"，其余可比类型 {baseline:.2%}（差 {lift:+.2%}）。"


# ── 步骤 3：Evidence Check ──────────────────────────────────────────────


def evidence_check(candidate: InsightCandidate, *, min_samples: int = MIN_SAMPLES) -> InsightCandidate:
    """证据闸门：不过就写明原因，`ready=False` 的候选不会进记忆也不会产策略候选。"""
    blockers: list[str] = []
    if candidate.subject == UNRATED:
        blockers.append("内容类型未标注，分组没有意义：采集时先传 content_type。")
    if candidate.avg_engagement_rate is None:
        blockers.append("算不出互动率（缺 views 数据），无法比较。")
    elif candidate.rated_samples < min_samples:
        blockers.append(f"有效样本不足：只有 {candidate.rated_samples} 条有 views 的样本，"
                        f"至少要 {min_samples} 条。")
    if candidate.baseline_rate is None:
        blockers.append("缺少对比组：只有一类内容，高/低没有参照。")
    elif candidate.lift is not None and candidate.lift <= 0:
        blockers.append(f"低于其余类型平均（{candidate.lift:+.2%}），不构成正向候选。")
    if not any(item.startswith("post_ids=") and item != "post_ids=" for item in candidate.evidence):
        blockers.append("没有可回溯的 post_id，结论无法复核。")

    candidate.blockers = blockers
    candidate.ready = not blockers
    return candidate


# ── 步骤 4：Memory（只写「观察」，等 Memory Review） ─────────────────────


def record_to_memory(candidate: InsightCandidate, memory: MemoryAPI, source: str = "analytics-agent") -> dict[str, Any]:
    """把通过闸门的候选写成 pending 观察（status=观察），不写成已验证 Insight。"""
    if not candidate.ready:
        raise ValueError("未通过证据闸门的候选不能进长期记忆。")
    return memory.recordObservation(
        topic=f"{DIMENSION}:{candidate.subject}",
        observation=candidate.statement,
        evidence="；".join(candidate.evidence),
        confidence=candidate.confidence,
        source=source,
    )


# ── 步骤 5：Strategy Candidate（只提案，不生效） ─────────────────────────


def propose_strategy(candidate: InsightCandidate) -> StrategyCandidate:
    """产出待人工确认的策略候选；本函数与本模块都不提供任何写 Strategy 的能力。"""
    if not candidate.ready:
        raise ValueError("未通过证据闸门的候选不能变成策略候选。")
    return StrategyCandidate(
        subject=candidate.subject,
        proposal=(
            f"考虑提高「{candidate.subject}」类内容的占比"
            f"（基于最近 {candidate.rated_samples} 条有 views 样本的互动率对比）"
        ),
        rationale=candidate.statement,
        insight_topic=f"{DIMENSION}:{candidate.subject}",
    )
