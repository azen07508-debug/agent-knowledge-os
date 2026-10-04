from runtime.aihot_bridge import import_selected_snapshot
from runtime.research_store import ResearchStore


def test_import_selected_snapshot_preserves_public_evidence():
    payload = {
        "asOf": "2026-10-03T10:00:00Z",
        "cursor": "c1",
        "items": [{
            "id": "a1",
            "title": "Agent 工具更新",
            "summary": "一个项目发布新的 Agent 工作流能力。",
            "reason": "有具体能力变化",
            "score": 85,
            "source": {"name": "Example"},
            "links": {"aihot": "http://localhost:3000/items/a1", "original": "https://example.com/a1"},
            "publishedAt": "2026-10-03T09:00:00Z",
            "attribution": {"name": "CreatorOS 热点"},
        }],
    }
    with ResearchStore(":memory:") as store:
        result = import_selected_snapshot(payload, store)
        item = store.get("https://example.com/a1")
    assert result["created"] == 1
    assert item is not None
    assert item["source"] == "Example"
    assert item["topic"] == "aihot-selected"
    assert item["engagement"]["aihot_score"] == 85
    assert '"aihot_url"' in item["evidence"]


def test_import_skips_items_without_any_public_url():
    with ResearchStore(":memory:") as store:
        result = import_selected_snapshot({"items": [{"title": "无链接"}]}, store)
    assert result["count"] == 0
    assert result["skipped"] == 1


def test_reimporting_same_snapshot_is_idempotent_and_tracks_cursor():
    payload = {"asOf": "2026-10-04T08:00:00Z", "cursor": "cursor-1", "items": [{
        "title": "重复材料", "summary": "摘要", "source": {"name": "S"},
        "links": {"original": "https://example.com/same"},
    }]}
    with ResearchStore(":memory:") as store:
        first = import_selected_snapshot(payload, store)
        second = import_selected_snapshot(payload, store)
        assert first["created"] == 1
        assert second["updated"] == 1
        assert second["count"] == 1
        assert second["cursor"] == "cursor-1"


def test_save_cursor_writes_only_local_sync_state(tmp_path):
    from runtime.aihot_bridge import save_cursor
    path = tmp_path / "cursor.json"
    save_cursor({"cursor": "c2", "asOf": "now", "items": []}, path)
    assert '"cursor": "c2"' in path.read_text(encoding="utf-8")
