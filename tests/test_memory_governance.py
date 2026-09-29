"""Phase 3 治理：七字段元数据、状态机、置信度、Memory Health。"""

import re

import pytest

from runtime.creator_memory import CATEGORY_BY_KEY, confidence_level
from runtime.memory_api import MemoryAPI

ACCOUNT = {
    "账号定位": "AI 工具实测",
    "目标受众": "开发者",
    "内容领域": "开源项目",
    "内容支柱": "项目实测",
    "表达风格": "实测 > 空谈",
    "长期目标": "沉淀评测方法论",
    "禁止内容": "收益承诺",
    "平台差异": "X 走 Thread",
    "账号阶段": "冷启动",
}

DECISION = {"日期": "2026-09-28", "事项": "AI 标题", "决策": "不采用", "原因": "过度营销"}


def make_api(tmp_path) -> MemoryAPI:
    return MemoryAPI(vault_path=tmp_path)


def write_decisions(memory: MemoryAPI, count: int = 1, **overrides) -> list[str]:
    titles = []
    for index in range(count):
        memory.create(
            "decision",
            f"2026-09-28-决策-{index}",
            {**DECISION, "事项": overrides.get("事项", f"AI 标题{index}")},
            confidence=overrides.get("confidence"),
            source=overrides.get("source"),
            status=overrides.get("status", "active"),
        )
        titles.append(f"2026-09-28-决策-{index}")
    return titles


# ── 元数据：七字段齐备 ───────────────────────────────────────────────────


def test_frontmatter_carries_all_seven_governance_fields(tmp_path):
    memory = make_api(tmp_path)
    memory.create("decision", "2026-09-28-决策-AI 标题", DECISION, confidence="高", source="review-2026-09-28")

    frontmatter = memory.get("decision", "2026-09-28-决策-AI 标题")["frontmatter"]

    for field in ("type", "status", "created", "updated", "confidence", "source"):
        assert field in frontmatter, field
    assert frontmatter["type"] == "decision"
    assert frontmatter["status"] == "active"
    assert frontmatter["confidence"] == "HIGH"
    assert frontmatter["source"] == "review-2026-09-28"


def test_unspecified_metadata_defaults_to_unknown_source_and_medium(tmp_path):
    memory = make_api(tmp_path)
    memory.create("decision", "2026-09-28-决策-AI 标题", DECISION)

    frontmatter = memory.get("decision", "2026-09-28-决策-AI 标题")["frontmatter"]

    assert frontmatter["confidence"] == "MEDIUM"
    assert frontmatter["source"] == "unknown"  # 未标注来源要能被 health 查出来


def test_invalid_status_and_confidence_are_rejected(tmp_path):
    memory = make_api(tmp_path)

    with pytest.raises(ValueError, match="记忆状态只能是"):
        memory.create("decision", "2026-09-28-决策-AI 标题", DECISION, status="draft")
    with pytest.raises(ValueError, match="置信度只能是"):
        memory.create("decision", "2026-09-28-决策-AI 标题", DECISION, confidence="非常高")
    with pytest.raises(ValueError, match="置信度只能是"):
        confidence_level("信心十足")


def test_chinese_confidence_maps_to_frontmatter_level(tmp_path):
    memory = make_api(tmp_path)
    record = memory.recordHypothesis(hypothesis="X Thread 更适合项目拆解")

    frontmatter = memory.get("experiment", record["title"])["frontmatter"]
    assert frontmatter["confidence"] == "LOW"  # 正文仍写「低」，frontmatter 用规格枚举


def test_strategy_state_maps_to_confidence(tmp_path):
    memory = make_api(tmp_path)
    memory.layer.save_strategy("项目拆解", ["开源项目"], "开发者", state="已确认")

    assert memory.get("strategy")["frontmatter"]["confidence"] == "HIGH"

    memory.layer.save_strategy("项目拆解", ["开源项目"], "开发者", state="假设")
    assert memory.get("strategy")["frontmatter"]["confidence"] == "LOW"


# ── 状态机：ACTIVE / PENDING / ARCHIVED / SUPERSEDED ────────────────────


def test_insight_and_analytics_start_pending_until_reviewed(tmp_path):
    memory = make_api(tmp_path)

    observation = memory.recordObservation(topic="内容类型", observation="新闻类互动低", evidence="两条对比")
    validated = memory.recordInsight(topic="内容类型", insight="项目拆解更合适", evidence="多条对比")
    memory.layer.save_analytics(observation="o", candidate_insight="c", sample_size=30)

    assert memory.get("insight", observation["title"])["frontmatter"]["status"] == "pending"
    assert memory.get("insight", validated["title"])["frontmatter"]["status"] == "active"
    analytics_title = memory.layer.list_notes("analytics")[0].rsplit("/", 1)[-1].removesuffix(".md")
    assert memory.get("analytics", analytics_title)["frontmatter"]["status"] == "pending"


def test_review_approval_promotes_pending_to_active(tmp_path):
    memory = make_api(tmp_path)
    memory.layer.save_analytics(observation="o", candidate_insight="c", sample_size=30)
    title = memory.layer.list_notes("analytics")[0].rsplit("/", 1)[-1].removesuffix(".md")

    record = memory.review("analytics", title, approved=True, reason="样本量达标，采纳")

    assert record["ok"] is True
    found = memory.get("analytics", title)
    assert found["frontmatter"]["status"] == "active"
    assert found["sections"]["复核意见"] == "样本量达标，采纳"


def test_review_rejection_archives_the_note(tmp_path):
    memory = make_api(tmp_path)
    memory.layer.save_analytics(observation="o", candidate_insight="c", sample_size=3)
    title = memory.layer.list_notes("analytics")[0].rsplit("/", 1)[-1].removesuffix(".md")

    memory.review("analytics", title, approved=False, reason="样本量不足")

    assert memory.get("analytics", title)["ok"] is False
    archived = tmp_path / "99-Archive" / "14-Analytics" / f"{title}.md"
    assert archived.exists()
    assert "status: archived" in archived.read_text(encoding="utf-8")
    assert "样本量不足" in archived.read_text(encoding="utf-8")


def test_review_rejection_handles_titles_with_unsafe_characters(tmp_path):
    """回归：标题含 `:`（Phase 17 主题命名 content_type:thread）时，驳回复核不能找不到文件。"""
    memory = make_api(tmp_path)
    record = memory.recordObservation(topic="content_type:thread",
                                      observation="thread 互动更高", evidence="3 条对比")
    title = record["title"]
    source = memory.layer.exporter.note_path(CATEGORY_BY_KEY["insight"].folder, title)
    assert source.exists()                                   # 写入时 `:` 已被换成 `-`

    memory.review("insight", title, approved=False, reason="样本不足")

    assert memory.get("insight", title)["ok"] is False
    archived = tmp_path / "99-Archive" / source.parent.name / source.name
    assert archived.exists()
    assert "status: archived" in archived.read_text(encoding="utf-8")


def test_supersede_marks_note_and_requires_reason(tmp_path):
    memory = make_api(tmp_path)
    memory.create("decision", "2026-09-28-决策-AI 标题", DECISION, source="review")

    with pytest.raises(ValueError, match="必须写明原因"):
        memory.supersede("decision", "2026-09-28-决策-AI 标题", "  ")

    memory.supersede("decision", "2026-09-28-决策-AI 标题", reason="已由 09-29 决策取代")
    found = memory.get("decision", "2026-09-28-决策-AI 标题")

    assert found["frontmatter"]["status"] == "superseded"
    assert found["sections"]["取代原因"] == "已由 09-29 决策取代"
    assert found["frontmatter"]["source"] == "review"  # 状态变化不丢元数据


def test_archive_sets_archived_status(tmp_path):
    memory = make_api(tmp_path)
    memory.create("decision", "2026-09-28-决策-AI 标题", DECISION, source="review")
    memory.archive("decision", "2026-09-28-决策-AI 标题")

    archived = (tmp_path / "99-Archive" / "15-Decisions" / "2026-09-28-决策-AI 标题.md").read_text(encoding="utf-8")
    assert "status: archived" in archived
    assert "source: review" in archived


def test_update_preserves_governance_fields_unless_overridden(tmp_path):
    memory = make_api(tmp_path)
    memory.create("decision", "2026-09-28-决策-AI 标题", DECISION, confidence="高", source="review")
    path = tmp_path / "15-Decisions" / "2026-09-28-决策-AI 标题.md"
    path.write_text(
        re.sub(r"created: .*", "created: 2020-01-01 00:00:00", path.read_text(encoding="utf-8"), count=1),
        encoding="utf-8",
    )

    memory.update("decision", "2026-09-28-决策-AI 标题", {"决策": "改为采用"})
    found = memory.get("decision", "2026-09-28-决策-AI 标题")

    assert found["frontmatter"]["created"] == "2020-01-01 00:00:00"
    assert found["frontmatter"]["confidence"] == "HIGH"
    assert found["frontmatter"]["source"] == "review"

    memory.update("decision", "2026-09-28-决策-AI 标题", {}, status="pending", confidence="低")
    relinked = memory.get("decision", "2026-09-28-决策-AI 标题")["frontmatter"]
    assert relinked["status"] == "pending"
    assert relinked["confidence"] == "LOW"


def test_update_in_place_does_not_create_hashed_copy(tmp_path):
    memory = make_api(tmp_path)
    memory.create("decision", "2026-09-28-决策-AI 标题", DECISION)
    memory.update("decision", "2026-09-28-决策-AI 标题", {"决策": "改为采用"})

    assert memory.layer.list_notes("decision") == ["15-Decisions/2026-09-28-决策-AI 标题.md"]


# ── Memory Health ───────────────────────────────────────────────────────


def test_health_is_clean_on_governed_vault(tmp_path):
    memory = make_api(tmp_path)
    write_decisions(memory, source="review", confidence="中")

    report = memory.health()

    assert report["ok"] is True
    assert report["checked"] == 1
    assert all(count == 0 for count in report["summary"].values()), report["summary"]


def test_health_flags_missing_source_and_low_confidence(tmp_path):
    memory = make_api(tmp_path)
    write_decisions(memory, count=2, confidence="低")  # source 缺省 unknown

    report = memory.health()

    assert len(report["issues"]["no_source"]) == 2
    assert len(report["issues"]["low_confidence"]) == 2


def test_health_flags_duplicate_notes_with_same_content(tmp_path):
    memory = make_api(tmp_path)
    memory.create("decision", "2026-09-28-决策-AI 标题", DECISION, source="review", confidence="中")
    memory.create("decision", "另一个标题", DECISION, source="review", confidence="中")

    report = memory.health()

    assert len(report["issues"]["duplicate"]) == 1
    assert len(report["issues"]["duplicate"][0]["paths"]) == 2


def test_health_flags_conflicting_insights_on_same_topic(tmp_path):
    memory = make_api(tmp_path)
    memory.recordInsight(topic="内容类型", insight="项目拆解最合适", evidence="a", source="analytics-1")
    memory.recordInsight(topic="内容类型", insight="新闻最合适", evidence="b", source="analytics-2")

    report = memory.health()

    conflicts = report["issues"]["conflict"]
    assert len(conflicts) == 1
    assert conflicts[0]["topic"] == "主题:内容类型"
    assert len(conflicts[0]["paths"]) == 2


def test_health_flags_stale_and_invalid_metadata(tmp_path):
    memory = make_api(tmp_path)
    write_decisions(memory, count=2, source="review", confidence="中")
    folder = tmp_path / "15-Decisions"
    (folder / "2026-09-28-决策-0.md").write_text(
        re.sub(r"updated: .*", "updated: 2025-01-01 00:00:00", (folder / "2026-09-28-决策-0.md").read_text(encoding="utf-8"), count=1),
        encoding="utf-8",
    )
    (folder / "2026-09-28-决策-1.md").write_text(
        re.sub(r"status: .*", "status: draft", (folder / "2026-09-28-决策-1.md").read_text(encoding="utf-8"), count=1),
        encoding="utf-8",
    )

    report = memory.health(stale_days=30)

    assert len(report["issues"]["stale"]) == 1
    assert report["issues"]["stale"][0]["days"] > 30
    assert len(report["issues"]["invalid_metadata"]) == 1
    assert report["issues"]["invalid_metadata"][0]["status"] == "draft"


def test_health_skips_archived_notes(tmp_path):
    memory = make_api(tmp_path)
    write_decisions(memory, count=1, confidence="低")  # 无来源 + 低置信度
    memory.archive("decision", "2026-09-28-决策-0")

    report = memory.health()

    assert report["checked"] == 0
    assert all(count == 0 for count in report["summary"].values())


def test_account_and_strategy_survive_health_scan(tmp_path):
    memory = make_api(tmp_path)
    memory.create("account", "账号画像", ACCOUNT, source="founder")
    memory.layer.save_strategy("项目拆解", ["开源项目"], "开发者", state="已确认", source="founder")

    report = memory.health()

    assert report["checked"] == 2
    assert report["summary"]["no_source"] == 0
    assert report["summary"]["conflict"] == 0  # 固定单篇不参与冲突分组
