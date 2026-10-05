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


def summarize(
    results: list[EvaluationResult] | tuple[EvaluationResult, ...],
    *,
    authoritative: bool | None = None,
) -> EvaluationSummary:
    total = len(results)
    passed = sum(result.passed for result in results)
    values = tuple(results)
    def rate(value: int) -> float:
        return round(value / total, 4) if total else 0.0
    if authoritative is None:
        authoritative = all(result.source.strip() for result in values)
    return EvaluationSummary(
        total=total,
        passed=passed,
        failed=total - passed,
        accuracy=round(passed / total, 4) if total else 0.0,
        results=values,
        authoritative=authoritative,
        calculation_accuracy=rate(sum(result.calculation_passed for result in values)),
        rule_accuracy=rate(sum(result.rule_passed for result in values)),
        agent_behavior_accuracy=rate(sum(
            result.evidence_cited and not result.certainty_violation for result in values
        )),
        strategy_conflict_rate=rate(sum(result.conflict for result in values)),
        evidence_citation_rate=rate(sum(result.evidence_cited for result in values)),
        certainty_violation_rate=rate(sum(result.certainty_violation for result in values)),
    )
