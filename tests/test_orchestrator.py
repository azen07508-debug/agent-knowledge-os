import json

from runtime.orchestrator import Orchestrator


def test_default_stage_has_no_external_side_effects(tmp_path):
    orchestrator = Orchestrator(log_path=tmp_path / "runs.jsonl")
    result = orchestrator.run("PUBLISH_APPROVED")
    assert result["status"] == "skipped"
    assert result["external_side_effects"] == []
    line = (tmp_path / "runs.jsonl").read_text().splitlines()[0]
    assert json.loads(line)["stage"] == "PUBLISH_APPROVED"


def test_unknown_stage_is_recorded_as_failed(tmp_path):
    orchestrator = Orchestrator(log_path=tmp_path / "runs.jsonl")
    result = orchestrator.run("NOT_A_STAGE")
    assert result["status"] == "failed"
    assert "NOT_A_STAGE" in result["error"]


def test_import_stage_requires_explicit_network_flag(tmp_path):
    orchestrator = Orchestrator(log_path=tmp_path / "runs.jsonl")
    result = orchestrator.run("IMPORT_AI_HOT")
    assert result["status"] == "skipped"
    assert "network" in result["message"]


# ── 执行器接线（deps 注入，不碰真实网络/记忆） ──────────────────────────


def test_import_stage_runs_fetch_and_import_when_network_allowed(tmp_path):
    calls = {}

    def fetch():
        calls["fetch"] = True
        return {"asOf": "t", "cursor": "c", "items": []}

    def importer(payload, store):
        calls["import"] = True
        return {"created": 1, "count": 1}

    orchestrator = Orchestrator(
        log_path=tmp_path / "runs.jsonl",
        deps={"fetch_snapshot": fetch, "import_snapshot": importer, "research_store": object()},
    )
    result = orchestrator.run("IMPORT_AI_HOT", allow_network=True)

    assert result["status"] == "ran"
    assert result["external_side_effects"] == ["network"]
    assert calls == {"fetch": True, "import": True}
    assert result["data"]["created"] == 1


def test_research_stage_runs_injected_researcher_with_network_flag(tmp_path):
    class Researcher:
        def run(self, task, context):
            return {"summary": "抓取 3 条材料", "candidates": [1, 2, 3], "query": context.get("query")}

    orchestrator = Orchestrator(log_path=tmp_path / "runs.jsonl",
                                deps={"researcher": Researcher(), "research_query": "ai tools"})
    result = orchestrator.run("RESEARCH", allow_network=True)

    assert result["status"] == "ran"
    assert result["external_side_effects"] == ["network"]
    assert "3" in result["message"]


def test_build_topics_without_candidates_is_skipped(tmp_path):
    orchestrator = Orchestrator(log_path=tmp_path / "runs.jsonl", deps={"candidates": []})
    result = orchestrator.run("BUILD_TOPICS")
    assert result["status"] == "skipped"
    assert "候选" in result["message"]


def test_build_drafts_without_recommendation_is_skipped(tmp_path):
    orchestrator = Orchestrator(log_path=tmp_path / "runs.jsonl")
    result = orchestrator.run("BUILD_DRAFTS")
    assert result["status"] == "skipped"
    assert "recommendation" in result["message"]


def test_checks_stage_reports_missing_platform_posts(tmp_path):
    orchestrator = Orchestrator(
        log_path=tmp_path / "runs.jsonl",
        deps={"contents": [{"id": "a", "status": "REVIEW", "topic": "工具帖", "platform_posts": {}}]},
    )
    result = orchestrator.run("RUN_CHECKS")

    assert result["status"] == "ran"
    assert any("缺平台帖" in item for item in result["data"]["problems"])


def test_review_stage_counts_pending_and_approved(tmp_path):
    orchestrator = Orchestrator(
        log_path=tmp_path / "runs.jsonl",
        deps={"contents": [{"id": "a", "status": "REVIEW"}, {"id": "b", "status": "REVIEW"},
                           {"id": "c", "status": "APPROVED"}]},
    )
    result = orchestrator.run("WAIT_HUMAN_REVIEW")

    assert result["status"] == "ran"
    assert "2" in result["message"] and "1" in result["message"]
    assert result["external_side_effects"] == []


def test_publish_stage_uses_injected_workflow(tmp_path):
    class XWorkflow:
        def __init__(self):
            self.calls = []

        def publish(self, content_id, dry_run=True):
            self.calls.append((content_id, dry_run))
            return {"ok": True, "message": "已发"}

    workflow = XWorkflow()
    orchestrator = Orchestrator(
        log_path=tmp_path / "runs.jsonl",
        deps={"contents": [{"id": "c1", "status": "APPROVED"}], "x_workflow": workflow},
    )
    result = orchestrator.run("PUBLISH_APPROVED", allow_publish=True)

    assert result["status"] == "ran"
    assert result["external_side_effects"] == ["publish"]
    assert workflow.calls == [("c1", False)]
    assert "1" in result["message"]


def test_publish_stage_without_backend_is_honestly_skipped(tmp_path):
    orchestrator = Orchestrator(
        log_path=tmp_path / "runs.jsonl",
        deps={"contents": [{"id": "c1", "status": "APPROVED"}]},
    )
    result = orchestrator.run("PUBLISH_APPROVED", allow_publish=True)

    assert result["status"] == "skipped"
    assert "注入" in result["message"]


def test_collect_stage_without_collector_is_skipped(tmp_path):
    orchestrator = Orchestrator(log_path=tmp_path / "runs.jsonl")
    result = orchestrator.run("COLLECT_ANALYTICS", allow_analytics=True)

    assert result["status"] == "skipped"
    assert "采集器" in result["message"]


def test_insight_stage_records_candidates_and_reports_writes(tmp_path):
    class Agent:
        def run(self, task, context):
            return {"patterns": [{"key": "tool_post"}], "memory_writes": ["w1", "w2"],
                    "summary": "2 组模式"}

    orchestrator = Orchestrator(log_path=tmp_path / "runs.jsonl",
                                deps={"analytics_agent": Agent()})
    result = orchestrator.run("WRITE_INSIGHT_CANDIDATE")

    assert result["status"] == "ran"
    assert "2" in result["message"]
    assert result["external_side_effects"] == []


def test_insight_stage_skips_honestly_without_data(tmp_path):
    class Agent:
        def run(self, task, context):
            return {"patterns": [], "summary": "没有可分析的表现数据"}

    orchestrator = Orchestrator(log_path=tmp_path / "runs.jsonl",
                                deps={"analytics_agent": Agent()})
    result = orchestrator.run("WRITE_INSIGHT_CANDIDATE")

    assert result["status"] == "skipped"
    assert "表现数据" in result["message"]
