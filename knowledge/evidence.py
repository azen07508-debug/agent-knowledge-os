"""从确定性命盘构建可追溯证据。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engines.bazi.models import Chart
from knowledge.rules import RuleMatch, RuleRegistry


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "facts": [fact.__dict__ for fact in self.facts],
            "rules": [match.rule.id for match in self.matches],
            "sources": [match.rule.source for match in self.matches],
            "conflicts": list(self.conflicts),
            "strength": self.strength,
        }


def extract_facts(chart: Chart) -> tuple[Fact, ...]:
    """只提取命盘中实际存在的结构事实。"""
    facts = [
        Fact("day_master", chart.day_master, "chart.day_master"),
        Fact("month_ten_god", chart.pillars[1].ten_god, "chart.pillars[1].ten_god"),
    ]
    for relation in chart.relations:
        facts.append(Fact("has_relation", relation["type"], "chart.relations"))
    return tuple(fact for fact in facts if fact.value is not None)


def build_evidence(chart: Chart, registry: RuleRegistry, topic: str = "general") -> Evidence:
    facts = extract_facts(chart)
    fact_map = {fact.type: fact.value for fact in facts}
    matches = registry.match(fact_map)
    rule_ids = [match.rule.id for match in matches]
    conflicts = registry.conflicts(rule_ids)
    confidence = {"LOW": 0.4, "MEDIUM": 0.7, "HIGH": 1.0}
    base = sum(confidence[match.rule.confidence] for match in matches) / len(matches) if matches else 0.0
    strength = max(0.0, min(1.0, base - len(conflicts) * 0.15))
    return Evidence(topic, facts, matches, conflicts, round(strength, 4))
