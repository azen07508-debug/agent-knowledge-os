"""策略上下文和结果契约测试。"""

from dataclasses import FrozenInstanceError

import pytest

from engines.bazi import BirthInput, SxtwlBaziProvider
from engines.bazi.strategies import (
    ClassicalApproxDayunPolicy,
    DayunPeriod,
    DayunResult,
    StrategyContext,
    StrategyResult,
)


def chart(*, gender: str | None = "男"):
    return SxtwlBaziProvider().calculate(BirthInput(1990, 2, 1, 12, gender=gender))


def test_strategy_context_requires_school_policy_version():
    for field in ("school", "policy", "version"):
        values = {"school": "classical", "policy": "dayun", "version": "v1"}
        values[field] = ""
        with pytest.raises(ValueError, match=field):
            StrategyContext(**values, assumptions=())


def test_strategy_result_keeps_provenance_and_approximation():
    context = StrategyContext("classical", "dayun", "v1", ("按节气近似",))
    result = StrategyResult(
        context=context,
        evidence=("month pillar",),
        confidence=0.5,
        conflicts=("起运日未精确计算",),
        approximate=True,
    )

    assert result.context is context
    assert result.context.assumptions == ("按节气近似",)
    assert result.evidence == ("month pillar",)
    assert result.confidence == 0.5
    assert result.conflicts == ("起运日未精确计算",)
    assert result.approximate is True
    with pytest.raises(FrozenInstanceError):
        result.approximate = False


def test_dayun_strategy_protocol_result_is_structured():
    strategy = ClassicalApproxDayunPolicy()
    result = strategy.calculate(chart())

    assert strategy.name == "classical_approx_v1"
    assert isinstance(result, DayunResult)
    assert result.context.policy == "classical_approx_v1"
    assert result.approximate is True
    assert result.direction in ("forward", "backward")
    assert result.periods
    assert all(isinstance(period, DayunPeriod) for period in result.periods)


def test_dayun_period_cannot_be_mutated_in_place():
    period = ClassicalApproxDayunPolicy().calculate(chart()).periods[0]

    with pytest.raises(FrozenInstanceError):
        period.heavenly_stem = "乙"


def test_dayun_period_supports_legacy_read_only_mapping_access():
    period = ClassicalApproxDayunPolicy().calculate(chart()).periods[0]

    assert period["index"] == period.index
    assert period["heavenly_stem"] == period.heavenly_stem
    assert period["earthly_branch"] == period.earthly_branch
    with pytest.raises(KeyError):
        period["unknown"]
    with pytest.raises(TypeError):
        period["index"] = 99


def test_dayun_without_gender_is_rejected():
    with pytest.raises(ValueError, match="gender"):
        ClassicalApproxDayunPolicy().calculate(chart(gender=None))
