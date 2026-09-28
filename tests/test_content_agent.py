"""Phase 9：Content Agent 端到端（选题 → 草稿 → 三道检查 → 等人审）。"""

from agents import ContentAgent
from runtime.content_store import ContentStore
from runtime.memory_api import MemoryAPI

ACCOUNT = {
    "账号定位": "AI 工具实测",
    "目标受众": "开发者",
    "内容领域": "开源项目",
    "内容支柱": "项目实测",
    "表达风格": "实测 > 空谈",
    "长期目标": "沉淀评测方法论",
    "禁止内容": "收益承诺、标题党",
    "平台差异": "X 走 Thread",
    "账号阶段": "冷启动",
}


def candidate(**overrides) -> dict:
    base = {
        "topic": "Obsidian 记忆分层",
        "angle": "冷暖热三层实测",
        "audience": "开发者",
        "category": "记忆系统",
        "sources": ["https://a.com/1"],
        "evidence": [{"url": "https://a.com/1", "quote": "热层 3 条规则"}],
        "facts": ["热层 3 条规则"],
        "opinions": ["建议先做检索"],
    }
    base.update(overrides)
    return base


def make_agent(tmp_path, with_account=True, **kwargs) -> ContentAgent:
    memory = MemoryAPI(vault_path=tmp_path)
    if with_account:
        memory.create("account", "账号画像", ACCOUNT)
    return ContentAgent(store=ContentStore(tmp_path / "content.sqlite3"), memory=memory, **kwargs)


# ── 成功路径 ────────────────────────────────────────────────────────────


def test_successful_run_reaches_review(tmp_path):
    agent = make_agent(tmp_path)

    result = agent.run("写一条 Thread", {"recommendation": candidate()})

    assert result["errors"] == []
    assert result["content"]["status"] == "REVIEW"
    assert result["pending_human_review"] is True
    assert result["posts"][0] == "冷暖热三层实测"
    assert result["content"]["hook"] == "冷暖热三层实测"
    assert all(section["ok"] for section in result["checks"].values())
    assert "等人审" in result["summary"]
    assert "Human Review" in result["next_actions"][0]
    assert "✓ fact_check" in result["details"]


def test_content_is_persisted(tmp_path):
    agent = make_agent(tmp_path)

    result = agent.run("x", {"recommendation": candidate()})
    reloaded = ContentStore(tmp_path / "content.sqlite3").get(result["content"]["id"])

    assert reloaded.status == "REVIEW"
    assert reloaded.core_content.startswith("冷暖热三层实测")
    assert reloaded.claims == ["热层 3 条规则"]


def test_brief_supplies_audience_when_unknown(tmp_path):
    agent = make_agent(tmp_path)
    brief = {"answer": ["账号定位「AI 工具实测」，受众「开发者」。"]}

    result = agent.run("x", {"recommendation": candidate(audience="UNKNOWN"), "brief": brief})

    assert "AI 工具实测" in result["content"]["audience"]


def test_injected_drafter_controls_posts(tmp_path):
    agent = make_agent(tmp_path, drafter=lambda **kw: ["定制首条", "定制结尾"])

    result = agent.run("x", {"recommendation": candidate()})

    assert result["posts"] == ["定制首条", "定制结尾"]
    assert result["content"]["status"] == "REVIEW"


# ── 失败路径：不放行、不落库 ────────────────────────────────────────────


def test_missing_input_returns_failure_without_writing(tmp_path):
    agent = make_agent(tmp_path)

    result = agent.run("x")

    assert result["summary"].startswith("缺少输入")
    assert result["content"] is None
    assert agent.store.count() == 0


def test_candidate_without_evidence_is_rejected(tmp_path):
    agent = make_agent(tmp_path)

    result = agent.run("x", {"recommendation": candidate(sources=[], evidence=[] )})

    assert "缺少研究证据" in result["summary"]
    assert agent.store.count() == 0


def test_untraceable_claim_blocks_review(tmp_path):
    agent = make_agent(tmp_path)
    bad = candidate(facts=["来源里查不到的断言"])

    result = agent.run("x", {"recommendation": bad})

    assert result["content"]["status"] == "DRAFT"  # 没证据的断言不许进 REVIEW
    assert any("事实核查" in issue for issue in result["errors"])
    assert result["pending_human_review"] is False


def test_banned_word_blocks_review(tmp_path):
    agent = make_agent(tmp_path)
    dirty = candidate(
        facts=["照做就能收益承诺翻倍"],
        evidence=[{"url": "https://a.com/1", "quote": "照做就能收益承诺翻倍"}],
    )

    result = agent.run("x", {"recommendation": dirty})

    assert result["content"]["status"] == "DRAFT"
    assert any("禁用词" in issue for issue in result["errors"])


def test_ai_flavor_blocks_review(tmp_path):
    agent = make_agent(tmp_path)
    flavored = candidate(opinions=["总之，这套方法最值得用"])

    result = agent.run("x", {"recommendation": flavored})

    assert result["content"]["status"] == "DRAFT"
    assert any("AI 味" in issue for issue in result["errors"])


def test_no_claims_still_reaches_review_with_empty_fact_check(tmp_path):
    agent = make_agent(tmp_path)

    result = agent.run("x", {"recommendation": candidate(facts=[])})  # 没抽到事实线索

    assert result["content"]["status"] == "REVIEW"
    assert result["checks"]["fact_check"]["checked"] == 0  # 无可核查项，不冒充「已核查」
    assert result["pending_human_review"] is True


def test_missing_account_skips_banned_words_gracefully(tmp_path):
    agent = make_agent(tmp_path, with_account=False)

    result = agent.run("x", {"recommendation": candidate()})

    assert result["content"]["status"] == "REVIEW"  # 读不到账号就只做其余检查
    assert result["checks"]["style_check"]["ok"] is True
