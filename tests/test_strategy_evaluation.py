"""多流派本地 golden case 评估。"""

import json

from agents.mingli import Analysis, AnalystAgent
from evaluation.core import EvaluationCase, summarize
from evaluation.custom import load_cases, run_cases
from knowledge.default_rules import default_registry


def test_golden_case_checks_chart_fields_and_preserves_source(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{
        "case_id": "golden-001",
        "source": "local test fixture",
        "input": {"year": 1990, "month": 2, "day": 1, "hour": 12},
        "expected": {
            "question": "事业",
            "provider": "sxtwl",
            "pillars": [
                {"name": "year", "heavenly_stem": "己", "earthly_branch": "巳", "ten_god": "食神", "na_yin": "大林木"},
                {"name": "month", "heavenly_stem": "丁", "earthly_branch": "丑", "ten_god": "比肩", "na_yin": "涧下水"},
                {"name": "day", "heavenly_stem": "丁", "earthly_branch": "酉", "ten_god": "日主", "na_yin": "山下火"},
                {"name": "hour", "heavenly_stem": "丙", "earthly_branch": "午", "ten_god": "劫财", "na_yin": "天河水"},
            ],
            "relations": [{"type": "六害", "branches": ["丑", "午"], "pillars": ["month", "hour"]}],
        },
    }], ensure_ascii=False), encoding="utf-8")

    case = load_cases(path)[0]
    summary = run_cases(AnalystAgent(default_registry()), [case])

    assert summary.results[0].source == "local test fixture"
    assert summary.results[0].actual["provider"] == "sxtwl"
    assert summary.results[0].actual["pillars"][0]["ten_god"] == "食神"
    assert summary.calculation_accuracy == 1.0


def test_behavior_metrics_are_separate_and_missing_source_is_not_authoritative():
    result = summarize([], authoritative=False)
    assert result.authoritative is False
    assert result.strategy_conflict_rate == 0.0
    assert result.evidence_citation_rate == 0.0
    assert result.certainty_violation_rate == 0.0

    case = EvaluationCase("no-source", {"year": 1990, "month": 2, "day": 1, "hour": 12}, {}, "")
    summary = run_cases(AnalystAgent(default_registry()), [case])
    assert summary.authoritative is False
    assert summary.results[0].failure_reason


def test_certainty_violation_is_counted_from_critic_output():
    base = AnalystAgent(default_registry())

    class CertainAgent:
        registry = base.registry

        def analyze(self, chart, question):
            analysis = base.analyze(chart, question)
            return Analysis(analysis.question, analysis.evidence, analysis.conclusion + "一定")

    case = EvaluationCase(
        "dangerous-word", {"year": 1990, "month": 2, "day": 1, "hour": 12},
        {"question": "事业"}, "local fixture",
    )
    summary = run_cases(CertainAgent(), [case])
    assert summary.certainty_violation_rate == 1.0


def test_authoritative_metrics_exclude_missing_source_and_rule_metric_can_be_inapplicable():
    cases = [
        EvaluationCase("authoritative", {"year": 1990, "month": 2, "day": 1, "hour": 12}, {"question": "事业"}, "local"),
        EvaluationCase("unverified", {"year": 1990, "month": 2, "day": 1, "hour": 12}, {"question": "事业"}, ""),
    ]
    summary = run_cases(AnalystAgent(default_registry()), cases)
    assert (summary.total, summary.authoritative_count) == (2, 1)
    assert summary.calculation_accuracy == 0.0
    assert summary.rule_accuracy is None


def test_invalid_case_is_recorded_with_mismatch_without_aborting_batch():
    cases = [
        EvaluationCase("bad", "not-a-dict", {}, "local"),  # type: ignore[arg-type]
        EvaluationCase("good", {"year": 1990, "month": 2, "day": 1, "hour": 12}, {"question": "事业"}, "local"),
    ]
    summary = run_cases(AnalystAgent(default_registry()), cases)
    assert summary.total == 2
    assert "mismatch" in summary.results[0].failure_reason
    assert summary.results[1].case_id == "good"


def test_unknown_expected_field_is_an_explicit_mismatch():
    case = EvaluationCase(
        "unknown-field", {"year": 1990, "month": 2, "day": 1, "hour": 12},
        {"question": "事业", "not_a_metric": True}, "local",
    )
    result = run_cases(AnalystAgent(default_registry()), [case]).results[0]
    assert not result.passed
    assert "mismatch" in result.failure_reason


def test_malformed_expected_question_does_not_abort_following_case():
    cases = [
        EvaluationCase(
            "bad-question", {"year": 1990, "month": 2, "day": 1, "hour": 12},
            {"question": None}, "local",
        ),
        EvaluationCase(
            "good-question", {"year": 1990, "month": 2, "day": 1, "hour": 12},
            {"question": "事业"}, "local",
        ),
    ]
    summary = run_cases(AnalystAgent(default_registry()), cases)
    assert summary.results[0].case_id == "bad-question"
    assert "mismatch" in summary.results[0].failure_reason
    assert summary.results[1].case_id == "good-question"
    assert summary.results[1].failure_reason == ""


def test_non_string_expected_key_is_recorded_as_mismatch():
    case = EvaluationCase(
        "bad-key", {"year": 1990, "month": 2, "day": 1, "hour": 12},
        {"question": "事业", 1: True}, "local",  # type: ignore[dict-item]
    )
    result = run_cases(AnalystAgent(default_registry()), [case]).results[0]
    assert "mismatch" in result.failure_reason
