"""流月与命盘关系规则的 service/API 测试。"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engines.bazi import BirthInput, SxtwlBaziProvider
from engines.bazi.time_engine import liu_month_at
from knowledge.default_rules import default_registry
from knowledge.evidence import build_evidence
from runtime.mingli_service import MingLiService

client = TestClient(app)


def payload():
    return {
        "year": 1990,
        "month": 2,
        "day": 1,
        "hour": 12,
        "gender": "男",
        "question": "事业",
    }


def chart():
    return SxtwlBaziProvider().calculate(BirthInput(1990, 2, 1, 12, gender="男"))


def birth():
    return {key: value for key, value in payload().items() if key != "question"}


def test_default_registry_matches_liu_month_relations_with_review_window_open():
    month = liu_month_at(chart(), date(2024, 12, 15))

    evidence = build_evidence(
        chart(),
        default_registry(),
        topic="事业",
        include_unreviewed=True,
        liu_month=month,
    )

    matched = {match.rule.id for match in evidence.matches}
    assert {"LIU_CLASH_001", "LIU_COMBINE_001", "LIU_BREAK_001"} <= matched
    assert set(evidence.rule_statuses) == {"UNREVIEWED"}


def test_service_target_date_attaches_liu_month_facts():
    response = MingLiService().analyze(
        birth(),
        payload()["question"],
        school="classical",
        policy="classical_approx_v1",
        version="1",
        target_date="2024-12-15",
    )

    facts = response.analysis["evidence"]["facts"]
    assert any(fact["type"] == "liu_month_relation" for fact in facts)
    assert response.metadata["liu_month"]["earthly_branch"] == "子"
    assert response.metadata["liu_month"]["solar_term"] == "大雪"


def test_service_rejects_malformed_target_date():
    with pytest.raises(ValueError, match="target_date"):
        MingLiService().analyze(birth(), payload()["question"], target_date="2024/12/15")


def test_api_accepts_target_date_and_reports_liu_month():
    response = client.post("/api/analyze", json={**payload(), "target_date": "2024-12-15"})

    assert response.status_code == 200
    assert response.json()["metadata"]["liu_month"]["solar_term"] == "大雪"


def test_api_rejects_malformed_target_date():
    response = client.post("/api/analyze", json={**payload(), "target_date": "2024/12/15"})

    assert response.status_code == 422
