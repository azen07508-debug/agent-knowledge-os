"""FastAPI 接口测试。"""

import pytest
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


@pytest.mark.parametrize("asset,content_type", [
    ("app.css", "text/css"),
    ("daily-glow.webp", "image/webp"),
    ("bamboo.webp", "image/webp"),
    ("horse.webp", "image/webp"),
    ("icons/calendar-blank.svg", "image/svg+xml"),
    ("fonts/paper-serif.otf", "font/otf"),
])
def test_ui_assets_remain_accessible_with_api_auth_enabled(monkeypatch, asset, content_type):
    monkeypatch.setenv("MINGLI_API_KEY", "test-only-key")
    response = client.get("/assets/" + asset)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(content_type)
    assert response.content
    assert client.post("/api/chart", json=payload()).status_code == 401


def test_static_mount_cannot_serve_repository_files():
    assert client.get("/assets/%2e%2e/%2e%2e/api/server.py").status_code == 404


@pytest.mark.parametrize("year", [-10**30, 0, 10000, 10**30])
@pytest.mark.parametrize("method,path,extra", [
    ("post", "/api/chart", {}),
    ("post", "/api/analyze", {"question": "事业"}),
    ("post", "/api/ziwei", {}),
    ("post", "/api/windows", {"target_year": 2024}),
    ("put", "/api/memory/invalid-year", {}),
])
def test_out_of_range_birth_year_returns_422(year, method, path, extra):
    response = getattr(client, method)(path, json={**payload(), **extra, "year": year})

    assert response.status_code == 422


@pytest.mark.parametrize("question", ["", " ", "\t\n", "\u3000"])
@pytest.mark.parametrize("explicit", [False, True])
def test_analyze_rejects_blank_questions(question, explicit):
    selector = {"school": "classical", "policy": "classical_approx_v1", "version": "1"}
    response = client.post("/api/analyze", json={
        **payload(), "gender": "男", "question": question, **(selector if explicit else {}),
    })

    assert response.status_code == 422


@pytest.mark.parametrize("question", ["", " ", "\t\n", "\u3000"])
def test_memory_analyze_rejects_blank_questions_before_profile_lookup(question):
    response = client.post("/api/memory/missing-blank-question/analyze", json={"question": question})

    assert response.status_code == 422
