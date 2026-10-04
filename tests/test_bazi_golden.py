"""Phase 1：golden case 与 differential comparison 测试。"""

import pytest

from engines.bazi.golden import GoldenCase, assert_chart_matches, compare_chart
from tests.test_bazi_engine_contract import FixtureProvider, birth, chart_for


def case(expected=None) -> GoldenCase:
    return GoldenCase(
        case_id="fixture-001",
        birth=birth(),
        expected=expected or {"day_master": "戊"},
        source="local fixture; not an authoritative calculation",
    )


def test_golden_case_requires_identity_source_and_expected_values():
    with pytest.raises(ValueError, match="case_id"):
        GoldenCase("", birth(), {"day_master": "戊"}, "fixture")
    with pytest.raises(ValueError, match="source"):
        GoldenCase("case", birth(), {"day_master": "戊"}, "")
    with pytest.raises(ValueError, match="expected"):
        GoldenCase("case", birth(), {}, "fixture")


def test_compare_chart_returns_no_difference_for_matching_fields():
    chart = chart_for(birth())

    assert compare_chart(chart, case().expected) == []


def test_compare_chart_compares_pillars_as_serializable_values():
    chart = chart_for(birth())

    assert compare_chart(
        chart,
        {
            "pillars": [
                {"name": "year", "heavenly_stem": "甲", "earthly_branch": "子"},
                {"name": "month", "heavenly_stem": "丙", "earthly_branch": "寅"},
                {"name": "day", "heavenly_stem": "戊", "earthly_branch": "午"},
                {"name": "hour", "heavenly_stem": "壬", "earthly_branch": "申"},
            ]
        },
    ) == []


def test_assert_chart_matches_explains_mismatch_and_source():
    chart = FixtureProvider().calculate(birth())

    with pytest.raises(AssertionError, match=r"fixture-001.*local fixture"):
        assert_chart_matches(chart, case({"day_master": "甲"}))
