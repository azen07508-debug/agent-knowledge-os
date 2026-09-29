"""Phase 19：静态 Dashboard——各 store + 记忆 → 单文件本地 HTML。"""

import json

from runtime import dashboard
from runtime.analytics_store import AnalyticsStore
from runtime.content_object import ContentObject
from runtime.content_store import ContentStore
from runtime.memory_api import MemoryAPI
from runtime.post_analytics import PostAnalytics
from runtime.publish_queue import PublishJobStore
from runtime.research_store import ResearchItem, ResearchStore


def stores(tmp_path):
    return {
        "memory": MemoryAPI(vault_path=tmp_path / "vault"),
        "research_store": ResearchStore(tmp_path / "research.sqlite3"),
        "content_store": ContentStore(tmp_path / "content.sqlite3"),
        "publish_store": PublishJobStore(tmp_path / "publish.sqlite3"),
        "analytics_store": AnalyticsStore(tmp_path / "analytics.sqlite3"),
    }


def gather(built, **context):
    """用测试自己的 store 实例聚合（不触碰项目 data/ 目录）。"""
    return dashboard.collect(memory=built["memory"],
                             research_store=built["research_store"],
                             content_store=built["content_store"],
                             publish_store=built["publish_store"],
                             analytics_store=built["analytics_store"],
                             **context)


def collect(tmp_path):
    built = stores(tmp_path)
    built["memory"].create(
        "account", "账号画像",
        {"账号定位": "AI 记忆系统实测", "目标受众": "开发者", "内容支柱": "项目实测",
         "表达风格": "实测 > 空谈", "长期目标": "沉淀评测方法论", "禁止内容": "收益承诺",
         "平台差异": "X 走 Thread", "账号阶段": "冷启动", "内容领域": "开源知识库"},
    )
    return built, gather(built, limit=20)


# ── 页面与结构 ──────────────────────────────────────────────────────────


def test_collect_covers_all_11_plan_pages(tmp_path):
    _built, data = collect(tmp_path)

    assert list(data["pages"]) == list(dashboard.PAGES)
    for page, sections in data["pages"].items():
        assert sections, f"{page} 页面至少要有 1 个 section"
        for section in sections:
            assert section["columns"] and isinstance(section["rows"], list)
    assert set(data["totals"]) == {"research", "content", "jobs", "snapshots", "insights"}
    assert all(value == 0 for value in data["totals"].values())   # 空库就是 0，不编数


def test_render_is_single_self_contained_html(tmp_path):
    _built, data = collect(tmp_path)

    page = dashboard.render(data)

    assert page.startswith("<!DOCTYPE html>")
    assert page.count('class="nav"') == len(dashboard.PAGES)
    for loader in ("<script src", "<link ", "@import", "fetch(", "XMLHttpRequest"):
        assert loader not in page                      # 不加载任何外部资源
    assert "不联网、不加载外部资源" in page


def test_empty_state_says_so_honestly(tmp_path):
    _built, data = collect(tmp_path)

    page = dashboard.render(data)

    assert "暂无数据" in page                           # 空库显示空态，不放占位数字
    assert "CONTRACT_ONLY" in page                     # Settings 页如实标平台能力


def test_write_creates_file(tmp_path):
    _built, data = collect(tmp_path)
    out = tmp_path / "dash.html"

    path = dashboard.write(out, data)

    assert path == out and path.exists()
    assert path.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


# ── 数据真的流到对应页面 ────────────────────────────────────────────────


def test_each_kind_of_data_reaches_its_page(tmp_path):
    built = stores(tmp_path)
    built["research_store"].save(ResearchItem(
        source="github", url="https://a.com/memory", title="Obsidian 记忆分层实测",
        content="热层放 3 条高频规则。", timestamp="2026-09-29 09:00:00"))
    built["content_store"].save(ContentObject(topic="记忆分层线程", status="REVIEW"))
    built["publish_store"].enqueue("c1", "x", fingerprint="fp")
    built["analytics_store"].record(PostAnalytics(
        post_id="t1", platform="x", content_type="thread",
        metrics={"likes": 10, "views": 100}, collected_at="2026-09-29 10:00:00"))

    data = dashboard.collect(memory=MemoryAPI(vault_path=tmp_path / "vault"),
                             research_store=built["research_store"],
                             content_store=built["content_store"],
                             publish_store=built["publish_store"],
                             analytics_store=built["analytics_store"], limit=20)
    page = dashboard.render(data)

    assert "Obsidian 记忆分层实测" in page               # Research / Dashboard
    assert "记忆分层线程" in page and "REVIEW" in page     # Content / Review
    assert "c1" in page                                  # Calendar / Publish
    assert "t1" in page and "0.1" in page                # Analytics（10/100）
    assert data["totals"] == {"research": 1, "content": 1, "jobs": 1,
                              "snapshots": 1, "insights": 0}


def test_topics_page_runs_local_topic_engine(tmp_path):
    built = stores(tmp_path)
    built["research_store"].save(ResearchItem(
        source="github", url="https://a.com/memory", title="Obsidian 记忆分层实测",
        content="热层放 3 条高频规则，检索延迟从 800ms 降到 120ms。",
        timestamp="2026-09-29 09:00:00"))

    data = dashboard.collect(memory=MemoryAPI(vault_path=tmp_path / "vault"),
                             research_store=built["research_store"],
                             content_store=built["content_store"],
                             publish_store=built["publish_store"],
                             analytics_store=built["analytics_store"])

    topics = {section["title"]: section for section in data["pages"]["Topics"]}
    assert topics["推荐选题"]["count"] >= 1
    assert "Obsidian 记忆分层实测" in str(topics["推荐选题"]["rows"])


def test_hot_section_refuses_to_invent_ranking(tmp_path):
    built = stores(tmp_path)
    built["research_store"].save(ResearchItem(
        source="web", url="https://a.com/1", title="无互动数据的材料",
        content="热层放 3 条高频规则。", timestamp="2026-09-29 09:00:00"))

    data = dashboard.collect(memory=MemoryAPI(vault_path=tmp_path / "vault"),
                             research_store=built["research_store"],
                             content_store=built["content_store"],
                             publish_store=built["publish_store"],
                             analytics_store=built["analytics_store"])
    hot = next(s for s in data["pages"]["Dashboard"] if s["title"] == "热点")

    assert "不编造热度" in hot["note"]                   # 没数据就说没数据


# ── 安全与只读 ──────────────────────────────────────────────────────────


def test_render_escapes_hostile_titles(tmp_path):
    built = stores(tmp_path)
    built["research_store"].save(ResearchItem(
        source="web", url="https://a.com/x", title="<script>alert(1)</script>",
        content="热层放 3 条高频规则。", timestamp="2026-09-29 09:00:00"))

    data = dashboard.collect(memory=MemoryAPI(vault_path=tmp_path / "vault"),
                             research_store=built["research_store"],
                             content_store=built["content_store"],
                             publish_store=built["publish_store"],
                             analytics_store=built["analytics_store"])
    page = dashboard.render(data)

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_collect_never_writes_memory(tmp_path):
    built, _data = collect(tmp_path)
    record = built["memory"].recordObservation(
        topic="content_type:thread", observation="thread 互动更高", evidence="post_ids=t1")
    before = sorted(path.name for path in (tmp_path / "vault").rglob("*.md"))

    dashboard.collect(memory=built["memory"],
                      research_store=built["research_store"],
                      content_store=built["content_store"],
                      publish_store=built["publish_store"],
                      analytics_store=built["analytics_store"])

    after = sorted(path.name for path in (tmp_path / "vault").rglob("*.md"))
    assert after == before
    assert record["ok"] is True


def test_insight_note_shows_pending_status(tmp_path):
    built, _data = collect(tmp_path)
    built["memory"].recordObservation(topic="content_type:thread",
                                      observation="thread 互动更高", evidence="post_ids=t1")

    data = dashboard.collect(memory=built["memory"],
                             research_store=built["research_store"],
                             content_store=built["content_store"],
                             publish_store=built["publish_store"],
                             analytics_store=built["analytics_store"])
    insight = next(s for s in data["pages"]["Dashboard"] if s["title"] == "AI Insight")

    assert insight["count"] == 1
    assert insight["rows"][0][1] == "pending"           # 待 Memory Review，不当已验证


def test_publish_log_section_reads_local_jsonl(tmp_path, monkeypatch):
    log = tmp_path / "publish_log.jsonl"
    log.write_text("\n".join([
        json.dumps({"at": "2026-09-29 10:00:00", "kind": "publish",
                    "job_id": "job-1", "status": "SUCCEEDED", "ok": True}),
        json.dumps({"at": "2026-09-29 10:05:00", "kind": "publish",
                    "job_id": "job-2", "status": "TIMEOUT_UNVERIFIED", "ok": False}),
    ]), encoding="utf-8")
    monkeypatch.setattr(dashboard, "PUBLISH_LOG", log)

    built = stores(tmp_path)
    data = dashboard.collect(memory=built["memory"],
                             research_store=built["research_store"],
                             content_store=built["content_store"],
                             publish_store=built["publish_store"],
                             analytics_store=built["analytics_store"])

    sections = {section["title"]: section for section in data["pages"]["Publish"]}
    log_section = next(s for s in sections.values() if s["title"].startswith("发布日志"))
    assert log_section["count"] == 2
    assert log_section["rows"][0][-1] == "成功"
    assert log_section["rows"][1][-1] == "失败"
