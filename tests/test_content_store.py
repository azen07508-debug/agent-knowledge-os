"""Phase 8：ContentStore 持久化与状态推进。"""

import pytest

from runtime.content_object import ContentObject, idea_from_recommendation
from runtime.content_store import ContentStore


def make(tmp_path, db_name="content.sqlite3") -> ContentStore:
    return ContentStore(tmp_path / db_name)


def ready_object(**overrides) -> ContentObject:
    base = {
        "topic": "Obsidian 记忆分层",
        "angle": "冷暖热三层实测",
        "audience": "开发者",
        "sources": ["https://a.com/1"],
        "evidence": [{"url": "https://a.com/1", "quote": "热层 3 条规则"}],
        "claims": ["热层 3 条规则"],
        "hook": "你的笔记不是记忆",
        "core_content": "三层结构的实测对比。",
        "platform_versions": {"X": "thread 内容"},
    }
    base.update(overrides)
    return ContentObject(**base)


def test_roundtrip_preserves_all_fields(tmp_path):
    store = make(tmp_path)
    obj = ready_object()
    store.save(obj)

    loaded = store.get(obj.id)

    assert loaded is not None
    assert loaded.to_dict() == obj.to_dict()
    assert loaded.platform_versions == {"X": "thread 内容"}
    store.close()


def test_save_is_upsert_by_id(tmp_path):
    store = make(tmp_path)
    obj = ready_object()

    first = store.save(obj)
    second = store.save(obj)

    assert first["created"] is True and second["created"] is False
    assert store.count() == 1
    store.close()


def test_list_filters_by_status_and_topic(tmp_path):
    store = make(tmp_path)
    store.save(ready_object(topic="记忆分层"))
    store.save(ready_object(topic="小红书排期"))
    store.save(ready_object(topic="记忆分层复盘"))

    assert len(store.list()) == 3
    assert len(store.list(topic="记忆分层")) == 2
    store.close()


def test_transition_persists_new_status(tmp_path):
    store = make(tmp_path)
    obj = ready_object()
    store.save(obj)

    result = store.transition(obj.id, "RESEARCHED")

    assert result == {"ok": True, "id": obj.id, "from": "IDEA", "to": "RESEARCHED"}
    assert store.get(obj.id).status == "RESEARCHED"
    store.close()


def test_illegal_transition_does_not_persist(tmp_path):
    store = make(tmp_path)
    obj = ready_object()
    store.save(obj)

    with pytest.raises(ValueError, match="状态机不允许"):
        store.transition(obj.id, "PUBLISHED")

    assert store.get(obj.id).status == "IDEA"
    store.close()


def test_transition_unknown_id_raises(tmp_path):
    store = make(tmp_path)

    with pytest.raises(FileNotFoundError):
        store.transition("no-such-id", "RESEARCHED")
    store.close()


def test_fill_persists_content_without_changing_status(tmp_path):
    store = make(tmp_path)
    obj = ready_object(hook="", core_content="")
    store.save(obj)

    store.fill(obj.id, {"hook": "你的笔记不是记忆", "core_content": "三层实测。"})

    loaded = store.get(obj.id)
    assert loaded.hook == "你的笔记不是记忆"
    assert loaded.status == "IDEA"
    store.close()


def test_fill_rejects_status_field(tmp_path):
    store = make(tmp_path)
    obj = ready_object()
    store.save(obj)

    with pytest.raises(ValueError, match="status"):
        store.fill(obj.id, {"status": "APPROVED"})
    store.close()


def test_pipeline_flow_from_idea_to_review(tmp_path):
    store = make(tmp_path)
    obj = idea_from_recommendation({
        "topic": "Obsidian 记忆分层",
        "angles": ["冷暖热三层实测"],
        "audience": "开发者",
        "sources": ["https://a.com/1"],
        "evidence": [{"url": "https://a.com/1", "quote": "热层"}],
        "facts": ["热层 3 条规则"],
    })
    store.save(obj)

    store.transition(obj.id, "RESEARCHED")
    store.fill(obj.id, {"hook": "你的笔记不是记忆", "core_content": "三层实测对比。"})
    store.transition(obj.id, "DRAFT")
    store.transition(obj.id, "REVIEW")

    counts = store.status_counts()
    assert counts["REVIEW"] == 1 and counts["IDEA"] == 0
    assert store.list(status="REVIEW")[0]["topic"] == "Obsidian 记忆分层"
    store.close()


def test_two_objects_have_distinct_ids(tmp_path):
    store = make(tmp_path)
    first = ready_object()
    second = ready_object()

    store.save_many([first, second])

    assert first.id != second.id
    assert store.count() == 2
    store.close()
