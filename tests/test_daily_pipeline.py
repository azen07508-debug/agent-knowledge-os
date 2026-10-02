"""Phase 21：自动化 Agent 的每日流程（DailyPipeline）——一轮跑完并留下记录。"""

from datetime import datetime

import pytest

from agents import ContentAgent, DailyPipeline, FeedbackLoop
from agents.feedback_loop import FAILED, RAN, SKIPPED
from runtime.content_store import ContentStore
from runtime.human_review import approve
from runtime.memory_api import MemoryAPI

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


def build(tmp_path, *, loop=None, **kwargs):
    """默认给一套全新 tmp 存储；测试可用 loop= 注入假 researcher/workflow。"""
    memory = kwargs.pop("memory", None) or MemoryAPI(vault_path=tmp_path / "vault")
    if not memory.list_notes("account"):
        memory.create("account", "账号画像", ACCOUNT)
        memory.create("strategy", "当前内容策略", STRATEGY)
    if loop is None:
        loop = FeedbackLoop(
            memory=memory,
            content_agent=ContentAgent(store=ContentStore(tmp_path / "content.sqlite3"),
                                       memory=memory),
        )
    pipeline = DailyPipeline(loop=loop, memory=memory,
                             log_path=tmp_path / "daily_runs.jsonl", **kwargs)
    return memory, loop, pipeline


class FakeResearcher:
    """不联网的调研替身：把收到的 context 记下来，回一批能进策略引擎的候选。"""

    def __init__(self, boom: bool = False):
        self.boom = boom
        self.last_context = None

    def run(self, task, context=None):
        self.last_context = dict(context or {})
        if self.boom:
            raise RuntimeError("调研通道挂了")
        return {"candidates": [{
            "topic": "Obsidian 记忆分层实测",
            "category": "记忆系统",
            "sources": ["https://a.com/obsidian-memory"],
            "evidence": [{"url": "https://a.com/obsidian-memory",
                          "quote": "热层放 3 条高频规则"}],
            "facts": ["热层放 3 条高频规则"],
            "opinions": [],
            "freshness": datetime.now().strftime("%Y-%m-%d"),
        }], "material_count": 1, "errors": []}


class FakeXWorkflow:
    """X 发布替身：按真实工作流把 APPROVED → SCHEDULED → PUBLISHED。"""

    def __init__(self, store: ContentStore):
        self.store = store
        self.calls = []

    def publish(self, content_id, dry_run=False):
        self.calls.append({"content_id": content_id, "dry_run": dry_run})
        obj = self.store.get(content_id)
        if obj is None or obj.status != "APPROVED":
            return {"ok": False, "message": "只有 APPROVED 才能发布"}
        if not obj.platform_versions:
            obj.fill({"platform_versions": {"X": "Thread"}})   # 与 XWorkflow 同样的前置补齐
        obj.transition("SCHEDULED")
        obj.transition("PUBLISHED")
        self.store.save(obj)
        return {"ok": True, "dry_run": dry_run}


def approved_content(pipeline, tmp_path) -> str:
    """跑一轮离线流程拿一条 REVIEW 内容，再走人审放行 → APPROVED。"""
    pipeline.run("生成内容", {"materials": materials()})
    store = ContentStore(tmp_path / "content.sqlite3")
    review = store.list(status="REVIEW")
    assert review, "人审闸门应该先停住内容"
    approve(store, review[0]["id"], reviewer="admin", note="来源核对无误")
    return review[0]["id"]


def steps_of(result):
    return {step["name"]: step for step in result["loop"]["steps"]}


# ── 默认行为：全本地、留下记录、待办交给人 ──────────────────────────────


def test_default_run_is_offline_and_reports_todo(tmp_path):
    _memory, _loop, pipeline = build(tmp_path)

    result = pipeline.run(None, {"materials": materials()})

    assert result["ok"] is True
    assert result["notes"] == []                       # 没开对外开关就没有额外警告
    steps = steps_of(result)
    assert steps["research"]["status"] == RAN and steps["content"]["status"] == RAN
    assert steps["publish"]["status"] == "gated"       # 人审拦住，不自动过
    joined = " ".join(result["todo"])
    assert "human_review.approve" in joined            # 今天必须人做的事

    lines = (tmp_path / "daily_runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = result["record"]
    assert record["date"] == result["date"] and record["ok"] is True
    assert record["stages"][0]["name"] == "research"
    assert record["duration_ms"] >= 0


def test_channel_is_dropped_without_research_opt_in(tmp_path):
    researcher = FakeResearcher()
    memory = MemoryAPI(vault_path=tmp_path / "vault")
    memory.create("account", "账号画像", ACCOUNT)
    memory.create("strategy", "当前内容策略", STRATEGY)
    loop = FeedbackLoop(memory=memory, researcher=researcher,
                        content_agent=ContentAgent(store=ContentStore(tmp_path / "content.sqlite3"),
                                                   memory=memory))
    _memory, _loop, pipeline = build(tmp_path, loop=loop, memory=memory)  # research=False 默认

    result = pipeline.run(None, {"channel": "github", "materials": materials()})

    assert researcher.last_context.get("channel") is None   # 没开联网就不把 channel 交出去
    assert researcher.last_context.get("materials")         # 本地材料照常可用
    assert steps_of(result)["research"]["status"] == RAN
    assert any("未开启联网研究" in note for note in result["notes"])
    assert any("未开启联网研究" in item for item in result["todo"])


def test_research_opt_in_passes_channel_to_agent(tmp_path):
    researcher = FakeResearcher()
    memory = MemoryAPI(vault_path=tmp_path / "vault")
    memory.create("account", "账号画像", ACCOUNT)
    memory.create("strategy", "当前内容策略", STRATEGY)
    loop = FeedbackLoop(memory=memory, researcher=researcher,
                        content_agent=ContentAgent(store=ContentStore(tmp_path / "content.sqlite3"),
                                                   memory=memory))
    _memory, _loop, pipeline = build(tmp_path, loop=loop, memory=memory, research=True)

    result = pipeline.run(None, {"channel": "github"})

    assert steps_of(result)["research"]["status"] == RAN
    assert researcher.last_context["channel"] == "github"   # 联网调研只在显式开启时发起


def test_research_harvest_failure_marks_stage_failed(tmp_path):
    """调研失败（如检索词 0 结果）要报 FAILED、整轮 ok=False，不能静悄悄当成跑过。"""

    class FailingResearcher(FakeResearcher):
        def run(self, task, context=None):
            self.last_context = dict(context or {})
            return {"candidates": [], "material_count": 0,
                    "errors": ["调研通道返回空结果。（检索词：zzz）"]}

    memory = MemoryAPI(vault_path=tmp_path / "vault")
    memory.create("account", "账号画像", ACCOUNT)
    memory.create("strategy", "当前内容策略", STRATEGY)
    loop = FeedbackLoop(memory=memory, researcher=FailingResearcher(),
                        content_agent=ContentAgent(store=ContentStore(tmp_path / "content.sqlite3"),
                                                   memory=memory))
    _memory, _loop, pipeline = build(tmp_path, loop=loop, memory=memory, research=True)

    result = pipeline.run(None, {"channel": "github"})

    assert steps_of(result)["research"]["status"] == FAILED
    assert result["ok"] is False


# ── 对外开关：发布必须两步确认 ──────────────────────────────────────────


def test_send_without_publish_x_is_config_error(tmp_path):
    with pytest.raises(ValueError, match="publish_x"):
        build(tmp_path, send=True)


def test_publish_x_without_send_keeps_approved_content(tmp_path):
    _memory, _loop, pipeline = build(tmp_path, publish_x=True)
    content_id = approved_content(pipeline, tmp_path)

    result = pipeline.run(None, {"materials": materials()})

    publish = steps_of(result)["publish"]
    assert publish["status"] == SKIPPED and "已过审" in publish["summary"]
    assert ContentStore(tmp_path / "content.sqlite3").get(content_id).status == "APPROVED"
    assert any("演练位" in note for note in result["notes"])
    assert any(item.startswith("[publish]") for item in result["todo"])  # 待发布要交给人


def test_publish_x_with_send_publishes_approved_content(tmp_path):
    workflow = FakeXWorkflow(ContentStore(tmp_path / "content.sqlite3"))
    memory, _loop, pipeline = build(tmp_path, publish_x=True, send=True, x_workflow=workflow)
    content_id = approved_content(pipeline, tmp_path)

    result = pipeline.run(None, {"materials": materials()})

    publish = steps_of(result)["publish"]
    assert publish["status"] == RAN and publish["data"]["published"] == [content_id]
    assert workflow.calls and workflow.calls[0]["dry_run"] is False   # 注入即真实发送
    assert ContentStore(tmp_path / "content.sqlite3").get(content_id).status == "PUBLISHED"
    assert memory.get("strategy")["frontmatter"]["status"] == "active"  # 每日流程也不写策略


def test_publish_failure_is_reported_as_failed(tmp_path):
    class RefusingWorkflow:
        def publish(self, content_id, dry_run=False):
            return {"ok": False, "message": "X 后端未配置"}

    _memory, _loop, pipeline = build(tmp_path, publish_x=True, send=True,
                                     x_workflow=RefusingWorkflow())
    approved_content(pipeline, tmp_path)

    result = pipeline.run(None, {"materials": materials()})

    publish = steps_of(result)["publish"]
    assert publish["status"] == "failed" and "X 后端未配置" in publish["summary"]
    assert result["ok"] is False
    assert any("[失败]" in item for item in result["todo"])


# ── 第二天继续：记录可追加、失败也如实入账 ──────────────────────────────


def test_log_appends_one_record_per_run(tmp_path):
    _memory, _loop, pipeline = build(tmp_path)

    pipeline.run(None, {"materials": materials()})
    pipeline.run(None, {})

    lines = (tmp_path / "daily_runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    import json

    records = [json.loads(line) for line in lines]
    assert all(record["date"] for record in records)
    assert records[1]["todo"] >= 0


def test_failed_stage_is_logged_with_ok_false(tmp_path):
    memory = MemoryAPI(vault_path=tmp_path / "vault")
    memory.create("account", "账号画像", ACCOUNT)
    memory.create("strategy", "当前内容策略", STRATEGY)
    loop = FeedbackLoop(memory=memory, researcher=FakeResearcher(boom=True),
                        content_agent=ContentAgent(store=ContentStore(tmp_path / "content.sqlite3"),
                                                   memory=memory))
    _memory, _loop, pipeline = build(tmp_path, loop=loop, memory=memory)

    result = pipeline.run(None, {"materials": materials()})

    assert result["ok"] is False
    assert steps_of(result)["research"]["status"] == "failed"
    assert any("[失败] research" in item for item in result["todo"])
    import json

    record = json.loads((tmp_path / "daily_runs.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert record["ok"] is False and record["counts"]["failed"] == 1
