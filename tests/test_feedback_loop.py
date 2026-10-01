"""Phase 18：核心闭环编排（FeedbackLoop）——Research → … → Memory → Strategy 转一圈。"""

from datetime import datetime

from agents import ContentAgent, FeedbackLoop
from agents.feedback_loop import GATED, RAN, SKIPPED, STAGES
from runtime.analytics_store import AnalyticsStore
from runtime.content_store import ContentStore
from runtime.memory_api import MemoryAPI
from runtime.post_analytics import PostAnalytics

ACCOUNT = {
    "账号定位": "AI 记忆系统实测",
    "目标受众": "开发者",
    "内容领域": "开源知识库",
    "内容支柱": "项目实测",
    "表达风格": "实测 > 空谈",
    "长期目标": "沉淀评测方法论",
    "禁止内容": "收益承诺、标题党",
    "平台差异": "X 走 Thread",
    "账号阶段": "冷启动",
}

STRATEGY = {
    "当前内容策略": "围绕记忆系统做项目实测",
    "内容支柱": "项目实测",
    "目标方向": "沉淀评测方法论",
    "状态": "Confirmed",
    "策略变更原因": "首次建立",
}


def materials() -> list[dict]:
    """离线材料（不联网）：带时间戳、可抽出事实与证据。"""
    return [{
        "url": "https://a.com/obsidian-memory",
        "title": "Obsidian 记忆分层实测",
        "content": (
            "热层放 3 条高频规则，冷层存 200 条归档笔记。\n"
            "检索延迟从 800ms 降到 120ms，实测 5 次都稳定。\n"
            "建议先做记忆分层，再接 Agent 自动写入。"
        ),
        "source": "web",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }]


def seed_analytics(store: AnalyticsStore) -> None:
    for index in range(3):
        store.record(PostAnalytics(
            post_id=f"t{index}", platform="x", content_type="thread",
            metrics={"likes": 10, "views": 100},
            collected_at=f"2026-09-0{index + 1} 10:00:00"))
        store.record(PostAnalytics(
            post_id=f"p{index}", platform="x", content_type="post",
            metrics={"likes": 2, "views": 100},
            collected_at=f"2026-09-0{index + 1} 11:00:00"))


def build(tmp_path, *, with_analytics=True):
    memory = MemoryAPI(vault_path=tmp_path / "vault")
    memory.create("account", "账号画像", ACCOUNT)
    memory.create("strategy", "当前内容策略", STRATEGY)
    analytics = AnalyticsStore(tmp_path / "analytics.sqlite3")
    if with_analytics:
        seed_analytics(analytics)
    loop = FeedbackLoop(
        memory=memory,
        analytics_store=analytics,
        content_agent=ContentAgent(store=ContentStore(tmp_path / "content.sqlite3"),
                                   memory=memory),
    )
    return memory, analytics, loop


def steps_of(result):
    return result["steps"]


# ── 端到端：一圈真的转起来 ──────────────────────────────────────────────


def test_loop_closes_the_full_cycle_offline(tmp_path):
    _memory, _store, loop = build(tmp_path)

    result = loop.run("本轮闭环", {"materials": materials()})

    assert result["ok"] is True
    assert [step["name"] for step in steps_of(result)] == list(STAGES)
    research, strategy, content, publish, analytics, insight, memory_step, feedback = steps_of(result)

    assert research["status"] == RAN and len(research["data"]["candidates"]) >= 1
    assert strategy["status"] == RAN
    assert content["status"] == RAN and content["data"]["status"] == "REVIEW"
    assert content["data"]["pending_human_review"] is True
    assert publish["status"] == GATED and "人审" in publish["summary"]
    assert analytics["status"] == SKIPPED and "采集器" in analytics["summary"]
    assert insight["status"] == RAN and insight["data"]["memory_writes"] >= 1
    assert memory_step["status"] == RAN and len(memory_step["data"]["pending"]) >= 1
    assert feedback["status"] == RAN and feedback["data"]["insight_notes"]

    # 闭环的证据：这轮写进去的观察，下一轮 Strategy 确实读得到
    assert set(memory_step["data"]["pending"][i]["title"]
               for i in range(len(memory_step["data"]["pending"]))) <= set(feedback["data"]["insight_notes"])


def test_loop_never_touches_strategy_and_stops_at_gates(tmp_path):
    memory, _store, loop = build(tmp_path)

    loop.run("本轮闭环", {"materials": materials()})

    found = memory.get("strategy")
    assert found["ok"] is True
    assert found["sections"] == STRATEGY
    assert found["frontmatter"]["status"] == "active"

    rows = ContentStore(tmp_path / "content.sqlite3").list()
    assert rows and all(row["status"] == "REVIEW" for row in rows)  # 人审前不许往下走


def test_next_actions_point_to_human_gates(tmp_path):
    _memory, _store, loop = build(tmp_path)

    result = loop.run("本轮闭环", {"materials": materials()})

    joined = " ".join(result["next_actions"])
    assert "human_review.approve" in joined
    assert "review_insight" in joined
    assert "PROPOSED" in joined


def test_selected_recommendation_can_skip_research(tmp_path):
    memory, _store, loop = build(tmp_path)
    raw = _recommendation(memory)

    result = loop.run("本轮闭环", {"recommendations": [raw]})

    steps = {index: step for index, step in enumerate(steps_of(result))}
    assert steps[0]["status"] == SKIPPED and "缺外部输入" in steps[0]["summary"]
    assert steps[1]["status"] == RAN
    assert steps[2]["status"] == RAN


def _recommendation(memory) -> dict:
    from runtime.topic_engine import TopicEngine

    return TopicEngine(memory=memory).recommend(_candidates())["recommendations"][0]


def _candidates() -> list[dict]:
    return [{
        "topic": "Obsidian 记忆分层实测",
        "category": "记忆系统",
        "sources": ["https://a.com/obsidian-memory"],
        "evidence": [{"url": "https://a.com/obsidian-memory",
                      "quote": "热层放 3 条高频规则"}],
        "facts": ["热层放 3 条高频规则"],
        "opinions": [],
        "freshness": datetime.now().strftime("%Y-%m-%d"),
    }]


# ── 断点与诚实失败 ──────────────────────────────────────────────────────


def test_facts_survive_from_engine_to_content_claims(tmp_path):
    """闭环断点回归：Phase 6 推荐必须带上 facts，否则 Phase 9 的事实核查空转。"""
    memory, _store, _loop = build(tmp_path)

    recommendation = _recommendation(memory)

    assert recommendation["facts"] == ["热层放 3 条高频规则"]

    from agents import ContentAgent

    agent = ContentAgent(store=ContentStore(tmp_path / "c2.sqlite3"), memory=memory)
    result = agent.run("写一条 Thread", {"recommendation": recommendation})

    assert result["content"]["status"] == "REVIEW"
    assert result["content"]["claims"] == ["热层放 3 条高频规则"]
    assert result["checks"]["fact_check"]["ok"] is True


def test_loop_without_analytics_reports_insight_skipped(tmp_path):
    _memory, _store, loop = build(tmp_path, with_analytics=False)

    result = loop.run("本轮闭环", {"materials": materials()})

    insight = steps_of(result)[5]
    assert insight["status"] == SKIPPED
    assert "表现数据" in insight["summary"] or "采集" in insight["summary"]
    assert result["insights"] == [] and result["pending_review"] == []
    assert result["ok"] is True                     # 没数据是 skip，不是失败


def test_content_stage_picks_topic_when_no_recommend_verdict(tmp_path):
    """历史重合会让 verdict 降到「需人工判断」；人用 topic 指定今天做哪题才能往下走。"""
    memory, _store, loop = build(tmp_path)
    briefs = [{"topic": "Obsidian 记忆分层实测", "verdict": "需人工判断",
               "recommendation": _recommendation(memory)}]

    skipped = loop._content("写一条 Thread", {}, [], briefs)
    assert skipped.status == SKIPPED
    assert "需人工判断" in skipped.summary            # skip 要说清是哪题卡住、卡在什么结论

    picked = loop._content("写一条 Thread", {"topic": "Obsidian 记忆分层实测"}, [], briefs)
    assert picked.status == RAN
    assert picked.data["status"] == "REVIEW"          # 绕开 verdict 闸门不等于绕过人审


def test_loop_without_inputs_skips_upstream_stages(tmp_path):
    _memory, _store, loop = build(tmp_path)

    result = loop.run("本轮闭环", {})

    research, strategy, content, publish = steps_of(result)[:4]
    for step in (research, strategy, content, publish):
        assert step["status"] == SKIPPED
        assert step["summary"]                      # 每个 skip 都要写清缺什么


def test_stage_exception_becomes_failed_not_success(tmp_path):
    class BoomCollector:
        def collect_published(self, limit=20):
            raise RuntimeError("通道挂了")

    _memory, _store, loop = build(tmp_path)
    result = loop.run("本轮闭环", {"materials": materials(), "collector": BoomCollector()})

    analytics = steps_of(result)[4]
    assert analytics["status"] == "failed" and "通道挂了" in analytics["summary"]
    assert result["ok"] is False
    assert result["counts"]["failed"] == 1


# ── Memory Review 闸门 ─────────────────────────────────────────────────


def test_review_insight_approve_promotes_to_active(tmp_path):
    memory, _store, loop = build(tmp_path)
    record = memory.recordObservation(topic="content_type:thread",
                                      observation="thread 类互动率更高",
                                      evidence="post_ids=t0")
    title = record["title"].removesuffix(".md")

    outcome = loop.review_insight(title, approved=True, reason="样本够了")

    assert outcome["ok"] is True
    assert memory.get("insight", title)["frontmatter"]["status"] == "active"


def test_review_insight_reject_archives(tmp_path):
    memory, _store, loop = build(tmp_path)
    record = memory.recordObservation(topic="content_type:thread",
                                      observation="样本不足的猜测",
                                      evidence="post_ids=t0")
    title = record["title"].removesuffix(".md")

    loop.review_insight(title, approved=False, reason="只有 3 条样本，先归档")

    assert title not in [path.rsplit("/", 1)[-1].removesuffix(".md")
                         for path in memory.list_notes("insight")]
