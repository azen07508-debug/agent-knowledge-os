"""Time Engine 的确定性流年测试。"""

import pytest

from engines.bazi import BirthInput, SxtwlBaziProvider
from engines.bazi.time_engine import (
    DayunPolicy,
    liu_month_contexts,
    sexagenary_year,
    year_contexts,
)


def chart():
    return SxtwlBaziProvider().calculate(BirthInput(1990, 2, 1, 12))


def test_sexagenary_year_known_cases():
    assert sexagenary_year(1984) == ("甲", "子", 0)
    assert sexagenary_year(2024) == ("甲", "辰", 40)


def test_year_contexts_are_reproducible_and_provider_traced():
    contexts = year_contexts(chart(), 2024, 2026)
    assert [(item.heavenly_stem, item.earthly_branch) for item in contexts] == [
        ("甲", "辰"), ("乙", "巳"), ("丙", "午")
    ]
    assert all(item.chart_provider == "sxtwl" for item in contexts)


def test_year_contexts_reject_reverse_range():
    with pytest.raises(ValueError, match="start_year"):
        year_contexts(chart(), 2026, 2024)


def test_dayun_policy_does_not_guess():
    with pytest.raises(NotImplementedError, match="顺逆"):
        DayunPolicy().calculate(chart())


def test_liu_month_contexts_use_real_solar_terms():
    contexts = liu_month_contexts(chart(), 2024)

    assert len(contexts) == 12
    assert contexts[0].month_index == 0
    assert contexts[0].solar_term
    assert contexts[0].start_jd < contexts[1].start_jd
    assert contexts[0].chart_provider == "sxtwl"


def test_liu_month_contexts_reject_invalid_year():
    with pytest.raises(ValueError, match="year"):
        liu_month_contexts(chart(), 0)
