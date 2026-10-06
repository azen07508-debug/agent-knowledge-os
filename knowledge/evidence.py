"""从确定性命盘构建可追溯证据。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from engines.bazi.models import Chart
from engines.bazi.sxtwl_provider import BRANCH_RELATIONS
from knowledge.rules import RuleMatch, RuleRegistry

if TYPE_CHECKING:
    from engines.bazi.strategies import StrategyContext
    from engines.bazi.time_engine import LiuMonthContext


BRANCH_RELATION_BY_PAIR = {
    frozenset(pair): name for name, pairs in BRANCH_RELATIONS.items() for pair in pairs
}


@dataclass(frozen=True)
class Fact:
    type: str
    value: Any
    source: str
    confidence: float = 1.0


@dataclass(frozen=True)
class Evidence:
    topic: str
    facts: tuple[Fact, ...]
    matches: tuple[RuleMatch, ...]
    conflicts: tuple[tuple[str, str], ...]
    strength: float
    strategy_context: StrategyContext | None = None
    rule_statuses: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "facts": [fact.__dict__ for fact in self.facts],
            "rules": [match.rule.id for match in self.matches],
            "sources": [match.rule.source for match in self.matches],
            "conflicts": list(self.conflicts),
            "strength": self.strength,
            "strategy_context": (
                {
                    "school": self.strategy_context.school,
                    "policy": self.strategy_context.policy,
                    "version": self.strategy_context.version,
                    "assumptions": list(self.strategy_context.assumptions),
                }
                if self.strategy_context is not None else None
            ),
            "rule_statuses": list(self.rule_statuses),
        }


def extract_facts(
    chart: Chart, liu_month: LiuMonthContext | None = None
) -> tuple[Fact, ...]:
    """只提取命盘中实际存在的结构事实；可选叠加流月与命盘的结构关系。"""
    facts = [
        Fact("day_master", chart.day_master, "chart.day_master"),
        Fact("month_ten_god", chart.pillars[1].ten_god, "chart.pillars[1].ten_god"),
    ]
    for relation in chart.relations:
        facts.append(Fact("has_relation", relation["type"], "chart.relations"))
    if liu_month is not None:
        natal = tuple(pillar.earthly_branch for pillar in chart.pillars)
        for name, branch in zip(("year", "month", "day", "hour"), natal):
            relation = BRANCH_RELATION_BY_PAIR.get(frozenset((liu_month.earthly_branch, branch)))
            if relation:
                facts.append(
                    Fact(
                        "liu_month_relation",
                        relation,
                        f"liu_month.earthly_branch × chart.pillars.{name}",
                    )
                )
        if liu_month.earthly_branch in natal:
            facts.append(
                Fact("liu_month_branch_is_natal", True, "liu_month.earthly_branch")
            )
    return tuple(fact for fact in facts if fact.value is not None)


def _fact_map(facts: tuple[Fact, ...]) -> dict[str, Any]:
    """同名事实保留全部取值；仅一个取值时保持标量，兼容既有规则写法。"""
    grouped: dict[str, list[Any]] = {}
    for fact in facts:
        grouped.setdefault(fact.type, []).append(fact.value)
    return {
        key: values[0] if len(values) == 1 else frozenset(values)
        for key, values in grouped.items()
    }


def build_evidence(
    chart: Chart,
    registry: RuleRegistry,
    topic: str = "general",
    *,
    strategy_context: StrategyContext | None = None,
    include_unreviewed: bool = False,
    liu_month: LiuMonthContext | None = None,
) -> Evidence:
    facts = extract_facts(chart, liu_month)
    fact_map = _fact_map(facts)
    matches = tuple(
        match for match in registry.match(fact_map, include_unreviewed=include_unreviewed)
        if include_unreviewed or match.rule.status != "UNREVIEWED"
    )
    rule_ids = [match.rule.id for match in matches]
    conflicts = registry.conflicts(rule_ids)
    confidence = {"LOW": 0.4, "MEDIUM": 0.7, "HIGH": 1.0}
    base = sum(confidence[match.rule.confidence] for match in matches) / len(matches) if matches else 0.0
    strength = max(0.0, min(1.0, base - len(conflicts) * 0.15))
    statuses = tuple(match.rule.status for match in matches)
    return Evidence(topic, facts, matches, conflicts, round(strength, 4), strategy_context, statuses)
