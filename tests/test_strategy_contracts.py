"""策略上下文和结果契约测试。"""

from dataclasses import FrozenInstanceError

import pytest

from engines.bazi import BirthInput, SxtwlBaziProvider
from engines.bazi.strategies import (
    ClassicalApproxDayunPolicy,
    DayStemDayunPolicy,
    DayunPeriod,
    DayunResult,
    LichunDayunPolicy,
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


def test_dayun_approx_start_age_uses_birth_to_term_distance():
    result = ClassicalApproxDayunPolicy().calculate(chart())

    assert result.start_age != 3.0
    assert result.approximate is True
    assert any("节气" in conflict for conflict in result.conflicts)


def test_dayun_start_age_follows_direction_to_reaching_jie():
    male = ClassicalApproxDayunPolicy().calculate(chart(gender="男"))
    female = ClassicalApproxDayunPolicy().calculate(chart(gender="女"))

    # 1990-02-01 在立春前，年干为己（阴年）：阴年男逆行、女顺行。
    assert (male.direction, female.direction) == ("backward", "forward")
    assert male.start_age > 0
    assert female.start_age > 0
    assert male.start_age != female.start_age


def test_day_stem_school_can_flip_dayun_direction():
    target = SxtwlBaziProvider().calculate(BirthInput(1990, 3, 1, 12, gender="男"))

    yearly = ClassicalApproxDayunPolicy().calculate(target)
    daily = DayStemDayunPolicy().calculate(target)

    assert yearly.context.policy == "classical_approx_v1"
    assert daily.context.policy == "day_stem_approx_v1"
    assert (yearly.direction, daily.direction) == ("forward", "backward")


def test_lichun_school_uses_different_start_age_reference():
    target = chart()
    nearest = ClassicalApproxDayunPolicy().calculate(target)
    lichun = LichunDayunPolicy().calculate(target)

    assert lichun.context.policy == "lichun_start_approx_v1"
    assert lichun.approximate is True
    assert lichun.start_age != nearest.start_age
    assert any("立春" in note for note in lichun.context.assumptions)
