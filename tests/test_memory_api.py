import re

import pytest

from runtime.memory_api import MemoryAPI
from runtime.obsidian_exporter import parse_note

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


def make_api(tmp_path) -> MemoryAPI:
    return MemoryAPI(vault_path=tmp_path)


# ── create / get ─────────────────────────────────────────────────────────


def test_create_then_get_returns_sections(tmp_path):
    memory = make_api(tmp_path)
    memory.create(
        "decision",
        "2026-09-28-决策-AI 标题",
        {"日期": "2026-09-28", "事项": "AI 标题", "决策": "不采用", "原因": "过度营销"},
    )

    found = memory.get("decision", "2026-09-28-决策-AI 标题")

    assert found["ok"] is True
    assert found["sections"]["决策"] == "不采用"
    assert found["frontmatter"]["type"] == "decision"
    assert found["frontmatter"]["status"] == "active"
    assert found["frontmatter"]["confidence"] == "MEDIUM"
    assert found["frontmatter"]["source"] == "unknown"
    assert found["frontmatter"]["tags"] == ["decision"]
    assert found["path"].startswith("15-Decisions/")


def test_get_missing_note_returns_not_ok(tmp_path):
    result = make_api(tmp_path).get("decision", "不存在")

    assert result["ok"] is False
    assert "记忆不存在" in result["message"]


def test_get_fixed_title_does_not_need_title(tmp_path):
    memory = make_api(tmp_path)
    memory.create("account", "账号画像", ACCOUNT)

    assert memory.get("account")["ok"] is True
    with pytest.raises(ValueError, match="必须提供 title"):
        memory.get("insight")


def test_create_unknown_category_raises(tmp_path):
    with pytest.raises(ValueError, match="未知记忆类别"):
        make_api(tmp_path).create("spam", "t", {"a": "b"})


def test_create_account_twice_requires_update(tmp_path):
    memory = make_api(tmp_path)
    memory.create("account", "账号画像", ACCOUNT)

    with pytest.raises(ValueError, match="必须提供 reason"):
        memory.create("account", "账号画像", ACCOUNT)


# ── update ──────────────────────────────────────────────────────────────


def test_update_merges_and_keeps_created(tmp_path):
    memory = make_api(tmp_path)
    memory.create("strategy", "当前内容策略", {"当前内容策略": "旧策略", "内容支柱": "p", "目标方向": "d", "状态": "已观察", "策略变更原因": "首次"})

    path = tmp_path / "10-Strategy" / "当前内容策略.md"
    original = path.read_text(encoding="utf-8")
    path.write_text(
        re.sub(r"created: .*", "created: 2020-01-01 00:00:00", original, count=1),
        encoding="utf-8",
    )

    record = memory.update("strategy", "当前内容策略", {"当前内容策略": "新策略", "状态": "已确认"})
    found = memory.get("strategy")

    assert record["ok"] is True
    assert found["sections"]["当前内容策略"] == "新策略"
    assert found["sections"]["状态"] == "已确认"
    assert found["sections"]["目标方向"] == "d"  # 未提及的字段保留
    assert found["frontmatter"]["created"] == "2020-01-01 00:00:00"


def test_update_missing_note_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        make_api(tmp_path).update("strategy", "当前内容策略", {"当前内容策略": "x"})


def test_update_account_requires_reason_and_writes_decision(tmp_path):
    memory = make_api(tmp_path)
    memory.create("account", "账号画像", ACCOUNT)

    with pytest.raises(ValueError, match="必须提供 reason"):
        memory.update("account", None, {**ACCOUNT, "账号定位": "新定位"})

    record = memory.update("account", None, {**ACCOUNT, "账号定位": "新定位"}, reason="受众反馈")
    assert record["decision"]["category"] == "decision"
    assert len(memory.layer.list_notes("decision")) == 1


# ── search / archive ────────────────────────────────────────────────────


def test_search_without_category_uses_full_vault(tmp_path):
    memory = make_api(tmp_path)
    memory.create("research", "研究-Agent-Reach", {"主题": "Agent-Reach", "关键结论": "- 多后端路由", "重要来源": "- github", "研究时间": "2026-09-28"})
    result = memory.search("多后端路由")

    assert result["source"] == "obsidian"
    assert result["matches"][0]["path"].startswith("11-Research/")


def test_search_with_category_only_scans_that_folder(tmp_path):
    memory = make_api(tmp_path)
    memory.create("research", "研究-Agent-Reach", {"主题": "Agent-Reach", "关键结论": "- 多后端路由", "重要来源": "- github", "研究时间": "2026-09-28"})
    memory.create("agent", "2026-09-28-Content Agent-经验", {"Agent": "Content Agent", "经验": "多后端路由类选题容易写虚", "证据": "-", "记录时间": "2026-09-28"})

    scoped = memory.search("多后端路由", category="agent")

    assert scoped["source"] == "obsidian"
    assert scoped["category"] == "agent"
    assert all(match["path"].startswith("16-Agent/") for match in scoped["matches"])


def test_archive_then_get_fails(tmp_path):
    memory = make_api(tmp_path)
    memory.create("agent", "2026-09-28-X Agent-经验", {"Agent": "X Agent", "经验": "前两条密度决定读完率", "证据": "-", "记录时间": "2026-09-28"})
    memory.archive("agent", "2026-09-28-X Agent-经验")

    assert memory.get("agent", "2026-09-28-X Agent-经验")["ok"] is False
    assert (tmp_path / "99-Archive" / "16-Agent" / "2026-09-28-X Agent-经验.md").exists()


# ── 领域记录方法 ─────────────────────────────────────────────────────────


def test_record_observation_and_insight_land_in_insights(tmp_path):
    memory = make_api(tmp_path)

    obs = memory.recordObservation(topic="内容类型", observation="新闻类互动低", evidence="两条对比")
    ins = memory.recordInsight(topic="内容类型", insight="项目拆解更合适", evidence="多条对比", confidence="中")

    assert obs["title"].startswith("2026-") and "-观察-" in obs["title"]
    assert ins["title"].startswith("2026-") and "-洞察-" in ins["title"]
    assert memory.get("insight", obs["title"])["sections"]["状态"] == "观察"
    assert memory.get("insight", ins["title"])["sections"]["状态"] == "已验证"
    assert len(memory.layer.list_notes("insight")) == 2


def test_record_hypothesis_becomes_pending_experiment(tmp_path):
    memory = make_api(tmp_path)

    record = memory.recordHypothesis(
        hypothesis="X Thread 比单帖更适合项目拆解",
        expected="互动率更高",
    )

    assert record["title"] == "Experiment-001"
    sections = memory.get("experiment", "Experiment-001")["sections"]
    assert sections["结论"] == "数据不足"
    assert sections["置信度"] == "低"
    assert sections["下一步"] == "设计实验收集数据"


def test_record_experiment_continues_numbering(tmp_path):
    memory = make_api(tmp_path)
    memory.recordHypothesis(hypothesis="h1")

    memory.recordExperiment(
        hypothesis="h2",
        variables=["主题"],
        expected="e",
        actual="a",
        evidence="ev",
        conclusion="暂时支持",
        confidence="中",
        next_action="继续",
    )

    assert memory.get("experiment", "Experiment-002")["ok"] is True


def test_record_decision(tmp_path):
    memory = make_api(tmp_path)
    record = memory.recordDecision(subject="AI 标题", decision="不采用", reason="过度营销", date="2026-09-28")

    assert record["category"] == "decision"
    assert memory.get("decision", "2026-09-28-决策-AI 标题")["sections"]["原因"] == "过度营销"


def test_same_title_different_content_does_not_overwrite(tmp_path):
    memory = make_api(tmp_path)
    first = memory.recordObservation(topic="内容类型", observation="观察一", evidence="证据一")
    second = memory.recordObservation(topic="内容类型", observation="观察二", evidence="证据二")

    assert first["path"] != second["path"]
    assert len(memory.layer.list_notes("insight")) == 2


def test_same_content_rewrite_is_idempotent(tmp_path):
    memory = make_api(tmp_path)
    first = memory.recordObservation(topic="内容类型", observation="观察", evidence="证据")
    second = memory.recordObservation(topic="内容类型", observation="观察", evidence="证据")

    assert first["path"] == second["path"]
    assert len(memory.layer.list_notes("insight")) == 1


# ── 解析器 ──────────────────────────────────────────────────────────────


def test_parse_note_handles_frontmatter_and_sections():
    text = (
        "---\n"
        "type: decision\n"
        "status: archived\n"
        "created: 2026-09-28 10:00:00\n"
        "tags:\n"
        "  - decision\n"
        "  - creator-os\n"
        "related: []\n"
        "---\n\n"
        "# 标题\n\n"
        "## 事项\nAI 标题\n\n"
        "## 原因\n第一行\n第二行\n"
    )
    frontmatter, sections = parse_note(text)

    assert frontmatter["type"] == "decision"
    assert frontmatter["status"] == "archived"
    assert frontmatter["tags"] == ["decision", "creator-os"]
    assert frontmatter["related"] == "[]"
    assert sections["事项"] == "AI 标题"
    assert sections["原因"] == "第一行\n第二行"
