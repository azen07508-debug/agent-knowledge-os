"""评估引擎测试。"""

from agents.mingli import AnalystAgent
from evaluation.core import EvaluationCase, EvaluationResult, summarize
from evaluation.custom import run_cases
from knowledge.default_rules import default_registry


def test_summarize_empty_and_nonempty_results():
    assert summarize([]).accuracy == 0.0
    result = summarize([EvaluationResult("a", True, 1, 1), EvaluationResult("b", False, 1, 2)])
    assert (result.total, result.passed, result.failed, result.accuracy) == (2, 1, 1, 0.5)


def test_custom_evaluation_runs_local_chart_and_agent():
    cases = [
        EvaluationCase(
            "chart-001",
            {"year": 1990, "month": 2, "day": 1, "hour": 12},
            {"question": "事业", "provider": "sxtwl", "day_master": "丁"},
            "local fixture",
        )
    ]

    summary = run_cases(AnalystAgent(default_registry()), cases)

    assert summary.total == 1
    assert summary.accuracy == 1.0
