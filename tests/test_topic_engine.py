"""Phase 6：Topic Engine 评分与推荐。"""

from datetime import datetime

from runtime.memory_api import MemoryAPI
from runtime.topic_engine import TopicEngine
from runtime.topics import TopicCandidate

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

TODAY = datetime.now().strftime("%Y-%m-%d")


def candidate(**overrides) -> TopicCandidate:
    base = {
        "topic": "Obsidian 长期记忆分层实践",
        "category": "AI 工具",
        "sources": ["https://a.com/1", "https://a.com/2"],
        "evidence": [{"url": "https://a.com/1", "quote": "热层 3 条规则"}],
        "facts": ["热层 3 条规则"],
        "opinions": [],
        "freshness": TODAY,
        "confidence": "LOW",
    }
    base.update(overrides)
    return TopicCandidate(**base)


def engine_with_account(tmp_path) -> TopicEngine:
    memory = MemoryAPI(vault_path=tmp_path)
    if not memory.get("account").get("ok"):
        memory.create("account", "账号画像", ACCOUNT)
    return TopicEngine(memory=memory)


# ── 输出结构 ────────────────────────────────────────────────────────────


def test_recommendation_covers_all_phase6_fields(tmp_path):
    result = engine_with_account(tmp_path).recommend([candidate()])

    rec = result["recommendations"][0]
    for field in ("topic", "angles", "audience", "sources", "evidence", "freshness",
                  "competition", "account_fit", "content_type", "why", "blockers", "score"):
        assert field in rec, field
    assert rec["audience"] == "开发者"  # 受众取自 Account Memory，不自己编
    assert rec["competition"] == "UNKNOWN"  # 没有竞争数据就不编
    assert rec["content_type"] in ("X Post", "X Thread")  # Phase 9 第一阶段只做 X
    assert len(rec["angles"]) >= 2


def test_recommendations_are_sorted_by_score(tmp_path):
    strong = candidate(sources=["https://a.com/1", "https://a.com/2", "https://a.com/3"],
                       facts=["热层 3 条规则", "样本量 5"])
    weak = candidate(topic="无关话题", category="未分类", sources=[], facts=[], evidence=[], freshness="1999-01-01")

    result = engine_with_account(tmp_path).recommend([weak, strong])

    assert result["recommendations"][0]["topic"] == strong.topic
    assert result["recommendations"][0]["score"] > result["recommendations"][1]["score"]


def test_top_k_truncates(tmp_path):
    items = [candidate(topic=f"选题{i}") for i in range(5)]

    assert len(engine_with_account(tmp_path).recommend(items, top_k=2)["recommendations"]) == 2
    assert engine_with_account(tmp_path).recommend(items, top_k=0)["recommendations"] == []


def test_empty_candidates_is_not_an_error(tmp_path):
    result = engine_with_account(tmp_path).recommend([])

    assert result["ok"] is True and result["recommendations"] == [] and result["warnings"] == []


# ── 账号契合 ────────────────────────────────────────────────────────────


def test_account_fit_high_when_category_matches_profile(tmp_path):
    result = engine_with_account(tmp_path).recommend([candidate(category="AI 工具", topic="Agent 自动化工具实测")])

    rec = result["recommendations"][0]
    assert rec["account_fit"] == "HIGH"
    assert any("命中账号定位词" in reason for reason in rec["why"])


def test_account_fit_low_when_topic_is_irrelevant(tmp_path):
    rec = engine_with_account(tmp_path).recommend([candidate(topic="美食探店攻略", category="未分类")])["recommendations"][0]

    assert rec["account_fit"] == "LOW"
    assert any("关联弱" in blocker for blocker in rec["blockers"])


def test_missing_account_memory_yields_unknown_fit(tmp_path):
    engine = TopicEngine(memory=MemoryAPI(vault_path=tmp_path))  # 没有 Account

    result = engine.recommend([candidate()])

    rec = result["recommendations"][0]
    assert rec["account_fit"] == "UNKNOWN"
    assert rec["audience"] == "UNKNOWN"
    assert result["warnings"] and "Account Memory" in result["warnings"][0]
    assert any("缺 Account Memory" in blocker for blocker in rec["blockers"])


# ── 理由与阻塞项 ────────────────────────────────────────────────────────


def test_blockers_expose_missing_evidence_and_freshness(tmp_path):
    rec = engine_with_account(tmp_path).recommend(
        [candidate(facts=[], evidence=[], freshness="UNKNOWN")]
    )["recommendations"][0]

    assert "缺少可引用的事实线索，先补证据" in rec["blockers"]
    assert "没有可展示的证据摘录" in rec["blockers"]
    assert "材料时间未知，需要确认时效" in rec["blockers"]
    full = engine_with_account(tmp_path).recommend([candidate()])["recommendations"][0]
    assert full["score"] - rec["score"] >= 35  # 缺事实(10) + 缺时效(25) 至少扣 35 分


def test_old_material_gets_no_freshness_score(tmp_path):
    old = engine_with_account(tmp_path).recommend([candidate(freshness="2024-01-01")])["recommendations"][0]
    fresh = engine_with_account(tmp_path).recommend([candidate(freshness=TODAY)])["recommendations"][0]

    assert fresh["score"] - old["score"] >= 25


def test_why_lists_sources_and_fit(tmp_path):
    rec = engine_with_account(tmp_path).recommend([candidate()])["recommendations"][0]

    assert any("2 条来源" in reason for reason in rec["why"])
    assert any("事实线索" in reason for reason in rec["why"])
    assert any("时效窗口" in reason for reason in rec["why"])
