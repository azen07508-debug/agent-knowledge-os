"""Phase 22：最终能力（Briefing）——早报 / 多平台生成 / 发布回执 / 晚报。"""

from datetime import datetime

from agents import Briefing, ContentAgent
from runtime.content_store import ContentStore
from runtime.human_review import approve
from runtime.memory_api import MemoryAPI
from runtime.post_analytics import PostAnalytics
from runtime.topic_engine import TopicEngine

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


def build(tmp_path):
    memory = MemoryAPI(vault_path=tmp_path / "vault")
    memory.create("account", "账号画像", ACCOUNT)
    memory.create("strategy", "当前内容策略", STRATEGY)
    store = ContentStore(tmp_path / "content.sqlite3")
    briefing = Briefing(memory=memory, store=store)
    return memory, store, briefing


def candidate(index: int, *, category: str, topic: str) -> dict:
    return {
        "topic": topic,
        "category": category,
        "sources": [f"https://a.com/{index}"],
        "evidence": [{"url": f"https://a.com/{index}", "quote": "热层 3 条规则"}],
        "facts": ["热层 3 条规则"],
        "opinions": [],
        "freshness": datetime.now().strftime("%Y-%m-%d"),
    }


def high_candidates(count: int) -> list[dict]:
    # 分类「记忆系统」的关键词命中账号定位词 → account_fit=HIGH
    return [candidate(i, category="记忆系统", topic=f"记忆分层实测第 {i} 期")
            for i in range(count)]


def low_candidates(count: int) -> list[dict]:
    # 分类「平台运营」不命中、选题与账号文本无共同词 → account_fit=LOW
    return [candidate(100 + i, category="平台运营", topic=f"东京樱花观赏攻略 {i}")
            for i in range(count)]


def seed_analytics(store) -> None:
    for index in range(3):
        store.record(PostAnalytics(
            post_id=f"t{index}", platform="x", content_type="thread",
            metrics={"likes": 10, "views": 100},
            collected_at=f"2026-09-0{index + 1} 10:00:00"))
        store.record(PostAnalytics(
            post_id=f"p{index}", platform="x", content_type="post",
            metrics={"likes": 2, "views": 100},
            collected_at=f"2026-09-0{index + 1} 11:00:00"))


def make_content(memory, store) -> str:
    recommendation = TopicEngine(memory=memory).recommend(
        [candidate(1, category="记忆系统", topic="记忆分层实测")], top_k=1,
    )["recommendations"][0]
    result = ContentAgent(store=store, memory=memory).run(
        "写一条 Thread", {"recommendation": recommendation})
    content_id = result["content"]["id"]
    assert store.get(content_id).status == "REVIEW"   # 人审闸门先拦住
    return content_id


# ── 早上：10 个话题 + 3 个最符合账号定位 ────────────────────────────────


def test_morning_lists_ten_topics_and_top_fit(tmp_path):
    _memory, _store, briefing = build(tmp_path)
    candidates = high_candidates(8) + low_candidates(5)

    result = briefing.morning(candidates, limit=10, top=3)

    assert result["ok"] is True
    assert len(result["topics"]) == 10
    assert len(result["top_fit"]) == 3
    assert all(item["account_fit"] == "HIGH" for item in result["top_fit"])
    assert "10 个话题" in result["summary"] and "3 个最符合" in result["summary"]


def test_morning_without_candidates_says_what_is_missing(tmp_path):
    _memory, _store, briefing = build(tmp_path)

    result = briefing.morning([])

    assert result["ok"] is False
    assert result["topics"] == [] and result["top_fit"] == []
    assert "缺候选选题" in result["summary"]


def test_morning_does_not_pad_when_few_high_fit(tmp_path):
    _memory, _store, briefing = build(tmp_path)

    result = briefing.morning(high_candidates(2) + low_candidates(4), limit=10, top=3)

    assert result["ok"] is True
    assert len(result["top_fit"]) == 2              # 只有 2 个 HIGH 就给 2 个
    assert "不凑数" in result["summary"]


# ── 白天：多平台生成，只生成不改状态 ────────────────────────────────────


def test_generate_renders_versions_without_changing_status(tmp_path):
    _memory, store, briefing = build(tmp_path)
    content_id = make_content(_memory, store)

    result = briefing.generate(content_id)

    assert result["ok"] is True and result["status"] == "REVIEW"
    assert len(result["versions"]) == 4
    assert {item["platform"] for item in result["versions"]} == {"x", "xiaohongshu", "douyin", "bilibili"}
    by_platform = {item["platform"]: item for item in result["versions"]}
    assert by_platform["x"]["ok"] and by_platform["x"]["valid"] and by_platform["x"]["preview"]
    assert by_platform["xiaohongshu"]["ok"] and by_platform["xiaohongshu"]["valid"]
    # 抖音/B站是视频平台：没有媒体文件就如实报契约错误，不假装能发
    for platform in ("douyin", "bilibili"):
        assert by_platform[platform]["ok"] is True        # 渲染成功
        assert by_platform[platform]["valid"] is False     # 契约不过（缺媒体）
        assert any("媒体" in error for error in by_platform[platform]["errors"])
    assert "2/4" in result["summary"]
    assert store.get(content_id).status == "REVIEW"   # 生成不改状态，更不等于发布


def test_generate_reports_unknown_platform_per_item(tmp_path):
    _memory, store, briefing = build(tmp_path)
    content_id = make_content(_memory, store)

    result = briefing.generate(content_id, platforms=("kuaishou", "x"))

    unknown = next(item for item in result["versions"] if item["platform"] == "kuaishou")
    known = next(item for item in result["versions"] if item["platform"] == "x")
    assert unknown["ok"] is False and "未知平台" in unknown["message"]
    assert known["ok"] is True                        # 一个平台出错不拖垮整批
    assert result["ok"] is True


def test_generate_refuses_empty_body(tmp_path):
    from runtime.content_object import ContentObject

    _memory, store, briefing = build(tmp_path)
    obj = ContentObject(topic="还没写正文的选题", core_content="")
    store.save(obj)

    result = briefing.generate(obj.id)

    assert result["ok"] is False and "没有可生成的正文" in result["summary"]


# ── 发布：只有 APPROVED 才发，逐平台如实回执 ─────────────────────────────


def test_publish_refuses_unapproved_content(tmp_path):
    _memory, store, briefing = build(tmp_path)
    content_id = make_content(_memory, store)      # 停在 REVIEW

    result = briefing.publish(content_id)

    assert result["ok"] is False
    assert "只有 APPROVED 才能发布" in result["summary"]
    assert result["results"] == []                  # 连平台回执都不该有


def test_publish_reports_capability_honestly_without_workflow(tmp_path):
    _memory, store, briefing = build(tmp_path)
    content_id = make_content(_memory, store)
    approve(store, content_id, reviewer="admin", note="来源核对无误")

    result = briefing.publish(content_id, platforms=("x", "xiaohongshu"))

    x = next(item for item in result["results"] if item["platform"] == "x")
    xhs = next(item for item in result["results"] if item["platform"] == "xiaohongshu")
    assert result["ok"] is False
    assert "缺 X 发布能力" in x["message"]
    assert "CONTRACT_ONLY" in xhs["message"]        # 六平台不假装发布成功


class FakeXWorkflow:
    def __init__(self):
        self.calls = []

    def publish(self, content_id, dry_run=False):
        self.calls.append({"content_id": content_id, "dry_run": dry_run})
        return {"ok": True, "message": "已发布"}


def test_publish_uses_workflow_for_x_and_refuses_contract_only(tmp_path):
    _memory, store, briefing = build(tmp_path)
    content_id = make_content(_memory, store)
    approve(store, content_id, reviewer="admin", note="来源核对无误")
    workflow = FakeXWorkflow()

    result = briefing.publish(content_id, platforms=("x", "douyin"), x_workflow=workflow)

    x = next(item for item in result["results"] if item["platform"] == "x")
    douyin = next(item for item in result["results"] if item["platform"] == "douyin")
    assert workflow.calls == [{"content_id": content_id, "dry_run": False}]  # 注入即真实发送
    assert x["ok"] is True
    assert douyin["ok"] is False and "CONTRACT_ONLY" in douyin["message"]
    assert result["ok"] is True and "失败 1 个" in result["summary"]


# ── 晚上：表现分析 + 记忆只写 pending 观察 ───────────────────────────────


def test_evening_without_collector_warns_and_reports_no_data(tmp_path):
    from runtime.analytics_store import AnalyticsStore

    memory, _store, briefing = build(tmp_path)
    briefing = Briefing(memory=memory, store=_store,
                        analytics_store=AnalyticsStore(tmp_path / "analytics.sqlite3"))

    result = briefing.evening()

    assert result["ok"] is True and result["has_data"] is False
    assert any("缺采集器" in note for note in result["warnings"])
    assert result["memory_writes"] == 0
    assert "没有可分析的表现数据" in result["summary"]


def test_evening_writes_pending_observations_only(tmp_path):
    from runtime.analytics_store import AnalyticsStore

    memory, _store, briefing = build(tmp_path)
    analytics = AnalyticsStore(tmp_path / "analytics.sqlite3")
    seed_analytics(analytics)
    briefing = Briefing(memory=memory, store=_store, analytics_store=analytics)

    result = briefing.evening()

    assert result["ok"] is True and result["has_data"] is True
    assert result["memory_writes"] >= 1
    assert result["pending_review"], "刚写进去的观察要出现在晚报待办里"
    for item in result["pending_review"]:
        found = memory.get("insight", item["title"])
        assert found["frontmatter"]["status"] == "pending"   # 不是已验证洞察
    assert result["strategy_candidates"]                      # 只到 PROPOSED，不改 Strategy


def test_evening_can_report_without_writing_memory(tmp_path):
    from runtime.analytics_store import AnalyticsStore

    memory, _store, briefing = build(tmp_path)
    analytics = AnalyticsStore(tmp_path / "analytics.sqlite3")
    seed_analytics(analytics)
    briefing = Briefing(memory=memory, store=_store, analytics_store=analytics)

    result = briefing.evening(write_memory=False)

    assert result["memory_writes"] == 0
    assert any("本次未写记忆" in note for note in result["warnings"])
