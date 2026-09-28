"""Phase 5：Research Agent 全链路（材料 -> 分类/抽取 -> Topic Candidate）。"""

from types import SimpleNamespace

from agents import ResearcherAgent
from runtime.reach_research import ReachResearch
from runtime.research_store import ResearchStore
from runtime.topics import build_candidates, classify, dedupe_items, extract

MEMORY_MATERIAL = {
    "url": "https://example.com/memory-layer",
    "title": "Obsidian 长期记忆分层实践",
    "content": "冷暖热三层结构，热层 3 条规则。\n建议：先只做检索，别急着上向量库。",
    "source": "web",
    "timestamp": "2026-09-28T10:00:00.000Z",
}
PLATFORM_MATERIAL = {
    "url": "https://example.com/xhs",
    "title": "小红书发布节奏",
    "content": "一周 3 条的互动率比日更高。",
    "source": "web",
    "timestamp": "2026-09-27T10:00:00.000Z",
}


def fake_reach(tmp_path, stdout="owner/repo\tA helper\tpublic\t2026-09-28\n", which_ok=True):
    return ReachResearch(
        vault_path=tmp_path,
        store=ResearchStore(":memory:"),
        runner=lambda argv, timeout: SimpleNamespace(returncode=0, stdout=stdout, stderr=""),
        which=lambda name: "/usr/local/bin/name" if which_ok else None,
    )


# ── 用现成材料跑（不联网） ──────────────────────────────────────────────


def test_run_with_materials_returns_candidates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agent = ResearcherAgent()

    result = agent.run("记忆分层", {"materials": [MEMORY_MATERIAL, PLATFORM_MATERIAL]})

    assert result["agent"] == "Researcher Agent"
    assert result["material_count"] == 2
    assert len(result["candidates"]) == 2
    assert set(result["knowledge_points"]) == {"记忆系统", "平台运营"}
    assert "候选选题" in result["details"]
    assert result["errors"] == []
    assert not (tmp_path / "obsidian_vault" / "11-Research").exists()  # 候选不写记忆


def test_candidate_fields_are_complete(tmp_path):
    agent = ResearcherAgent()
    candidate = agent.run("记忆分层", {"materials": [MEMORY_MATERIAL]})["candidates"][0]

    for field in ("topic", "category", "sources", "evidence", "facts", "opinions", "freshness", "confidence", "created_at"):
        assert field in candidate, field
    assert candidate["topic"] == "Obsidian 长期记忆分层实践"
    assert candidate["sources"] == ["https://example.com/memory-layer"]
    assert candidate["freshness"] == "2026-09-28"
    assert candidate["confidence"] == "LOW"  # 规则抽取，未经复核


def test_same_title_materials_merge_into_one_candidate():
    duplicate = {**MEMORY_MATERIAL, "url": "https://example.com/mirror"}
    candidates = build_candidates(dedupe_items([MEMORY_MATERIAL, duplicate]))

    assert len(candidates) == 1
    assert candidates[0].sources == [
        "https://example.com/memory-layer",
        "https://example.com/mirror",
    ]


# ── 走真实链路（假通道） ────────────────────────────────────────────────


def test_run_harvests_from_channel_and_stores_material(tmp_path):
    agent = ResearcherAgent(reach=fake_reach(tmp_path))

    result = agent.run("obsidian memory", {"channel": "github"})

    assert result["material_count"] == 1
    assert result["candidates"][0]["sources"] == ["https://github.com/owner/repo"]
    assert agent.reach.store.count() == 1  # 原始材料进数据库
    assert not (tmp_path / "11-Research").exists()  # 结论不进记忆


def test_run_reports_fetch_failure_without_candidates(tmp_path):
    agent = ResearcherAgent(reach=fake_reach(tmp_path, which_ok=False))

    result = agent.run("obsidian memory")

    assert result["summary"].startswith("调研失败")
    assert result["errors"] and "找不到命令" in result["errors"][0]
    assert result["candidates"] == []
    assert agent.reach.store.count() == 0


# ── 分类与抽取规则 ──────────────────────────────────────────────────────


def test_classify_maps_text_to_category():
    assert classify("Obsidian 长期记忆分层") == "记忆系统"
    assert classify("小红书发布节奏与涨粉") == "平台运营"
    assert classify("互动率数据分析面板") == "数据增长"
    assert classify("今天天气不错") == "未分类"


def test_extract_separates_facts_opinions_and_evidence():
    extracted = extract(MEMORY_MATERIAL)

    assert extracted["facts"] == ["冷暖热三层结构，热层 3 条规则。"]
    assert extracted["opinions"] == ["建议：先只做检索，别急着上向量库。"]
    assert extracted["evidence"] == [
        {"url": "https://example.com/memory-layer", "quote": "冷暖热三层结构，热层 3 条规则。"}
    ]


def test_extract_does_not_invent_facts_from_plain_text():
    extracted = extract({"url": "https://a.com/1", "content": "这是一段没有任何数字的普通描述文字"})

    assert extracted["facts"] == []
    assert extracted["evidence"][0]["url"] == "https://a.com/1"


def test_injected_extractor_overrides_rules():
    agent = ResearcherAgent(extractor=lambda item: {"facts": ["模型给出的事实"], "opinions": [], "evidence": []})

    candidate = agent.run("x", {"materials": [MEMORY_MATERIAL]})["candidates"][0]

    assert candidate["facts"] == ["模型给出的事实"]
    assert candidate["opinions"] == []  # 规则结果被完全替换


def test_defaults_do_not_touch_network(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agent = ResearcherAgent()  # 不构造通道

    assert agent._reach is None
    agent.run("x", {"materials": [MEMORY_MATERIAL]})
    assert agent._reach is None
