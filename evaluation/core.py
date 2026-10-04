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


@dataclass(frozen=True)
class EvaluationSummary:
    total: int
    passed: int
    failed: int
    accuracy: float
    results: tuple[EvaluationResult, ...]


def summarize(results: list[EvaluationResult] | tuple[EvaluationResult, ...]) -> EvaluationSummary:
    total = len(results)
    passed = sum(result.passed for result in results)
    return EvaluationSummary(
        total=total,
        passed=passed,
        failed=total - passed,
        accuracy=round(passed / total, 4) if total else 0.0,
        results=tuple(results),
    )
