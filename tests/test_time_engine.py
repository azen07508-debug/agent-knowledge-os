"""Time Engine 的确定性流年测试。"""

from datetime import date

import pytest
import sxtwl

from engines.bazi import BirthInput, SxtwlBaziProvider
from engines.bazi.sxtwl_provider import solar_term_jds
from engines.bazi.time_engine import (
    DayunPolicy,
    liu_month_at,
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


def test_solar_term_jds_are_chronological_and_deduplicated():
    terms = solar_term_jds(2024, 2025)

    assert len(terms) == 49
    assert [jd for jd, _ in terms] == sorted(jd for jd, _ in terms)
    assert len({jd for jd, _ in terms}) == len(terms)


def test_liu_month_at_resolves_target_date_to_solar_term_period():
    assert liu_month_at(chart(), date(2024, 12, 15)).solar_term == "大雪"
    assert liu_month_at(chart(), date(2024, 12, 15)).earthly_branch == "子"
    assert liu_month_at(chart(), date(2024, 5, 10)).solar_term == "立夏"


def test_liu_month_at_uses_previous_year_period_before_lichun():
    assert liu_month_at(chart(), date(2026, 1, 2)).solar_term == "大雪"
    assert liu_month_at(chart(), date(2026, 2, 5)).solar_term == "立春"


@pytest.mark.parametrize(
    "year,first_stem",
    list(zip(range(2024, 2034), "丙戊庚壬甲丙戊庚壬甲", strict=True)),
)
def test_liu_month_stems_match_all_ten_year_stems(year, first_stem):
    contexts = liu_month_contexts(chart(), year)

    assert contexts[0].heavenly_stem == first_stem
    for context in contexts:
        # 取节气后五日，避开节气交接时刻；包含跨年的小寒月。
        day = sxtwl.JD2DD(context.start_jd + 5)
        reference = SxtwlBaziProvider().calculate(
            BirthInput(day.getYear(), day.getMonth(), day.getDay(), 12)
        ).pillars[1]
        assert (context.heavenly_stem, context.earthly_branch) == (
            reference.heavenly_stem, reference.earthly_branch
        )
