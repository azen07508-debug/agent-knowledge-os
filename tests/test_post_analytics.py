"""Phase 16：PostAnalytics / AnalyticsStore / AnalyticsCollector。"""

import pytest

from runtime.analytics_collector import AnalyticsCollector
from runtime.analytics_store import AnalyticsStore
from runtime.post_analytics import (
    PostAnalytics,
    engagement_of,
    normalize_metrics,
)
from runtime.publish_queue import PublishJobStore

# ── 模型与归一 ──────────────────────────────────────────────────────────


def test_normalize_metrics_maps_aliases_and_coerces():
    raw = {"likes": "1,234", "replies": 5, "retweets": 2, "impression_count": "900",
           "unknown_field": 7, "view_count": "not-a-number"}

    metrics = normalize_metrics(raw)

    assert metrics == {"likes": 1234, "comments": 5, "reposts": 2, "views": 900}
    assert "unknown_field" not in metrics


def test_engagement_rate_none_without_views():
    interactions, rate = engagement_of({"likes": 3, "comments": 1})

    assert interactions == 4 and rate is None       # 没 views 不硬算率


def test_engagement_rate_computes_when_views_present():
    interactions, rate = engagement_of({"likes": 5, "reposts": 1, "views": 200})

    assert interactions == 6 and rate == 0.03


def test_post_analytics_requires_ids_and_calculates():
    snap = PostAnalytics(post_id="p1", platform="x", metrics={"likes": 2, "views": 10})

    assert snap.engagement == 2 and snap.engagement_rate == 0.2
    assert snap.attributed is True and snap.collected_at

    with pytest.raises(ValueError):
        PostAnalytics(post_id="", platform="x")
    with pytest.raises(ValueError):
        PostAnalytics(post_id="p1", platform="")


def test_retweet_snapshot_not_attributed():
    snap = PostAnalytics(post_id="p2", platform="x", is_retweet=True,
                         metrics={"likes": 99999, "views": 1000})

    assert snap.attributed is False                  # 指标属于原作者
    assert snap.engagement == 99999                  # 原始数保留（供回溯）


def test_from_backend_happy_path_and_guards():
    result = {"ok": True, "metrics": {"likes": 3, "replies": 1, "views": 50},
              "is_retweet": False, "publish_time": "Mon Sep 28 22:14:31 +0000 2026"}
    snap = PostAnalytics.from_backend("99", "x", result, content_id="c1",
                                      content_type="thread", source="x_backend")

    assert snap.metrics["comments"] == 1 and snap.publish_time.startswith("Mon Sep")
    assert snap.content_id == "c1" and snap.content_type == "thread"

    with pytest.raises(ValueError):
        PostAnalytics.from_backend("99", "x", {"ok": False, "message": "boom"})
    with pytest.raises(ValueError):
        PostAnalytics.from_backend("99", "x", {"ok": True})  # 无 metrics


# ── Store ───────────────────────────────────────────────────────────────


def make_store(tmp_path):
    return AnalyticsStore(tmp_path / "analytics.sqlite3")


def snap(post_id, collected_at="", **kw):
    defaults = {"post_id": post_id, "platform": "x", "metrics": {"likes": 1, "views": 10}}
    defaults.update(kw)
    if collected_at:
        defaults["collected_at"] = collected_at
    return PostAnalytics(**defaults)


def test_store_records_and_returns_history(tmp_path):
    store = make_store(tmp_path)
    store.record(snap("p1", collected_at="2026-09-01 10:00:00",
                      metrics={"likes": 1, "views": 10}))
    store.record(snap("p1", collected_at="2026-09-02 10:00:00",
                      metrics={"likes": 5, "views": 10}))

    history = store.history("p1")

    assert [s.collected_at for s in history] == ["2026-09-01 10:00:00", "2026-09-02 10:00:00"]
    assert store.latest("p1").metrics["likes"] == 5
    assert store.counts() == {"snapshots": 2, "posts": 1, "retweets": 0}
    store.close()


def test_store_excludes_retweets_by_default(tmp_path):
    store = make_store(tmp_path)
    store.record(snap("mine", collected_at="2026-09-01 10:00:00"))
    store.record(snap("rt", is_retweet=True, collected_at="2026-09-01 11:00:00",
                      metrics={"likes": 99999, "views": 10}))

    assert [s.post_id for s in store.recent()] == ["mine"]
    assert [s.post_id for s in store.recent(include_retweets=True)] == ["rt", "mine"]
    assert store.counts()["retweets"] == 1
    store.close()


def test_store_recent_dedupes_to_latest_snapshot(tmp_path):
    store = make_store(tmp_path)
    store.record(snap("p1", collected_at="2026-09-01 10:00:00"))
    store.record(snap("p1", collected_at="2026-09-02 10:00:00", metrics={"likes": 7, "views": 10}))
    store.record(snap("p2", collected_at="2026-09-03 10:00:00"))

    recent = store.recent()

    assert {s.post_id for s in recent} == {"p1", "p2"}       # 每 post 只留一条
    assert recent[0].post_id == "p2"                          # 按最新采集时间倒序
    by_post = {s.post_id: s for s in recent}
    assert by_post["p1"].metrics["likes"] == 7                # p1 留的是最新那条快照
    store.close()


def test_store_by_content(tmp_path):
    store = make_store(tmp_path)
    store.record(snap("p1", content_id="c1"))
    store.record(snap("p2", content_id="c1"))
    store.record(snap("p3", content_id="c2"))

    assert len(store.by_content("c1")) == 2
    assert len(store.by_content("c2")) == 1
    store.close()


# ── Collector ───────────────────────────────────────────────────────────


class FakeX:
    configured = True

    def __init__(self, result):
        self.result = result
        self.calls = []

    def analytics(self, post_id):
        self.calls.append(post_id)
        return self.result


def test_collector_collects_x_metrics(tmp_path):
    x = FakeX({"ok": True, "metrics": {"likes": 3, "replies": 1, "views": 60},
               "is_retweet": False, "publish_time": "Mon Sep 28 22:14:31 +0000 2026"})
    collector = AnalyticsCollector(AnalyticsStore(tmp_path / "a.sqlite3"), x=x)

    outcome = collector.collect("2104696280136221102", content_id="c1",
                                content_type="thread")

    assert outcome["ok"] is True and outcome["metrics"]["comments"] == 1
    assert outcome["engagement_rate"] == pytest.approx(4 / 60)
    stored = collector.store.history("2104696280136221102")
    assert stored and stored[0].content_id == "c1" and stored[0].content_type == "thread"


def test_collector_collects_retweet_but_marks_unattributed(tmp_path):
    x = FakeX({"ok": True, "metrics": {"retweets": 12712, "views": 0},
               "is_retweet": True})
    collector = AnalyticsCollector(AnalyticsStore(tmp_path / "a.sqlite3"), x=x)

    outcome = collector.collect("rt1")

    assert outcome["ok"] is True and outcome["attributed"] is False
    assert collector.store.recent() == []           # 默认查询里不出现
    assert collector.store.recent(include_retweets=True)[0].post_id == "rt1"


def test_collector_failure_writes_nothing(tmp_path):
    store = AnalyticsStore(tmp_path / "a.sqlite3")
    collector = AnalyticsCollector(store, x=FakeX({"ok": False, "message": "没有这条"}))

    outcome = collector.collect("nope")

    assert outcome["ok"] is False and "没有这条" in outcome["message"]
    assert store.counts()["snapshots"] == 0


def test_collector_contract_only_platforms_honest(tmp_path):
    collector = AnalyticsCollector(AnalyticsStore(tmp_path / "a.sqlite3"))

    for platform in ("xiaohongshu", "douyin", "bilibili", "wechat_mp", "weibo", "channels"):
        outcome = collector.collect("any", platform)

        assert outcome["ok"] is False
        assert outcome["error_code"] == "NOT_IMPLEMENTED"


def test_collector_without_x_backend_says_so(tmp_path):
    collector = AnalyticsCollector(AnalyticsStore(tmp_path / "a.sqlite3"), x=None)

    outcome = collector.collect("p1")

    assert outcome["ok"] is False and "未配置" in outcome["message"]


def test_collector_unknown_platform_rejected(tmp_path):
    collector = AnalyticsCollector(AnalyticsStore(tmp_path / "a.sqlite3"), x=FakeX({"ok": True}))

    outcome = collector.collect("p1", "kuaishou")

    assert outcome["ok"] is False and "未知平台" in outcome["message"]


# ── 与 Phase 15 发布记录衔接 ────────────────────────────────────────────


def make_published_job(publish_store, content_id="c1", post_id="p100"):
    job, _ = publish_store.enqueue(content_id, "x", fingerprint="fp")
    publish_store.transition(job, "RUNNING")
    publish_store.transition(job, "SUCCEEDED")
    attempt = publish_store.start_attempt(job.id)          # 走真实插入路径
    attempt.finish("SUCCEEDED", provider_request_id=post_id)
    attempt.published_post_id = post_id
    publish_store.save_attempt(attempt)
    return job


def test_collector_finds_published_post_ids(tmp_path):
    publish_store = PublishJobStore(tmp_path / "publish.sqlite3")
    make_published_job(publish_store, content_id="c1", post_id="p100")
    collector = AnalyticsCollector(AnalyticsStore(tmp_path / "a.sqlite3"),
                                   publish_store=publish_store)

    ids = collector.published_post_ids("c1", platform="x")

    assert ids == ["p100"]


def test_collect_content_reads_from_publish_records(tmp_path):
    publish_store = PublishJobStore(tmp_path / "publish.sqlite3")
    make_published_job(publish_store, content_id="c1", post_id="p100")
    x = FakeX({"ok": True, "metrics": {"likes": 2, "views": 20}})
    collector = AnalyticsCollector(AnalyticsStore(tmp_path / "a.sqlite3"), x=x,
                                   publish_store=publish_store)

    outcome = collector.collect_content("c1")

    assert outcome["ok"] is True and outcome["collected"] == 1
    assert collector.store.by_content("c1")[0].post_id == "p100"


def test_collect_content_without_publish_records_says_so(tmp_path):
    """没有成功发布记录时不报假成功（ok=True 却 collected=0）。"""
    publish_store = PublishJobStore(tmp_path / "publish.sqlite3")
    collector = AnalyticsCollector(AnalyticsStore(tmp_path / "a.sqlite3"),
                                   x=FakeX({"ok": True, "metrics": {"views": 1}}),
                                   publish_store=publish_store)

    outcome = collector.collect_content("c1")

    assert outcome["ok"] is False and outcome["collected"] == 0
    assert "无可采集" in outcome["message"]


def test_collect_content_without_publish_store_says_so(tmp_path):
    collector = AnalyticsCollector(AnalyticsStore(tmp_path / "a.sqlite3"),
                                   x=FakeX({"ok": True, "metrics": {"views": 1}}))

    outcome = collector.collect_content("c1")

    assert outcome["ok"] is False and "PublishJobStore" in outcome["message"]
