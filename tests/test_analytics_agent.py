"""Phase 17：Analytics Agent（模式识别 → 候选洞察 → 证据闸门 → 记忆/策略候选）。"""

import pytest

from agents import AnalyticsAgent
from runtime.analytics_agent import (
    UNRATED,
    InsightCandidate,
    build_insight_candidates,
    detect_patterns,
    evidence_check,
    propose_strategy,
    record_to_memory,
)
from runtime.analytics_store import AnalyticsStore
from runtime.memory_api import MemoryAPI
from runtime.post_analytics import PostAnalytics


def snap(post_id, content_type, rate, views=100, collected_at=""):
    """一条已发布内容的最新快照：engagement 只有 likes，rate = likes/views。"""
    return PostAnalytics(
        post_id=post_id,
        platform="x",
        content_type=content_type,
        metrics={"likes": round(views * rate), "views": views},
        collected_at=collected_at,
    )


def seed(store):
    """thread 3 条 10%，post 3 条 2% —— thread 明显更高，且样本刚好够闸门。"""
    for index in range(3):
        store.record(snap(f"t{index}", "thread", 0.10, collected_at=f"2026-09-0{index + 1} 10:00:00"))
        store.record(snap(f"p{index}", "post", 0.02, collected_at=f"2026-09-0{index + 1} 11:00:00"))
    return store


# ── Pattern Detection ──────────────────────────────────────────────────


def test_detect_patterns_groups_by_content_type(tmp_path):
    store = seed(AnalyticsStore(tmp_path / "a.sqlite3"))

    patterns = detect_patterns(store)

    by_key = {p.key: p for p in patterns}
    assert by_key["thread"].samples == 3 and by_key["thread"].rated_samples == 3
    assert by_key["thread"].avg_engagement_rate == pytest.approx(0.10)
    assert by_key["post"].avg_engagement_rate == pytest.approx(0.02)
    assert len(by_key["thread"].post_ids) == 3
    assert patterns[0].key == "thread"                      # 互动率高的排前面
    store.close()


def test_detect_patterns_uses_latest_snapshot_and_skips_retweets(tmp_path):
    store = AnalyticsStore(tmp_path / "a.sqlite3")
    store.record(snap("t0", "thread", 0.01, collected_at="2026-09-01 10:00:00"))
    store.record(snap("t0", "thread", 0.20, collected_at="2026-09-02 10:00:00"))  # 同 post 更新一条
    store.record(PostAnalytics(post_id="rt0", platform="x", content_type="thread",
                               is_retweet=True, metrics={"likes": 99, "views": 100}))

    patterns = detect_patterns(store)
    thread = next(p for p in patterns if p.key == "thread")

    assert thread.samples == 1                                # 转发不算，同 post 只取最新
    assert thread.avg_engagement_rate == pytest.approx(0.20)
    assert "rt0" not in thread.post_ids
    store.close()


def test_detect_patterns_without_content_type_falls_back_to_unrated(tmp_path):
    store = AnalyticsStore(tmp_path / "a.sqlite3")
    store.record(snap("x1", "", 0.05))

    assert [p.key for p in detect_patterns(store)] == [UNRATED]
    store.close()


def test_detect_patterns_empty_store_returns_nothing(tmp_path):
    store = AnalyticsStore(tmp_path / "a.sqlite3")

    assert detect_patterns(store) == []
    store.close()


# ── Insight Candidate ──────────────────────────────────────────────────


def test_candidates_compared_against_pooled_baseline(tmp_path):
    store = seed(AnalyticsStore(tmp_path / "a.sqlite3"))

    candidates = {c.subject: c for c in build_insight_candidates(detect_patterns(store))}

    thread, post = candidates["thread"], candidates["post"]
    assert thread.avg_engagement_rate == pytest.approx(0.10)
    assert thread.baseline_rate == pytest.approx(0.02)        # 其余类型的合并平均
    assert thread.lift == pytest.approx(0.08)
    assert post.baseline_rate == pytest.approx(0.10)          # 自己不进自己的基线
    assert post.lift == pytest.approx(-0.08)
    store.close()


def test_statement_states_facts_with_sample_size_not_commands(tmp_path):
    store = seed(AnalyticsStore(tmp_path / "a.sqlite3"))

    thread = next(c for c in build_insight_candidates(detect_patterns(store)) if c.subject == "thread")

    assert "6 条" in thread.statement and "3 条" in thread.statement   # 总量与本组样本量
    assert "平均互动率" in thread.statement and "10.00%" in thread.statement
    assert not any(word in thread.statement for word in ("以后", "全部", "应该", "一定要"))


def test_candidate_carries_traceable_evidence(tmp_path):
    store = seed(AnalyticsStore(tmp_path / "a.sqlite3"))

    thread = next(c for c in build_insight_candidates(detect_patterns(store)) if c.subject == "thread")

    evidence = next(item for item in thread.evidence if item.startswith("post_ids="))
    assert {"t0", "t1", "t2"} <= set(evidence.removeprefix("post_ids=").split(","))
    assert any(item.startswith("采集窗口=") for item in thread.evidence)
    assert thread.confidence in ("低", "中")                  # 永远不产生「高」
    store.close()


# ── Evidence Check ─────────────────────────────────────────────────────


def check(subject, **overrides):
    candidate = build_candidate(subject, **overrides)
    return evidence_check(candidate)


def build_candidate(subject, *, rated=3, rate=0.10, baseline=0.02, lift=0.08, evidence=None):
    return InsightCandidate(
        subject=subject,
        statement="（测试用陈述）",
        samples=rated,
        rated_samples=rated,
        avg_engagement_rate=rate,
        baseline_rate=baseline,
        lift=lift,
        evidence=evidence if evidence is not None else ["post_ids=t0,t1,t2"],
    )


def test_evidence_check_passes_with_enough_samples_and_baseline():
    candidate = check("thread")

    assert candidate.ready is True and candidate.blockers == []


def test_evidence_check_blocks_small_sample():
    candidate = check("thread", rated=2)

    assert candidate.ready is False
    assert any("样本不足" in blocker for blocker in candidate.blockers)


def test_evidence_check_blocks_single_group_without_baseline():
    candidate = check("thread", baseline=None, lift=None)

    assert candidate.ready is False
    assert any("缺少对比组" in blocker for blocker in candidate.blockers)


def test_evidence_check_blocks_below_baseline():
    candidate = check("post", rate=0.02, baseline=0.10, lift=-0.08)

    assert candidate.ready is False
    assert any("不构成正向候选" in blocker for blocker in candidate.blockers)


def test_evidence_check_blocks_unrated_and_missing_evidence():
    unrated = check(UNRATED)
    no_evidence = check("thread", evidence=["post_ids="])

    assert any("未标注" in blocker for blocker in unrated.blockers)
    assert any("post_id" in blocker for blocker in no_evidence.blockers)
    assert unrated.ready is False and no_evidence.ready is False


def test_evidence_check_blocks_missing_rate():
    candidate = check("thread", rate=None, baseline=None, lift=None)

    assert candidate.ready is False
    assert any("算不出互动率" in blocker for blocker in candidate.blockers)


# ── Memory / Strategy Candidate ────────────────────────────────────────


def test_record_to_memory_writes_pending_observation(tmp_path):
    memory = MemoryAPI(vault_path=tmp_path / "vault")
    ready = check("thread")

    record = record_to_memory(ready, memory)

    assert record["ok"] is True
    notes = memory.list_notes("insight")
    assert len(notes) == 1
    found = memory.get("insight", notes[0].rsplit("/", 1)[-1].removesuffix(".md"))
    assert found["frontmatter"]["status"] == "pending"        # 观察，等 Memory Review
    assert found["sections"]["状态"] == "观察"
    assert memory.get("strategy")["ok"] is False              # 绝不写 Strategy


def test_record_to_memory_rejects_blocked_candidate(tmp_path):
    memory = MemoryAPI(vault_path=tmp_path / "vault")
    blocked = check("thread", rated=2)

    with pytest.raises(ValueError):
        record_to_memory(blocked, memory)
    assert memory.list_notes("insight") == []


def test_propose_strategy_is_always_unapplied():
    candidate = propose_strategy(check("thread"))

    assert candidate.status == "PROPOSED" and candidate.applied is False
    assert candidate.requires_review is True and "recordDecision" in candidate.next_step
    assert "thread" in candidate.proposal and candidate.rationale


def test_propose_strategy_rejects_blocked_candidate():
    with pytest.raises(ValueError):
        propose_strategy(check("thread", rated=1))


# ── Agent 主链路 ────────────────────────────────────────────────────────


def run_agent(tmp_path, **context):
    store = seed(AnalyticsStore(tmp_path / "a.sqlite3"))
    memory = MemoryAPI(vault_path=tmp_path / "vault")
    agent = AnalyticsAgent(memory=memory, store=store)
    base = {"store": store}
    base.update(context)
    return agent, agent.run("分析最近内容表现", base)


def test_agent_full_pipeline(tmp_path):
    agent, result = run_agent(tmp_path)

    assert result["summary"].startswith("2 类内容")
    assert len(result["patterns"]) == 2
    ready = [c for c in result["insights"] if c["ready"]]
    blocked = [c for c in result["insights"] if not c["ready"]]
    assert len(ready) == 1 and ready[0]["subject"] == "thread"
    assert len(blocked) == 1 and blocked[0]["blockers"]         # post 组低于基线被拦

    assert len(result["strategy_candidates"]) == 1              # 只有通过闸门的才出候选
    strategy = result["strategy_candidates"][0]
    assert strategy["applied"] is False and strategy["status"] == "PROPOSED"

    assert len(result["memory_writes"]) == 1                    # 写的是 pending 观察
    assert agent.memory.get("strategy")["ok"] is False           # 策略记忆没被碰过
    assert result["errors"] == []


def test_agent_can_skip_memory_write(tmp_path):
    _, result = run_agent(tmp_path, write_memory=False)

    assert result["memory_writes"] == []
    assert any("未写记忆" in item for item in result["warnings"])
    notes = MemoryAPI(vault_path=tmp_path / "vault").list_notes("insight")
    assert notes == []


def test_agent_without_data_fails_honestly(tmp_path):
    store = AnalyticsStore(tmp_path / "empty.sqlite3")
    agent = AnalyticsAgent(memory=MemoryAPI(vault_path=tmp_path / "vault"), store=store)

    result = agent.run("分析最近内容表现", {"store": store})

    assert result["errors"] and "patterns 为空" in result["errors"][0]
    assert result["patterns"] == [] and result["strategy_candidates"] == []
    assert any("Phase 16" in action for action in result["next_actions"])
