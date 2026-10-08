"""Phase 1：八字引擎契约测试。"""

from dataclasses import replace

import pytest

from engines.bazi import BaziCalculator, BirthInput, Chart, EngineUnavailableError
from engines.bazi.models import Pillar


def birth() -> BirthInput:
    return BirthInput(1990, 2, 1, 12, longitude=116.4, latitude=39.9)


def chart_for(value: BirthInput, provider: str = "fixture", version: str = "1.0") -> Chart:
    pillars = tuple(
        Pillar(name=name, heavenly_stem=stem, earthly_branch=branch)
        for name, stem, branch in (
            ("year", "甲", "子"),
            ("month", "丙", "寅"),
            ("day", "戊", "午"),
            ("hour", "壬", "申"),
        )
    )
    return Chart(value, pillars, day_master="戊", provider=provider, algorithm_version=version)


class FixtureProvider:
    name = "fixture"
    algorithm_version = "1.0"

    def calculate(self, value: BirthInput) -> Chart:
        return chart_for(value, self.name, self.algorithm_version)


def test_birth_input_round_trip_and_location():
    value = birth()

    assert value.to_dict()["longitude"] == 116.4
    assert value.to_dict()["timezone"] == "Asia/Shanghai"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"month": 2, "day": 30},
        {"hour": 24},
        {"longitude": 181},
        {"latitude": -91},
        {"gender": "unknown"},
    ],
)
def test_birth_input_rejects_invalid_values(kwargs):
    values = {"year": 1990, "month": 2, "day": 1, "hour": 12}
    values.update(kwargs)

    with pytest.raises(ValueError):
        BirthInput(**values)


def test_calculator_does_not_guess_without_provider():
    with pytest.raises(EngineUnavailableError, match="不会猜测四柱"):
        BaziCalculator().calculate_chart(birth())


def test_calculator_validates_provider_contract():
    calculator = BaziCalculator(FixtureProvider())

    chart = calculator.calculate_chart(birth())

    assert chart.provider == "fixture"
    assert len(chart.pillars) == 4


def test_calculator_rejects_mismatched_chart_metadata():
    class BadProvider(FixtureProvider):
        def calculate(self, value: BirthInput) -> Chart:
            return replace(chart_for(value), provider="other")

    with pytest.raises(ValueError, match=r"provider\.name"):
        BaziCalculator(BadProvider()).calculate_chart(birth())


def test_chart_requires_four_pillars_and_provenance():
    with pytest.raises(ValueError, match="四柱"):
        Chart(birth(), (), provider="fixture", algorithm_version="1.0")

    with pytest.raises(ValueError, match="provider"):
        Chart(birth(), tuple(Pillar("x", "甲", "子") for _ in range(4)), algorithm_version="1.0")


@pytest.mark.parametrize("year", [-10**30, 0, 10000, 10**30])
def test_birth_input_rejects_out_of_range_year_as_value_error(year):
    with pytest.raises(ValueError):
        BirthInput(year, 1, 1, 12)


@pytest.mark.parametrize("year", [1, 9999])
def test_birth_input_accepts_calendar_year_boundaries(year):
    assert BirthInput(year, 1, 1, 12).year == year
