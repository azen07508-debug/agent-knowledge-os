"""统一的本地评估数据模型和指标。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    input_data: dict[str, Any]
    expected: dict[str, Any]
    source: str


@dataclass(frozen=True)
class EvaluationResult:
    case_id: str
    passed: bool
    expected: Any
    actual: Any
    error: str = ""
    source: str = ""
    failure_reason: str = ""
    calculation_passed: bool = False
    rule_passed: bool = False
    conflict: bool = False
    evidence_cited: bool = False
    certainty_violation: bool = False
    rule_applicable: bool = False
    calculation_applicable: bool = False


@dataclass(frozen=True)
class EvaluationSummary:
    total: int
    passed: int
    failed: int
    accuracy: float
    results: tuple[EvaluationResult, ...]
    authoritative: bool = True
    calculation_accuracy: float = 0.0
    rule_accuracy: float = 0.0
    agent_behavior_accuracy: float = 0.0
    strategy_conflict_rate: float = 0.0
    evidence_citation_rate: float = 0.0
    certainty_violation_rate: float = 0.0
    authoritative_count: int = 0
    rule_applicable_count: int = 0


def summarize(
    results: list[EvaluationResult] | tuple[EvaluationResult, ...],
    *,
    authoritative: bool | None = None,
) -> EvaluationSummary:
    total = len(results)
    passed = sum(result.passed for result in results)
    values = tuple(results)
    authoritative_results = tuple(result for result in values if result.source.strip())
    metric_results = authoritative_results
    def rate(value: int, denominator: int = len(metric_results)) -> float:
        return round(value / denominator, 4) if denominator else 0.0
    if authoritative is None:
        authoritative = len(authoritative_results) == total
    rule_results = tuple(result for result in metric_results if result.rule_applicable)
    calculation_results = tuple(result for result in metric_results if result.calculation_applicable)
    def rule_rate(value: int) -> float | None:
        return round(value / len(rule_results), 4) if rule_results else None
    return EvaluationSummary(
        total=total,
        passed=passed,
        failed=total - passed,
        accuracy=round(passed / total, 4) if total else 0.0,
        results=values,
        authoritative=authoritative,
        calculation_accuracy=(
            round(sum(result.calculation_passed for result in calculation_results) / len(calculation_results), 4)
            if calculation_results else 0.0
        ),
        rule_accuracy=rule_rate(sum(result.rule_passed for result in rule_results)),
        agent_behavior_accuracy=rate(sum(
            result.evidence_cited and not result.certainty_violation for result in metric_results
        )),
        strategy_conflict_rate=rate(sum(result.conflict for result in metric_results)),
        evidence_citation_rate=rate(sum(result.evidence_cited for result in metric_results)),
        certainty_violation_rate=rate(sum(result.certainty_violation for result in metric_results)),
        authoritative_count=len(authoritative_results),
        rule_applicable_count=len(rule_results),
    )
