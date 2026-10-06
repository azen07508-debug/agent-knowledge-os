"""日主旺衰策略测试。"""

from dataclasses import FrozenInstanceError

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engines.bazi import BirthInput, SxtwlBaziProvider
from engines.bazi.strategy_registry import StrategyRegistry
from engines.bazi.strength import ClassicalStrengthPolicy, StrengthResult

client = TestClient(app)


def chart(year: int, month: int, day: int):
    return SxtwlBaziProvider().calculate(BirthInput(year, month, day, 12, gender="男"))


def test_strength_result_keeps_provenance_and_is_approximate():
    result = ClassicalStrengthPolicy().calculate(chart(1988, 1, 1))

    assert isinstance(result, StrengthResult)
    assert result.context.school == "classical"
    assert result.context.policy == "classical_strength_v1"
    assert result.context.version == "1"
    assert result.approximate is True
    assert result.evidence
    assert any("月令" in note for note in result.context.assumptions)


def test_strength_labels_known_vectors():
    strong = ClassicalStrengthPolicy().calculate(chart(1988, 1, 1))
    even = ClassicalStrengthPolicy().calculate(chart(1988, 1, 2))
    weak = ClassicalStrengthPolicy().calculate(chart(1988, 1, 10))

    assert (strong.label, even.label, weak.label) == ("身强", "中和", "身弱")
    assert strong.score > even.score > weak.score
    assert round(strong.score, 4) == 0.6667
    assert round(weak.score, 4) == 0.3846


def test_strength_factors_name_each_contributing_position():
    factors = ClassicalStrengthPolicy().calculate(chart(1988, 1, 1)).factors

    assert any("月支" in factor for factor in factors)
    assert all(factors)


def test_strength_result_is_immutable():
    result = ClassicalStrengthPolicy().calculate(chart(1988, 1, 1))

    with pytest.raises(FrozenInstanceError):
        result.label = "身弱"


def test_registry_runs_strength_policy_by_explicit_key():
    registry = StrategyRegistry()

    result = registry.run(
        chart(1988, 1, 1),
        school="classical",
        policy="classical_strength_v1",
        version="1",
    )

    assert result.context.policy == "classical_strength_v1"
    assert "classical_strength_v1" in {
        item.context.policy for item in registry.list()
    }


def test_api_returns_strength_result_when_explicitly_selected():
    response = client.post(
        "/api/analyze",
        json={
            "year": 1988,
            "month": 1,
            "day": 1,
            "hour": 12,
            "gender": "男",
            "question": "事业",
            "school": "classical",
            "policy": "classical_strength_v1",
            "version": "1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["strategy"]["context"]["policy"] == "classical_strength_v1"
    assert body["strategy"]["label"] in ("身强", "身弱", "中和")
    assert body["metadata"]["strategy_selection"] == "explicit"
