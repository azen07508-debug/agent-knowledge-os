"""Time Engine 的确定性流年测试。"""

import pytest

from engines.bazi import BirthInput, SxtwlBaziProvider
from engines.bazi.time_engine import DayunPolicy, sexagenary_year, year_contexts


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
