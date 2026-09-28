"""Phase 4：ResearchItem 结构化存储（原始材料进数据库，不进记忆）。"""

import pytest

from runtime.research_store import CONTENT_CHARS, ResearchItem, ResearchStore


def make_store(tmp_path, name="research.sqlite3") -> ResearchStore:
    return ResearchStore(tmp_path / name)


def test_save_returns_created_then_updates_on_same_url(tmp_path):
    store = make_store(tmp_path)

    first = store.save(ResearchItem(source="web", url="https://a.com/x", title="旧标题", content="旧材料"))
    second = store.save(ResearchItem(source="web", url="https://a.com/x", title="新标题", content="新材料"))

    assert first["created"] is True
    assert second["created"] is False
    assert store.count() == 1
    assert store.get("https://a.com/x")["title"] == "新标题"
    assert store.get("https://a.com/x")["content"] == "新材料"


def test_save_requires_url(tmp_path):
    with pytest.raises(ValueError, match="必须有来源 URL"):
        make_store(tmp_path).save(ResearchItem(source="web", url="  "))


def test_item_content_is_truncated_not_fulltext(tmp_path):
    store = make_store(tmp_path)
    store.save(ResearchItem(source="web", url="https://a.com/x", content="长" * 5000))

    item = store.get("https://a.com/x")
    assert len(item["content"]) == CONTENT_CHARS + 1
    assert item["content"].endswith("…")


def test_get_by_id_and_missing_returns_none(tmp_path):
    store = make_store(tmp_path)
    store.save(ResearchItem(source="github", url="https://github.com/owner/repo"))

    assert store.get(store.get("https://github.com/owner/repo")["id"])["url"] == "https://github.com/owner/repo"
    assert store.get("https://nothing.example") is None


def test_search_by_keyword_and_topic(tmp_path):
    store = make_store(tmp_path)
    store.save(ResearchItem(source="web", url="https://a.com/1", title="记忆分层", topic="memory", content="冷暖热三层"))
    store.save(ResearchItem(source="web", url="https://a.com/2", title="发布排期", topic="publish", content="队列"))
    store.save(ResearchItem(source="web", url="https://a.com/3", title="记忆检索", topic="memory", content="混合检索"))

    by_keyword = store.search("记忆")
    by_topic = store.search(topic="memory")
    both = store.search("检索", topic="memory")

    assert [item["url"] for item in by_keyword] == ["https://a.com/3", "https://a.com/1"]
    assert len(by_topic) == 2
    assert [item["url"] for item in both] == ["https://a.com/3"]


def test_save_many_reports_created_and_updated(tmp_path):
    store = make_store(tmp_path)
    store.save(ResearchItem(source="web", url="https://a.com/1"))

    result = store.save_many(
        [
            ResearchItem(source="web", url="https://a.com/1"),
            ResearchItem(source="web", url="https://a.com/2"),
        ]
    )

    assert result == {"ok": True, "created": 1, "updated": 1, "count": 2}


def test_persists_across_instances(tmp_path):
    db = tmp_path / "research.sqlite3"
    ResearchStore(db).save(ResearchItem(source="web", url="https://a.com/1", title="留存"))

    assert ResearchStore(db).get("https://a.com/1")["title"] == "留存"


def test_memory_database_needs_no_files(tmp_path):
    store = ResearchStore(":memory:")
    store.save(ResearchItem(source="web", url="https://a.com/1"))

    assert store.count() == 1
    store.close()
