"""Time Engine 的确定性流年测试。"""

import pytest

from engines.bazi import BirthInput, SxtwlBaziProvider
from engines.bazi.time_engine import (
    ClassicalApproxDayunPolicy,
    DayunPolicy,
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


def test_classical_approx_dayun_is_explicit_and_traceable():
    value = SxtwlBaziProvider().calculate(BirthInput(1990, 2, 1, 12, gender="男"))
    result = ClassicalApproxDayunPolicy().calculate(value)

    assert len(result) == 8
    assert result[0]["policy"] == "classical_approx_v1"
    assert result[0]["approximate"] is True
    # 1990-02-01 在立春前，年柱属己巳（阴年）；阴年男逆排，故为 backward
    assert result[0]["direction"] == "backward"


def test_classical_approx_dayun_requires_gender():
    with pytest.raises(ValueError, match="gender"):
        ClassicalApproxDayunPolicy().calculate(chart())
