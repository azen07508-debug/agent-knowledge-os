"""策略选择 API 测试。"""

import pytest
from fastapi.testclient import TestClient

from api.server import app
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


def test_analyze_accepts_explicit_strategy_selector():
    response = client.post(
        "/api/analyze",
        json={
            **payload(),
            "school": "classical",
            "policy": "classical_approx_v1",
            "version": "1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["strategy"]["context"] == {
        "school": "classical",
        "policy": "classical_approx_v1",
        "version": "1",
        "assumptions": ["按月柱顺逆推导", "起运年龄按三天一岁近似", "不计算精确起运时刻"],
    }
    assert "conflicts" in body
    assert "限制" in body["report"]
    assert body["metadata"]["strategy_selection"] == "explicit"


def test_analyze_rejects_unknown_strategy_without_fallback():
    response = client.post(
        "/api/analyze",
        json={**payload(), "school": "missing", "policy": "missing", "version": "1"},
    )

    assert response.status_code == 422
    assert "未找到策略" in response.json()["detail"]


def test_analyze_without_selector_returns_explainable_metadata():
    response = client.post("/api/analyze", json=payload())

    assert response.status_code == 200
    body = response.json()
    assert body["strategy"] is None
    assert body["analysis"] is None
    assert body["critique"] is None
    assert body["conflicts"] is None
    assert body["report"] is None
    assert body["metadata"]["strategy_selection"] == "required"
    assert "显式选择" in body["metadata"]["message"]
    assert body["metadata"]["facts"]


def test_service_without_selector_returns_only_chart_and_facts():
    service = MingLiService()
    response = service.analyze(
        {key: value for key, value in payload().items() if key != "question"},
        payload()["question"],
    )

    assert response.analysis is None
    assert response.critique is None
    assert response.strategy is None
    assert response.conflicts is None
    assert response.report is None
    assert response.metadata["facts"]


@pytest.mark.parametrize(
    ("school", "policy", "version"),
    [
        ("", "", ""),
        (" ", " ", " "),
        ("classical", None, "1"),
    ],
)
def test_analyze_rejects_empty_or_partial_selector(school, policy, version):
    response = client.post(
        "/api/analyze",
        json={**payload(), "school": school, "policy": policy, "version": version},
    )

    assert response.status_code == 422


def test_service_rejects_empty_selector():
    with pytest.raises(ValueError, match=r"不能为空|必须同时提供"):
        MingLiService().analyze(
            {key: value for key, value in payload().items() if key != "question"},
            payload()["question"],
            school="",
            policy="",
            version="",
        )


def test_service_rejects_whitespace_selector():
    with pytest.raises(ValueError, match=r"不能为空|必须同时提供"):
        MingLiService().analyze(
            {key: value for key, value in payload().items() if key != "question"},
            payload()["question"],
            school=" ",
            policy=" ",
            version=" ",
        )
