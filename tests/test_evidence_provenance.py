from engines.bazi import BirthInput, SxtwlBaziProvider
from engines.bazi.strategies import StrategyContext
from knowledge.evidence import build_evidence
from knowledge.rules import Rule, RuleRegistry


def chart():
    return SxtwlBaziProvider().calculate(BirthInput(1990, 2, 1, 12))


def registry_with(rule_status="UNREVIEWED"):
    registry = RuleRegistry()
    registry.add(
        Rule(
            id="R1",
            source="fixture",
            school="fixture-school",
            category="structure",
            condition={"day_master": chart().day_master},
            conclusion="结构事实",
            status=rule_status,
        )
    )
    return registry


def test_unreviewed_rule_can_be_used_in_internal_evidence_but_is_marked():
    evidence = build_evidence(
        chart(),
        registry_with(),
        strategy_context=StrategyContext("school-a", "policy-a", "1", ()),
        include_unreviewed=True,
    )

    assert [match.rule.id for match in evidence.matches] == ["R1"]
    assert evidence.rule_statuses == ("UNREVIEWED",)
    assert evidence.to_dict()["rule_statuses"] == ["UNREVIEWED"]


def test_deprecated_rules_are_not_matched_by_default():
    evidence = build_evidence(chart(), registry_with("DEPRECATED"))

    assert evidence.matches == ()


def test_evidence_serializes_strategy_provenance():
    context = StrategyContext("school-a", "policy-a", "v2", ("近似",))
    evidence = build_evidence(chart(), registry_with("ACTIVE"), strategy_context=context)

    assert evidence.to_dict()["strategy_context"] == {
        "school": "school-a",
        "policy": "policy-a",
        "version": "v2",
        "assumptions": ["近似"],
    }


def test_evidence_keeps_provenance_for_each_strategy():
    first = build_evidence(
        chart(), registry_with("ACTIVE"),
        strategy_context=StrategyContext("school-a", "policy-a", "1", ()),
    )
    second = build_evidence(
        chart(), registry_with("ACTIVE"),
        strategy_context=StrategyContext("school-b", "policy-b", "2", ()),
    )

    assert first.strategy_context != second.strategy_context
    assert first.to_dict()["strategy_context"]["school"] == "school-a"
    assert second.to_dict()["strategy_context"]["school"] == "school-b"
