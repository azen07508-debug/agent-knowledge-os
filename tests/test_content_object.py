"""Phase 8：ContentObject 字段与状态机。"""

import pytest

from runtime.content_object import (
    ContentObject,
    idea_from_recommendation,
)

PLAN_FIELDS = (
    "topic", "title_candidates", "evidence_status", "content_source", "angle", "audience", "sources", "evidence", "claims",
    "hook", "core_content", "media", "platform_versions", "status",
)


def ready_object(**overrides) -> ContentObject:
    """一个各字段齐备、可以一路推进到发布的内容对象。"""
    base = {
        "topic": "Obsidian 记忆分层",
        "title_candidates": ["标题一", "标题二"],
        "evidence_status": "SELF_TESTED",
        "content_source": "项目实测",
        "angle": "冷暖热三层实测",
        "audience": "开发者",
        "sources": ["https://a.com/1"],
        "evidence": [{"url": "https://a.com/1", "quote": "热层 3 条规则"}],
        "claims": ["热层 3 条规则"],
        "hook": "你的笔记不是记忆",
        "core_content": "三层结构的实测对比。",
        "media": [],
        "platform_versions": {"X": "thread 内容"},
    }
    base.update(overrides)
    return ContentObject(**base)


# ── 字段 ────────────────────────────────────────────────────────────────


def test_object_covers_all_plan_fields():
    data = ready_object().to_dict()

    for name in PLAN_FIELDS:
        assert name in data, name


def test_defaults_are_idea_with_identity():
    obj = ContentObject(topic="选题")

    assert obj.status == "IDEA"
    assert obj.id and len(obj.id) == 12
    assert obj.created_at and obj.updated_at


def test_topic_is_required():
    with pytest.raises(ValueError, match="topic"):
        ContentObject(topic="  ")


def test_illegal_status_rejected():
    with pytest.raises(ValueError, match="非法状态"):
        ContentObject(topic="选题", status="LIVE")


def test_evidence_status_is_explicit():
    with pytest.raises(ValueError, match="非法证据状态"):
        ContentObject(topic="选题", evidence_status="GUESS")


# ── 状态机 ──────────────────────────────────────────────────────────────


def test_full_lifecycle_is_allowed():
    obj = ready_object()

    for target in ("RESEARCHED", "DRAFT", "REVIEW", "APPROVED", "SCHEDULED", "PUBLISHED", "ARCHIVED"):
        obj.transition(target)
        assert obj.status == target


def test_skipping_stages_is_rejected():
    obj = ready_object()

    with pytest.raises(ValueError, match="状态机不允许"):
        obj.transition("PUBLISHED")
    assert obj.status == "IDEA"  # 失败的转换不改变状态


def test_archived_is_terminal():
    obj = ready_object()
    obj.transition("ARCHIVED")

    assert obj.allowed_transitions() == ()
    with pytest.raises(ValueError, match="终态"):
        obj.transition("IDEA")


def test_researched_requires_sources_and_evidence():
    obj = ContentObject(topic="选题", sources=[], evidence=[])

    with pytest.raises(ValueError, match="来源"):
        obj.transition("RESEARCHED")
    assert obj.status == "IDEA"


def test_draft_requires_hook_and_core_content():
    obj = ContentObject(topic="选题", sources=["https://a.com/1"], evidence=[{"url": "u", "quote": "q"}])
    obj.transition("RESEARCHED")

    with pytest.raises(ValueError, match="Hook"):
        obj.transition("DRAFT")


def test_review_accepts_empty_claims():
    """空断言清单 = 无可核查项，观点型内容也该能进人审（真实材料常抽不出事实线索）。"""
    obj = ready_object(claims=[])
    obj.transition("RESEARCHED")
    obj.transition("DRAFT")

    obj.transition("REVIEW")

    assert obj.status == "REVIEW"


def test_scheduled_requires_platform_versions():
    obj = ready_object(platform_versions={})
    obj.transition("RESEARCHED")
    obj.transition("DRAFT")
    obj.transition("REVIEW")
    obj.transition("APPROVED")

    with pytest.raises(ValueError, match="平台版本"):
        obj.transition("SCHEDULED")


def test_transition_to_current_status_is_noop():
    obj = ready_object()

    obj.transition("IDEA")

    assert obj.status == "IDEA"


# ── 字段更新 ────────────────────────────────────────────────────────────


def test_fill_updates_content_but_not_status():
    obj = ready_object()

    obj.fill({"hook": "新钩子"})

    assert obj.hook == "新钩子"
    assert obj.status == "IDEA"


def test_fill_cannot_change_status():
    obj = ready_object()

    with pytest.raises(ValueError, match="status"):
        obj.fill({"status": "APPROVED"})


def test_evidence_status_requires_explicit_verification():
    obj = ready_object(evidence_status="PUBLIC_SOURCES")
    with pytest.raises(ValueError, match="不可更新"):
        obj.fill({"evidence_status": "SELF_TESTED"})
    with pytest.raises(ValueError, match="reviewer"):
        obj.mark_evidence_verified("SELF_TESTED", "")
    obj.mark_evidence_verified("SELF_TESTED", "reviewer", "本地跑通")
    assert obj.evidence_status == "SELF_TESTED"


# ── 从选题推荐落地 IDEA ─────────────────────────────────────────────────


def test_idea_from_recommendation_maps_phase6_fields():
    recommendation = {
        "topic": "Obsidian 记忆分层",
        "angles": ["冷暖热三层实测", "方案对比"],
        "audience": "开发者",
        "sources": ["https://a.com/1"],
        "evidence": [{"url": "https://a.com/1", "quote": "热层"}],
        "facts": ["热层 3 条规则"],
    }

    obj = idea_from_recommendation(recommendation)

    assert obj.status == "IDEA"
    assert obj.topic == "Obsidian 记忆分层"
    assert obj.angle == "冷暖热三层实测"  # 取第一个角度
    assert obj.audience == "开发者"
    assert obj.sources == ["https://a.com/1"]
    assert obj.evidence == [{"url": "https://a.com/1", "quote": "热层"}]
    assert obj.claims == ["热层 3 条规则"]  # 事实线索 -> 待核查断言，等 REVIEW 核对


def test_idea_from_recommendation_keeps_titles_and_evidence_status():
    obj = idea_from_recommendation({
        "topic": "Goose",
        "title_candidates": ["标题 A", "标题 B"],
        "evidence_status": "PUBLIC_SOURCES",
        "content_source": "公开资料观察，未实测",
    })
    assert obj.title_candidates == ["标题 A", "标题 B"]
    assert obj.evidence_status == "PUBLIC_SOURCES"
    assert obj.content_source == "公开资料观察，未实测"


def test_idea_falls_back_to_brief_when_audience_unknown():
    recommendation = {"topic": "t", "angles": ["a"], "audience": "UNKNOWN"}
    brief = {"answer": ["账号定位「AI 工具实测」，受众「开发者」。"]}

    obj = idea_from_recommendation(recommendation, brief)

    assert "AI 工具实测" in obj.audience
