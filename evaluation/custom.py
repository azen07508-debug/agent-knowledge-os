"""MingLi Agent 自建结构评估集。"""

from __future__ import annotations

from agents.mingli import AnalystAgent
from engines.bazi import BaziCalculator, BirthInput, SxtwlBaziProvider
from evaluation.core import EvaluationCase, EvaluationResult, EvaluationSummary, summarize


def run_cases(agent: AnalystAgent, cases: list[EvaluationCase]) -> EvaluationSummary:
    results = []
    calculator = BaziCalculator(SxtwlBaziProvider())
    for case in cases:
        try:
            birth = BirthInput(**case.input_data)
            chart = calculator.calculate_chart(birth)
            analysis = agent.analyze(chart, case.expected.get("question", ""))
            actual = {
                "provider": chart.provider,
                "day_master": chart.day_master,
                "evidence_rules": [match.rule.id for match in analysis.evidence.matches],
            }
            expected = {key: value for key, value in case.expected.items() if key != "question"}
            results.append(EvaluationResult(case.case_id, all(actual.get(k) == v for k, v in expected.items()), expected, actual))
        except (TypeError, ValueError, RuntimeError) as exc:
            results.append(EvaluationResult(case.case_id, False, case.expected, None, str(exc)))
    return summarize(results)
