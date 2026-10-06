"""Evidence Layer 第一版测试。"""

from datetime import date

from engines.bazi import BirthInput, SxtwlBaziProvider
from engines.bazi.time_engine import liu_month_at
from knowledge.default_rules import default_registry
from knowledge.evidence import build_evidence, extract_facts
from knowledge.rules import Rule, RuleRegistry


def chart():
    return SxtwlBaziProvider().calculate(BirthInput(1990, 2, 1, 12))


def relation_rule(rule_id: str, relation: str, category: str = "relation") -> Rule:
    return Rule(
        id=rule_id,
        source="地支关系表（算法定义，待流派解释核校）",
        school="zi_ping_structural",
        category=category,
        condition={"has_relation" if category == "relation" else "liu_month_relation": relation},
        conclusion=f"{relation} 结构事实。",
        status="ACTIVE",
    )


def liu_registry() -> RuleRegistry:
    registry = RuleRegistry()
    registry.add_many(
        [
            relation_rule("LIU_CLASH_001", "六冲", "liu_month"),
            relation_rule("LIU_COMBINE_001", "六合", "liu_month"),
            relation_rule("LIU_BREAK_001", "相破", "liu_month"),
            Rule(
                id="LIU_FUYIN_001",
                source="流月地支与命局同支（算法定义，待流派解释核校）",
                school="zi_ping_structural",
                category="liu_month",
                condition={"liu_month_branch_is_natal": True},
                conclusion="流月地支与命盘同支；仅结构事实。",
                status="ACTIVE",
            ),
        ]
    )
    return registry


def test_extract_facts_contains_only_calculated_values():
    facts = extract_facts(chart())

    assert any(fact.type == "day_master" for fact in facts)
    assert all(fact.source.startswith("chart.") for fact in facts)


def test_build_evidence_links_facts_to_rules():
    evidence = build_evidence(chart(), default_registry(), topic="general")

    assert evidence.topic == "general"
    assert evidence.strength >= 0
    assert all(match.rule.source for match in evidence.matches)
    assert "facts" in evidence.to_dict()


def test_repeated_fact_types_keep_every_value():
    multi = SxtwlBaziProvider().calculate(BirthInput(1988, 1, 1, 12))
    registry = RuleRegistry()
    registry.add_many(
        [relation_rule("BREAK_001", "相破"), relation_rule("CLASH_001", "六冲")]
    )

    evidence = build_evidence(multi, registry, topic="general")

    assert {match.rule.id for match in evidence.matches} == {"BREAK_001", "CLASH_001"}


def test_liu_month_facts_link_month_branch_to_natal_chart():
    month = liu_month_at(chart(), date(2024, 12, 15))

    evidence = build_evidence(
        chart(), liu_registry(), topic="general", include_unreviewed=True, liu_month=month
    )

    relations = {fact.value for fact in evidence.facts if fact.type == "liu_month_relation"}
    assert {"六合", "相破", "六冲"} <= relations
    assert {match.rule.id for match in evidence.matches} >= {
        "LIU_CLASH_001",
        "LIU_COMBINE_001",
        "LIU_BREAK_001",
    }


def test_liu_month_fuyin_marks_identical_branch():
    month = liu_month_at(chart(), date(2024, 5, 10))

    evidence = build_evidence(
        chart(), liu_registry(), topic="general", include_unreviewed=True, liu_month=month
    )

    assert any(
        fact.type == "liu_month_branch_is_natal" and fact.value is True
        for fact in evidence.facts
    )
    assert "LIU_FUYIN_001" in {match.rule.id for match in evidence.matches}


def test_no_liu_month_means_no_liu_facts():
    evidence = build_evidence(chart(), liu_registry(), topic="general", include_unreviewed=True)

    assert not any(fact.type.startswith("liu_month") for fact in evidence.facts)


def test_default_registry_ships_liu_month_rules_as_unreviewed():
    registry = default_registry()

    rules = registry.list(category="liu_month")

    assert {rule.id for rule in rules} >= {
        "LIU_CLASH_001",
        "LIU_COMBINE_001",
        "LIU_BREAK_001",
        "LIU_FUYIN_001",
    }
    assert all(rule.status == "UNREVIEWED" for rule in rules)
    assert all(rule.source for rule in rules)
