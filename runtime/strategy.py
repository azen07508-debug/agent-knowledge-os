"""Phase 7：Strategy Brief——用记忆回答「这个选题为什么适合这个账号」。

输入 Phase 6 的 TopicRecommendation + 记忆上下文（Account/Strategy/Content/Analytics/Insights），
输出带判断的 StrategyBrief。

边界：
    只读记忆，不写任何笔记
    历史表现（Analytics/Insights）只作「观察」引用，不参与评分、不直接改策略
    策略状态非 Confirmed 时只进 caveats，不当作既定方向
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from runtime.topic_engine import overlap_words
from runtime.topics import CATEGORIES

VERDICT_RECOMMEND = "推荐"
VERDICT_JUDGE = "需人工判断"
VERDICT_REJECT = "不建议"
VERDICTS = (VERDICT_RECOMMEND, VERDICT_JUDGE, VERDICT_REJECT)


@dataclass
class MemoryContext:
    """策略判断依赖的记忆快照（全部只读）。"""

    account: dict[str, str] = field(default_factory=dict)
    strategy_sections: dict[str, str] = field(default_factory=dict)
    strategy_status: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)
    analytics: list[dict[str, Any]] = field(default_factory=list)
    insights: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class StrategyBrief:
    """一个选题的策略判断：结论 + 逐条理由 + 依据 + 观察 + 注意事项。"""

    topic: str
    verdict: str
    answer: list[str] = field(default_factory=list)
    strategy_basis: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    recommendation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_briefs(
    recommendations: list[Mapping[str, Any]],
    context: MemoryContext,
) -> list[StrategyBrief]:
    """对每个选题推荐产出一份 StrategyBrief，保持原顺序。"""
    return [_brief(dict(rec), context) for rec in recommendations]


# ── 单个选题 ────────────────────────────────────────────────────────────


def _brief(rec: Mapping[str, Any], ctx: MemoryContext) -> StrategyBrief:
    topic = str(rec.get("topic") or "未命名选题")
    category = str(rec.get("category") or "未分类")
    fit = str(rec.get("account_fit") or "UNKNOWN")
    blockers = list(rec.get("blockers") or [])

    basis = _strategy_basis(category, ctx)
    history = _history_hits(topic, category, ctx.history)
    observations = _observations(category, topic, ctx.analytics, ctx.insights)
    caveats = _caveats(ctx, observations, fit)

    answer = _answer(rec, ctx, basis, history, observations)
    verdict = _verdict(fit, blockers, history)

    return StrategyBrief(
        topic=topic,
        verdict=verdict,
        answer=answer,
        strategy_basis=basis,
        history=history,
        observations=observations,
        caveats=caveats,
        recommendation=dict(rec),
    )


def _verdict(fit: str, blockers: list[str], history: list[str]) -> str:
    if fit == "LOW":
        return VERDICT_REJECT
    if fit == "UNKNOWN":
        return VERDICT_JUDGE
    if history:
        return VERDICT_JUDGE  # 与已发内容重合，先决定换不换角度
    if fit == "HIGH" and not blockers:
        return VERDICT_RECOMMEND
    return VERDICT_JUDGE


def _answer(
    rec: Mapping[str, Any],
    ctx: MemoryContext,
    basis: list[str],
    history: list[str],
    observations: list[str],
) -> list[str]:
    """「为什么适合这个账号」的逐条回答，只引用真实读到的记忆。"""
    category = str(rec.get("category") or "未分类")
    account = ctx.account
    lines: list[str] = []

    if account.get("定位"):
        lines.append(
            f"账号定位「{account['定位']}」，受众「{account.get('受众') or '未填'}」；"
            f"选题分类「{category}」。"
        )

    fit_reason = next((w for w in rec.get("why") or [] if "账号定位词" in w or "共同词" in w or "没有直接关联" in w), "")
    if fit_reason:
        lines.append(fit_reason)

    if basis:
        lines.append("当前策略支撑：" + "；".join(basis))
    elif ctx.strategy_sections:
        lines.append("当前策略文本与该选题分类没有直接对应，选题范围需人工确认。")

    if history:
        lines.append("与已发内容重合：" + "；".join(history) + "，建议换角度或不做。")

    if observations:
        lines.append("历史表现参考：" + "；".join(observations) + "（仅作观察，不直接改策略）。")

    if not lines:
        lines.append("记忆不足，无法回答是否适合，需人工判断。")
    return lines


def _strategy_basis(category: str, ctx: MemoryContext) -> list[str]:
    if not ctx.strategy_sections:
        return []
    strategy_text = " ".join(str(value) for value in ctx.strategy_sections.values()).lower()
    hits = [word for word in CATEGORIES.get(category, ()) if word.lower() in strategy_text]
    if not hits:
        return []
    return [f"选题分类「{category}」命中策略关键词：{'、'.join(hits[:3])}"]


def _history_hits(topic: str, category: str, history: list[dict[str, Any]]) -> list[str]:
    hits = []
    for note in history:
        sections = note.get("sections") or {}
        text = " ".join(str(value) for value in sections.values()).lower()
        title = str(note.get("title") or "")
        shared = overlap_words(topic, text)
        if len(shared) >= 2:  # 只共用一个常见词（如 agent）不算重复选题
            hits.append(f"《{title}》共用词 {'、'.join(shared[:3])}")
        elif any(word in text for word in CATEGORIES.get(category, ())):
            hits.append(f"《{title}》同属「{category}」")
    return hits


def _observations(
    category: str,
    topic: str,
    analytics: list[dict[str, Any]],
    insights: list[dict[str, Any]],
) -> list[str]:
    """历史表现观察：命中才算，仅作引用。"""
    observations = []
    for note in analytics:
        sections = note.get("sections") or {}
        text = " ".join(str(value) for value in sections.values()).lower()
        if any(word in text for word in CATEGORIES.get(category, ())) or overlap_words(topic, text):
            observation = str(sections.get("观察") or "").strip()
            if observation:
                observations.append(f"{note['title']}：{observation}")
    for note in insights:
        sections = note.get("sections") or {}
        theme = str(sections.get("主题") or "").strip()
        if theme and any(word in theme.lower() for word in CATEGORIES.get(category, ())):
            observations.append(f"Insight《{note['title']}》：{theme}")
    return observations


def _caveats(ctx: MemoryContext, observations: list[str], fit: str) -> list[str]:
    caveats: list[str] = []
    if not ctx.strategy_sections:
        caveats.append("没有当前策略记忆，只基于账号画像判断。")
    elif ctx.strategy_status and ctx.strategy_status != "Confirmed":
        caveats.append(f"策略状态为「{ctx.strategy_status}」，仅作参考，不当作既定方向。")
    if observations:
        caveats.append("历史表现只作观察：要据此调整策略需走 Memory Review 生成 Insight。")
    if fit == "UNKNOWN":
        caveats.append("缺 Account Memory，无法判断账号契合度。")
    return caveats
