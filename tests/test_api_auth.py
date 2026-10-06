"""生产化：可选的 API key 鉴权。

设置 MINGLI_API_KEY 后，/api/*（健康检查除外）必须携带 X-API-Key；
未设置时保持本地开放模式，方便本机开发与自动化测试。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.server as server

client = TestClient(server.app)

BIRTH = {"year": 1990, "month": 2, "day": 1, "hour": 12}


def test_api_stays_open_when_no_key_is_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MINGLI_API_KEY", raising=False)

    assert client.get("/api/health").status_code == 200
    assert client.post("/api/chart", json=BIRTH).status_code == 200


def test_api_requires_header_once_key_is_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINGLI_API_KEY", "secret")

    missing = client.post("/api/chart", json=BIRTH)
    wrong = client.post("/api/chart", json=BIRTH, headers={"X-API-Key": "wrong"})
    correct = client.post("/api/chart", json=BIRTH, headers={"X-API-Key": "secret"})

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert correct.status_code == 200


def test_health_and_web_console_stay_open_for_probes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINGLI_API_KEY", "secret")

    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 200
