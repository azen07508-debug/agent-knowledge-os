"""扶抑用神策略测试。"""

from dataclasses import FrozenInstanceError

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engines.bazi import BirthInput, SxtwlBaziProvider
from engines.bazi.yongshen import ClassicalYongshenPolicy, YongshenResult

client = TestClient(app)


def chart(year: int, month: int, day: int):
    return SxtwlBaziProvider().calculate(BirthInput(year, month, day, 12, gender="男"))


def test_yongshen_result_keeps_provenance_and_dependency():
    result = ClassicalYongshenPolicy().calculate(chart(1988, 1, 1))

    assert isinstance(result, YongshenResult)
    assert result.context.school == "classical"
    assert result.context.policy == "classical_fuyi_yongshen_v1"
    assert result.approximate is True
    assert any("扶抑" in note for note in result.context.assumptions)
    assert "classical_strength_v1" in " ".join(result.evidence)


def test_yongshen_for_strong_chart_prefers_draining_elements():
    result = ClassicalYongshenPolicy().calculate(chart(1988, 1, 1))

    assert result.strength_label == "身强"
    assert set(result.favorable) == {"火", "土", "金"}
    assert set(result.unfavorable) == {"木", "水"}
    assert set(result.candidates) == {"金"}


def test_yongshen_for_weak_chart_prefers_supporting_elements():
    result = ClassicalYongshenPolicy().calculate(chart(1988, 1, 10))

    assert result.strength_label == "身弱"
    assert set(result.favorable) == {"木", "水"}
    assert set(result.unfavorable) == {"火", "土", "金"}
    assert set(result.candidates) == {"木"}


def test_yongshen_refuses_to_guess_for_balanced_chart():
    result = ClassicalYongshenPolicy().calculate(chart(1988, 1, 2))

    assert result.strength_label == "中和"
    assert result.favorable == ()
    assert result.candidates == ()
    assert any("中和" in conflict for conflict in result.conflicts)


def test_yongshen_result_is_immutable():
    result = ClassicalYongshenPolicy().calculate(chart(1988, 1, 1))

    with pytest.raises(FrozenInstanceError):
        result.candidates = ("水",)


def test_api_returns_yongshen_result_when_explicitly_selected():
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
            "policy": "classical_fuyi_yongshen_v1",
            "version": "1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["strategy"]["context"]["policy"] == "classical_fuyi_yongshen_v1"
    assert body["strategy"]["strength_label"] == "身强"
    assert body["strategy"]["candidates"] == ["金"]
