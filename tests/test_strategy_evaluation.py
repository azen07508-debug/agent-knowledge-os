"""多流派本地 golden case 评估。"""

import json

from agents.mingli import AnalystAgent
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
