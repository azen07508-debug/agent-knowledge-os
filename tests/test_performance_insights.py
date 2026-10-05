"""Task 9：Performance Memory——三维度聚合、样本闸门、工具帖四要素。"""

import pytest

from runtime.analytics_store import AnalyticsStore
from runtime.memory_api import MemoryAPI
from runtime.performance_insights import build_insights, record_insight, tool_post_check
from runtime.post_analytics import PostAnalytics


def snap(post_id, content_id, content_type, rate=0.10, views=100, collected_at="2026-10-04 10:00:00"):
    return PostAnalytics(
        post_id=post_id,
        platform="x",
        content_id=content_id,
        content_type=content_type,
        metrics={"likes": round(views * rate), "views": views},
        collected_at=collected_at,
    )


def content(cid, title, hook="", content_type_topic="工具"):
    return {
        "id": cid,
        "topic": content_type_topic,
        "title_candidates": f'["{title}"]',
        "hook": hook,
        "core_content": "",
    }


def test_build_insights_aggregates_content_type_title_and_creator_reference(tmp_path):
    store = AnalyticsStore(tmp_path / "a.sqlite3")
    contents = []
    for index in range(3):
        cid = f"c{index}"
        store.record(snap(f"p{index}", cid, "tool_post"))
        contents.append(content(cid, f"{index + 1} 个工具解决重复劳动", hook="别再手抄了 @michael_liu"))

    insights = build_insights(store, contents)

    dims = {(i.dimension, i.key): i for i in insights}
    assert dims[("content_type", "tool_post")].samples == 3
    assert dims[("title_structure", "数字清单")].samples == 3
    assert dims[("creator_reference", "michael_liu")].samples == 3
    store.close()


def test_small_sample_group_stays_pending(tmp_path):
    store = AnalyticsStore(tmp_path / "a.sqlite3")
    store.record(snap("p0", "c0", "tool_post"))

    insights = build_insights(store, [content("c0", "为什么你总是手动重复？")])

    by_dim = {i.dimension: i for i in insights}
    assert by_dim["content_type"].status == "PENDING"
    assert by_dim["title_structure"].status == "PENDING"
    assert by_dim["content_type"].samples == 1
    store.close()


def test_sufficient_sample_candidate_still_never_touches_strategy(tmp_path):
    store = AnalyticsStore(tmp_path / "a.sqlite3")
    contents = []
    for index in range(3):
        cid = f"c{index}"
        store.record(snap(f"p{index}", cid, "tool_post"))
        contents.append(content(cid, "别再收藏工具了，这 3 个真正省时间"))
    memory = MemoryAPI(vault_path=tmp_path / "vault")

    candidate = next(i for i in build_insights(store, contents) if i.dimension == "content_type")
    assert candidate.status == "CANDIDATE"

    record = record_insight(candidate, memory)
    assert record["ok"] is True
    notes = memory.list_notes("insight")
    assert len(notes) == 1
    assert memory.get("strategy")["ok"] is False  # 候选洞察绝不写 Strategy
    store.close()


def test_pending_insight_cannot_enter_memory_review(tmp_path):
    store = AnalyticsStore(tmp_path / "a.sqlite3")
    store.record(snap("p0", "c0", "tool_post"))
    memory = MemoryAPI(vault_path=tmp_path / "vault")
    pending = build_insights(store, [content("c0", "标题")])[0]

    with pytest.raises(ValueError):
        record_insight(pending, memory)
    assert memory.list_notes("insight") == []
    store.close()


def test_tool_post_requires_pain_point_url_audience_and_caveats():
    empty = tool_post_check("一个很好的工具推荐")
    assert empty["ok"] is False
    assert set(empty["missing"]) == {"pain_point", "official_url", "audience", "caveats"}

    full = tool_post_check(
        "每天手抄数据很浪费时间。适合做日报的同学，注意免费版有条数限制。"
        "传送门：https://example.com/official"
    )
    assert full["ok"] is True
    assert full["missing"] == []
