"""Phase 2：规则模型、注册表和条件匹配测试。"""

import pytest

from knowledge.default_rules import default_registry
from knowledge.rules import Rule, RuleRegistry


def rule(**overrides) -> Rule:
    values = {
        "id": "R1",
        "source": "local fixture",
        "school": "fixture",
        "category": "structure",
        "condition": {"x": 1},
        "conclusion": "结构事实",
    }
    values.update(overrides)
    return Rule(**values)


def test_rule_requires_traceable_metadata():
    with pytest.raises(ValueError, match="source"):
        rule(source="")
    with pytest.raises(ValueError, match="confidence"):
        rule(confidence="GUESS")


def test_registry_rejects_duplicate_and_unknown_conflict():
    registry = RuleRegistry()
    registry.add(rule())
    with pytest.raises(ValueError, match="已存在"):
        registry.add(rule())
    with pytest.raises(ValueError, match="未知冲突"):
        registry.add(rule(id="R2", conflicts_with=("R404",)))


def test_registry_matches_only_complete_conditions():
    registry = RuleRegistry()
    registry.add(rule(condition={"x": 1, "y": "yes"}))

    assert registry.match({"x": 1}) == ()
    matches = registry.match({"x": 1, "y": "yes"})
    assert len(matches) == 1
    assert matches[0].matched_conditions == ("x", "y")


def test_registry_filters_by_school_and_category():
    registry = default_registry()

    assert len(registry.list(school="zi_ping_structural", category="relation")) == 2
    assert registry.list(school="missing") == ()


def test_conflicts_are_explicit_and_deduplicated():
    registry = RuleRegistry()
    registry.add(rule(id="A", conflicts_with=()))
    registry.add(rule(id="B", conflicts_with=("A",)))

    assert registry.conflicts(["A", "B"]) == (("A", "B"),)
