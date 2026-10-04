"""Evidence Layer 第一版测试。"""

from engines.bazi import BirthInput, SxtwlBaziProvider
from knowledge.default_rules import default_registry
from knowledge.evidence import build_evidence, extract_facts


def chart():
    return SxtwlBaziProvider().calculate(BirthInput(1990, 2, 1, 12))


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
