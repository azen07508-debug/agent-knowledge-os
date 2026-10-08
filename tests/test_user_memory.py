"""用户记忆测试：档案存取、咨询历史、按记忆分析，以及对应 API。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.server as server
from runtime.mingli_service import MingLiService
from runtime.user_memory import MAX_HISTORY, UserMemory

client = TestClient(server.app)

BIRTH = {"year": 1990, "month": 2, "day": 1, "hour": 12, "gender": "男"}


@pytest.fixture
def memory(tmp_path: Path):
    path = tmp_path / "memory.json"
    previous = server.service.memory
    server.service.memory = UserMemory(path)
    yield path
    server.service.memory = previous


def test_profile_round_trips_through_local_file(tmp_path: Path):
    store = UserMemory(tmp_path / "memory.json")

    store.save_profile("user-1", {"birth": BIRTH, "school": "classical"})
    loaded = store.profile("user-1")

    assert loaded == {"birth": BIRTH, "school": "classical"}
    assert store.profile("nobody") is None
    assert (tmp_path / "memory.json").exists()


def test_history_is_newest_first_and_capped(tmp_path: Path):
    store = UserMemory(tmp_path / "memory.json")

    for index in range(MAX_HISTORY + 5):
        store.record("user-1", {"question": f"q{index}"})

    history = store.history("user-1")

    assert len(history) == MAX_HISTORY
    assert history[0]["question"] == f"q{MAX_HISTORY + 4}"
    assert store.history("nobody") == []


def test_service_rejects_partial_selector_when_saving_profile(tmp_path: Path):
    service = MingLiService(memory=UserMemory(tmp_path / "memory.json"))

    with pytest.raises(ValueError, match="school"):
        service.save_profile("user-1", BIRTH, school="classical")


def test_analyze_from_memory_uses_stored_birth(tmp_path: Path):
    service = MingLiService(memory=UserMemory(tmp_path / "memory.json"))
    service.save_profile("user-1", BIRTH)

    response = service.analyze_from_memory("user-1", "事业")
    history = service.memory.history("user-1")

    assert len(response.chart["pillars"]) == 4
    assert history[0]["question"] == "事业"
    assert history[0]["strategy"] is None


def test_analyze_from_memory_requires_a_saved_profile(tmp_path: Path):
    service = MingLiService(memory=UserMemory(tmp_path / "memory.json"))

    with pytest.raises(ValueError, match="没有找到"):
        service.analyze_from_memory("nobody", "事业")


def test_api_saves_profile_and_recalls_history(memory: Path):
    saved = client.put(
        "/api/memory/user-1",
        json={**BIRTH, "school": "classical", "policy": "classical_approx_v1", "version": "1"},
    )
    assert saved.status_code == 200
    assert saved.json()["profile"]["birth"]["year"] == 1990

    asked = client.post("/api/memory/user-1/analyze", json={"question": "事业"})
    assert asked.status_code == 200
    assert len(asked.json()["chart"]["pillars"]) == 4

    recalled = client.get("/api/memory/user-1")
    assert recalled.status_code == 200
    body = recalled.json()
    assert body["profile"]["school"] == "classical"
    assert [entry["question"] for entry in body["history"]] == ["事业"]


def test_api_rejects_unknown_user_and_partial_selector(memory: Path):
    assert client.get("/api/memory/nobody").status_code == 404
    assert client.post("/api/memory/nobody/analyze", json={"question": "事业"}).status_code == 404
    rejected = client.put("/api/memory/user-1", json={**BIRTH, "school": "classical"})
    assert rejected.status_code == 422
    assert client.put("/api/memory/user-1", json={**BIRTH, "month": 13}).status_code == 422


@pytest.mark.parametrize("question", ["", " ", "\t\n", "\u3000"])
def test_api_rejects_blank_question_without_recording_history(memory: Path, question):
    saved = client.put("/api/memory/user-1", json=BIRTH)
    assert saved.status_code == 200
    before = memory.read_bytes()

    response = client.post("/api/memory/user-1/analyze", json={"question": question})

    assert response.status_code == 422
    assert memory.read_bytes() == before
