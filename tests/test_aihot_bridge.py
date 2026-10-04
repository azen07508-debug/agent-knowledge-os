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
