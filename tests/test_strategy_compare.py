"""策略结果比较与冲突报告测试。"""

import json
from dataclasses import replace

import pytest

from engines.bazi.strategies import ClassicalApproxDayunPolicy
from engines.bazi.strategy_compare import compare_results
from tests.test_strategy_contracts import chart


def results():
    result = ClassicalApproxDayunPolicy().calculate(chart())
    return result, replace(result, context=replace(result.context, policy="other"))


def test_same_structured_conclusion_has_no_conflict():
    first, second = results()

    report = compare_results([first, replace(second, direction=first.direction)])

    assert report.has_conflict is False
    assert report.conflicts == ()


def test_different_conclusions_are_retained_without_voting_or_dropping():
    first, second = results()
    second = replace(second, direction="backward" if first.direction == "forward" else "forward")

    report = compare_results([first, second])

    assert report.has_conflict is True
    assert report.results == (first, second)
    assert len(report.conflicts) == 1
    conflict = report.conflicts[0]
    assert conflict.left.provenance == (first.context.school, first.context.policy, first.context.version)
    assert conflict.right.provenance == (second.context.school, second.context.policy, second.context.version)
    assert "direction" in conflict.differences
    assert "多数" not in report.summary


def test_result_without_context_is_rejected():
    first, _ = results()

    with pytest.raises(ValueError, match="context"):
        compare_results([first, replace(first, context=None)])


def test_report_serialization_keeps_assumptions_and_evidence():
    first, _ = results()

    payload = compare_results([first]).to_dict()
    restored = json.loads(json.dumps(payload, ensure_ascii=False))

    assert restored["results"][0]["context"]["assumptions"] == list(first.context.assumptions)
    assert restored["results"][0]["evidence"] == list(first.evidence)
