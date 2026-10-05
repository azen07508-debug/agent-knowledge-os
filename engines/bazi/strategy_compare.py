"""多策略结果的结构化比较与冲突保留。"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any

from engines.bazi.strategies import StrategyResult


@dataclass(frozen=True)
class ConflictSide:
    """冲突一方的 provenance 和结构化结论。"""

    provenance: tuple[str, str, str]
    fingerprint: dict[str, Any]


@dataclass(frozen=True)
class StrategyConflict:
    """两个策略结果之间的可审计差异。"""

    left: ConflictSide
    right: ConflictSide
    differences: dict[str, tuple[Any, Any]]


@dataclass(frozen=True)
class ConflictReport:
    """比较报告：保留全部输入，不对冲突结果投票。"""

    results: tuple[StrategyResult, ...]
    conflicts: tuple[StrategyConflict, ...]
    has_conflict: bool
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


_NON_CONCLUSION_FIELDS = {"context", "evidence", "confidence", "conflicts"}


def compare_results(results: list[StrategyResult] | tuple[StrategyResult, ...]) -> ConflictReport:
    """按结构化结论指纹比较结果，并保留结果原序列。"""

    retained = tuple(results)
    for result in retained:
        context = getattr(result, "context", None)
        if context is None:
            raise ValueError("StrategyResult.context 不能为空。")

    conflicts: list[StrategyConflict] = []
    for index, left_result in enumerate(retained):
        for right_result in retained[index + 1 :]:
            left_fingerprint = _fingerprint(left_result)
            right_fingerprint = _fingerprint(right_result)
            differences = {
                field: (left_fingerprint.get(field), right_fingerprint.get(field))
                for field in left_fingerprint.keys() | right_fingerprint.keys()
                if left_fingerprint.get(field) != right_fingerprint.get(field)
            }
            if differences:
                conflicts.append(
                    StrategyConflict(
                        left=_side(left_result, left_fingerprint),
                        right=_side(right_result, right_fingerprint),
                        differences=differences,
                    )
                )

    summary = "未发现结构化结论冲突。" if not conflicts else f"发现 {len(conflicts)} 组结构化结论冲突；保留全部结果。"
    return ConflictReport(retained, tuple(conflicts), bool(conflicts), summary)


def _fingerprint(result: StrategyResult) -> dict[str, Any]:
    if not is_dataclass(result):
        raise TypeError("StrategyResult 必须是 dataclass 实例。")
    return {
        field.name: _normalize(getattr(result, field.name))
        for field in fields(result)
        if field.name not in _NON_CONCLUSION_FIELDS
    }


def _side(result: StrategyResult, fingerprint: dict[str, Any]) -> ConflictSide:
    context = result.context
    return ConflictSide((context.school, context.policy, context.version), fingerprint)


def _normalize(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _normalize(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return tuple(_normalize(item) for item in value)
    if isinstance(value, list):
        return tuple(_normalize(item) for item in value)
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    return value


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _serialize(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


__all__ = ["ConflictReport", "ConflictSide", "StrategyConflict", "compare_results"]
