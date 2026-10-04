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
