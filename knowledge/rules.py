"""可追溯的命理规则模型与匹配器。

规则是候选解释，不是事实；匹配器只判断结构条件是否满足，不把规则结论
升级成确定性预测。每条规则都要求来源、流派和证据字段，便于后续审查。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALID_CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}


@dataclass(frozen=True)
class Rule:
    id: str
    source: str
    school: str
    category: str
    condition: dict[str, Any]
    conclusion: str
    confidence: str = "LOW"
    conflicts_with: tuple[str, ...] = ()
    evidence_required: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("规则必须有 id。")
        if not self.source.strip():
            raise ValueError(f"规则 {self.id} 必须有 source。")
        if not self.school.strip():
            raise ValueError(f"规则 {self.id} 必须有 school。")
        if self.confidence not in VALID_CONFIDENCE:
            raise ValueError(f"规则 {self.id} 的 confidence 非法：{self.confidence}")
        if not self.condition:
            raise ValueError(f"规则 {self.id} 必须有 condition。")


@dataclass(frozen=True)
class RuleMatch:
    rule: Rule
    matched_conditions: tuple[str, ...]
    missing_conditions: tuple[str, ...] = ()


@dataclass
class RuleRegistry:
    """规则注册表；重复 ID 或未知冲突引用都拒绝。"""

    _rules: dict[str, Rule] = field(default_factory=dict)

    def add(self, rule: Rule) -> None:
        if rule.id in self._rules:
            raise ValueError(f"规则 ID 已存在：{rule.id}")
        self._rules[rule.id] = rule
        unknown = [item for item in rule.conflicts_with if item not in self._rules]
        if unknown:
            del self._rules[rule.id]
            raise ValueError(f"规则 {rule.id} 引用了未知冲突规则：{', '.join(unknown)}")

    def add_many(self, rules: list[Rule] | tuple[Rule, ...]) -> None:
        for rule in rules:
            self.add(rule)

    def get(self, rule_id: str) -> Rule:
        try:
            return self._rules[rule_id]
        except KeyError as exc:
            raise KeyError(f"未知规则：{rule_id}") from exc

    def list(self, *, school: str = "", category: str = "") -> tuple[Rule, ...]:
        return tuple(
            rule for rule in self._rules.values()
            if (not school or rule.school == school)
            and (not category or rule.category == category)
        )

    def match(self, facts: dict[str, Any], *, school: str = "", category: str = "") -> tuple[RuleMatch, ...]:
        matches = []
        for rule in self.list(school=school, category=category):
            matched = tuple(key for key, expected in rule.condition.items() if facts.get(key) == expected)
            missing = tuple(key for key in rule.condition if key not in matched)
            if not missing:
                matches.append(RuleMatch(rule=rule, matched_conditions=matched))
        return tuple(matches)

    def conflicts(self, rule_ids: list[str] | tuple[str, ...]) -> tuple[tuple[str, str], ...]:
        selected = set(rule_ids)
        pairs = []
        for rule_id in selected:
            rule = self.get(rule_id)
            for conflict in rule.conflicts_with:
                if conflict in selected:
                    pairs.append(tuple(sorted((rule_id, conflict))))
        return tuple(sorted(set(pairs)))
