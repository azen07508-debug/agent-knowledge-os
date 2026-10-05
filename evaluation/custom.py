"""MingLi Agent 自建结构评估集。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
                "pillars": [
                    {"name": p.name, "heavenly_stem": p.heavenly_stem,
                     "earthly_branch": p.earthly_branch, "ten_god": p.ten_god,
                     "na_yin": p.na_yin}
                    for p in chart.pillars
                ],
                "relations": list(chart.relations),
                "evidence_rules": [match.rule.id for match in analysis.evidence.matches],
            }
            expected = {key: value for key, value in case.expected.items() if key != "question"}
            calculation_keys = {"provider", "day_master", "pillars", "relations"}
            calculation_expected = {k: v for k, v in expected.items() if k in calculation_keys}
            rule_expected = {k: v for k, v in expected.items() if k not in calculation_keys}
            calculation_passed = all(actual.get(k) == v for k, v in calculation_expected.items())
            rule_passed = all(actual.get(k) == v for k, v in rule_expected.items())
            cited = bool(analysis.evidence.matches) and all(
                match.rule.source.strip() for match in analysis.evidence.matches
            )
            result_passed = calculation_passed and rule_passed
            results.append(EvaluationResult(
                case.case_id, result_passed, expected, actual,
                source=case.source, calculation_passed=calculation_passed,
                rule_passed=rule_passed, conflict=bool(analysis.evidence.conflicts),
                evidence_cited=cited,
            ))
        except (TypeError, ValueError, RuntimeError) as exc:
            results.append(EvaluationResult(
                case.case_id, False, case.expected, None, str(exc),
                source=case.source, failure_reason=str(exc),
            ))
    return summarize(results)


def load_cases(path: str | Path) -> list[EvaluationCase]:
    """读取本地 JSON fixture；不对来源做外部补全。"""
    payload: list[dict[str, Any]] = json.loads(Path(path).read_text(encoding="utf-8"))
    return [EvaluationCase(
        item["case_id"], item.get("input", item.get("input_data", {})),
        item.get("expected", {}), item.get("source", ""),
    ) for item in payload]
