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


def test_analyze_endpoint_returns_chart_and_facts_without_selector():
    response = client.post("/api/analyze", json={**payload(), "question": "事业"})

    assert response.status_code == 200
    body = response.json()
    assert body["analysis"] is None
    assert body["critique"] is None
    assert body["metadata"]["facts"]


def test_api_rejects_invalid_birth_input():
    response = client.post("/api/chart", json={**payload(), "month": 13})

    assert response.status_code == 422


def test_web_index_serves_single_page_console():
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    for endpoint in ("/api/chart", "/api/analyze", "/api/ziwei", "/api/windows"):
        assert endpoint in response.text
    assert "school" in response.text and "policy" in response.text



def test_oversized_birth_year_is_rejected_by_all_birth_endpoints():
    for year in (-10**30, 0, 10000, 10**30):
        invalid = {**payload(), "year": year}
        cases = (
            ("post", "/api/chart", invalid),
            ("post", "/api/analyze", {**invalid, "question": "事业"}),
            ("post", "/api/ziwei", invalid),
            ("post", "/api/windows", {**invalid, "target_year": 2024}),
            ("put", "/api/memory/audit-invalid", invalid),
        )
        for method, path, body in cases:
            assert getattr(client, method)(path, json=body).status_code == 422


def test_blank_questions_are_rejected_with_and_without_strategy():
    selector = {"school": "classical", "policy": "classical_approx_v1", "version": "1"}
    for question in ("", " ", "\t\n", "\u3000"):
        for strategy in ({}, selector):
            response = client.post("/api/analyze", json={
                **payload(), "question": question, **strategy,
            })
            assert response.status_code == 422
        # Validation must precede any attempt to load a stored profile.
        assert client.post("/api/memory/audit-invalid/analyze", json={
            "question": question,
        }).status_code == 422
