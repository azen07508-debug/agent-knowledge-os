"""应用服务层测试。"""

from dataclasses import replace

import pytest

from knowledge.default_rules import default_registry
from knowledge.rules import RuleRegistry
from runtime.mingli_service import MingLiService


def birth_data():
    return {"year": 1990, "month": 2, "day": 1, "hour": 12}


def test_service_returns_complete_traceable_response():
    response = MingLiService().analyze(
        {**birth_data(), "gender": "男"},
        "事业",
        school="classical",
        policy="classical_approx_v1",
        version="1",
    )
    result = response.to_dict()

    assert result["chart"]["provider"] == "sxtwl"
    assert result["chart"]["pillars"]
    assert result["analysis"]["evidence"]["facts"]
    assert "rules" in result["analysis"]["evidence"]
    assert "passed" in result["critique"]


def test_service_rejects_empty_question():
    with pytest.raises(ValueError, match="问题不能为空"):
        MingLiService().analyze(birth_data(), "")


def test_service_injects_one_registry_into_analyst_and_critic():
    registry = default_registry()
    service = MingLiService(registry)

    assert service.registry is registry
    assert service.analyst.registry is registry
    assert service.critic.registry is registry


def test_service_critic_marks_unknown_rule_reference():
    service = MingLiService(RuleRegistry())
    analysis = service.analyst.analyze(
        service.calculator.calculate_chart(__import__("engines.bazi", fromlist=["BirthInput"]).BirthInput(**birth_data())),
        "事业",
    )
    from knowledge.default_rules import default_registry as defaults

    rule = defaults().list()[0]
    analysis = replace(
        analysis,
        evidence=replace(analysis.evidence, matches=(type("Match", (), {"rule": rule})(),)),
    )

    critique = service.critic.critique(analysis)

    assert not critique.passed
    assert any("不存在" in issue for issue in critique.issues)



def test_service_rejects_whitespace_questions_before_strategy_selection():
    import pytest

    service = MingLiService()
    birth = {"year": 1990, "month": 2, "day": 1, "hour": 12}
    selector = {"school": "classical", "policy": "classical_approx_v1", "version": "1"}
    for strategy in ({}, selector):
        with pytest.raises(ValueError, match="问题不能为空"):
            service.analyze(birth, " \t\n", **strategy)
