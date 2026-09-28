"""Phase 12：Human Review 审核包 / 界面 / 审批动作。"""

import pytest

from runtime.content_object import ContentObject
from runtime.content_store import ContentStore
from runtime.human_review import approve, build_packet, render, request_changes
from runtime.research_store import ResearchItem, ResearchStore


def make_store(tmp_path) -> ContentStore:
    return ContentStore(tmp_path / "content.sqlite3")


def ready_object(**overrides) -> ContentObject:
    base = {
        "topic": "Obsidian 记忆分层",
        "angle": "冷暖热三层实测",
        "audience": "开发者",
        "sources": ["https://a.com/1"],
        "evidence": [{"url": "https://a.com/1", "quote": "热层 3 条规则"}],
        "claims": ["热层 3 条规则"],
        "hook": "你的笔记不是记忆",
        "core_content": "你的笔记不是记忆\n冷热三层，热层 3 条规则",
        "platform_versions": {"X": "Thread"},
        "ai_suggestions": ["有 1 条来源、1 条事实线索", "策略判断：与账号定位相关"],
        "status": "REVIEW",
    }
    base.update(overrides)
    return ContentObject(**base)


def test_packet_contains_all_review_sections(tmp_path):
    store = make_store(tmp_path)
    obj = ready_object()
    store.save(obj)
    research = ResearchStore(":memory:")
    research.save(ResearchItem(source="web", url="https://a.com/1", title="原始文章",
                               content="冷热三层，热层 3 条规则", topic="memory"))

    packet = build_packet(store, obj.id, research_store=research)

    for key in ("status", "research", "sources", "generated", "claims", "evidence",
                "ai_suggestions", "review_notes", "can_approve"):
        assert key in packet, key
    assert packet["can_approve"] is True
    assert packet["research"][0]["title"] == "原始文章"  # 原始研究来自 ResearchStore
    assert packet["generated"]["hook"] == "你的笔记不是记忆"
    assert packet["claims"] == ["热层 3 条规则"]
    assert packet["ai_suggestions"]


def test_packet_without_research_store_still_works(tmp_path):
    store = make_store(tmp_path)
    obj = ready_object()
    store.save(obj)

    packet = build_packet(store, obj.id)

    assert packet["research"] == []
    assert "不在 ResearchStore" in render(packet)


def test_render_lists_every_required_section(tmp_path):
    store = make_store(tmp_path)
    obj = ready_object()
    store.save(obj)

    text = render(build_packet(store, obj.id))

    for label in ("原始研究", "来源", "AI 生成内容", "Claims", "Evidence", "AI 建议", "修改记录"):
        assert label in text, label
    assert "你的笔记不是记忆" in text
    assert "热层 3 条规则" in text


def test_packet_for_missing_content_raises(tmp_path):
    store = make_store(tmp_path)

    with pytest.raises(FileNotFoundError):
        build_packet(store, "no-such-id")


# ── 审批动作 ────────────────────────────────────────────────────────────


def test_approve_moves_to_approved_and_records_reviewer(tmp_path):
    store = make_store(tmp_path)
    obj = ready_object()
    store.save(obj)

    result = approve(store, obj.id, reviewer="admin", note="核对过来源")

    assert result["ok"] is True and result["status"] == "APPROVED"
    saved = store.get(obj.id)
    assert saved.status == "APPROVED"
    assert saved.review_notes[-1]["action"] == "APPROVED"
    assert saved.review_notes[-1]["reviewer"] == "admin"
    assert saved.review_notes[-1]["note"] == "核对过来源"


def test_approve_only_allowed_in_review(tmp_path):
    store = make_store(tmp_path)
    obj = ready_object(status="IDEA")
    store.save(obj)

    with pytest.raises(ValueError, match="REVIEW"):
        approve(store, obj.id, reviewer="admin")


def test_request_changes_needs_reason_and_returns_to_draft(tmp_path):
    store = make_store(tmp_path)
    obj = ready_object()
    store.save(obj)

    with pytest.raises(ValueError, match="要改什么"):
        request_changes(store, obj.id, reviewer="admin", note="   ")

    result = request_changes(store, obj.id, reviewer="admin", note="Hook 太平，第二条补数据")

    assert result["status"] == "DRAFT"
    saved = store.get(obj.id)
    assert saved.status == "DRAFT"
    assert saved.review_notes[-1]["action"] == "CHANGES_REQUESTED"
    assert "Hook 太平" in saved.review_notes[-1]["note"]
