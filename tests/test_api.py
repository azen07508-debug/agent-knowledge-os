"""FastAPI 接口测试。"""

from fastapi.testclient import TestClient

from api.server import app

client = TestClient(app)


def payload():
    return {"year": 1990, "month": 2, "day": 1, "hour": 12}


def test_health_reports_real_provider():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "sxtwl"}


def test_chart_endpoint_returns_structured_chart():
    response = client.post("/api/chart", json=payload())

    assert response.status_code == 200
    assert response.json()["provider"] == "sxtwl"
    assert len(response.json()["pillars"]) == 4


def test_analyze_endpoint_returns_evidence_and_critique():
    response = client.post("/api/analyze", json={**payload(), "question": "事业"})

    assert response.status_code == 200
    assert "evidence" in response.json()["analysis"]
    assert "critique" in response.json()


def test_api_rejects_invalid_birth_input():
    response = client.post("/api/chart", json={**payload(), "month": 13})

    assert response.status_code == 422
