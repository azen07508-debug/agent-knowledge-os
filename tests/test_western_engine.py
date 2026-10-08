"""西方日月落座：独立参考星历、交界、时间精度与 provider 契约。"""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import astronomy
import pytest

from engines.western import AstronomyEngineProvider, WesternBirthInput, WesternCalculator
from engines.western.models import SIGNS


class ConstantProvider:
    name = "fixture"
    algorithm_version = "fixture-v1"
    accuracy_arcminutes = 1.0

    def __init__(self, value):
        self.value = value

    def longitudes(self, instant):
        return self.value, self.value


def exact_birth(**values):
    return WesternBirthInput(1990, 2, 1, 12, **values)


@pytest.mark.parametrize("index", range(12))
def test_all_twelve_signs_are_thirty_degree_sectors(index):
    chart = WesternCalculator(ConstantProvider(index * 30 + 15)).calculate(exact_birth())
    assert chart.sun.sign == chart.moon.sign == SIGNS[index]
    assert chart.sun.degree_in_sign == 15


@pytest.mark.parametrize("angle", [0, 359.99, 360, -0.01])
def test_zero_degree_wrap_retains_adjacent_sign_candidates(angle):
    chart = WesternCalculator(ConstantProvider(angle)).calculate(exact_birth())
    assert chart.sun.sign is None
    assert chart.sun.near_boundary is True
    assert set(chart.sun.possible_signs) == {"双鱼座", "白羊座"}


def test_exact_birth_reports_real_provider_and_utc():
    chart = WesternCalculator().calculate(exact_birth())
    assert chart.provider == "astronomy-engine"
    assert chart.algorithm_version.startswith("astronomy-engine-2.1.19-")
    assert chart.zodiac == "tropical"
    assert chart.coordinate_frame == "geocentric_true_ecliptic_of_date"
    assert chart.instant_utc == "1990-02-01T04:00:00+00:00"
    assert chart.sun.sign == "水瓶座"
    assert chart.moon.sign == "白羊座"
    assert chart.utc_interval is None


def test_equivalent_instants_in_different_timezones_match():
    calculator = WesternCalculator()
    shanghai = calculator.calculate(exact_birth())
    utc = calculator.calculate(WesternBirthInput(1990, 2, 1, 4, timezone="UTC"))
    assert shanghai.sun == utc.sun
    assert shanghai.moon == utc.moon


def test_timezone_conversion_can_cross_the_year_boundary():
    chart = WesternCalculator().calculate(WesternBirthInput(
        2024, 1, 1, 0, timezone="Pacific/Kiritimati"
    ))
    assert chart.instant_utc == "2023-12-31T10:00:00+00:00"


def test_march_equinox_uses_astronomy_instead_of_fixed_date_table():
    calculator = WesternCalculator()
    before = calculator.calculate(WesternBirthInput(2024, 3, 20, 1, timezone="UTC"))
    after = calculator.calculate(WesternBirthInput(2024, 3, 20, 5, timezone="UTC"))
    assert before.sun.sign == "双鱼座"
    assert after.sun.sign == "白羊座"


def test_unknown_time_preserves_ambiguity_without_fabricated_longitude():
    chart = WesternCalculator().calculate(WesternBirthInput(2024, 3, 20, timezone="UTC"))
    assert chart.birth.hour is None
    assert chart.time_precision == "day"
    assert chart.instant_utc is None
    assert chart.utc_interval == ("2024-03-20T00:00:00+00:00", "2024-03-21T00:00:00+00:00")
    assert set(chart.sun.possible_signs) == {"双鱼座", "白羊座"}
    assert chart.sun.sign is None
    assert chart.sun.longitude_deg is chart.moon.degree_in_sign is None


def test_unknown_time_retains_moon_ingress_candidates():
    chart = WesternCalculator().calculate(WesternBirthInput(1990, 2, 1, timezone="UTC"))
    assert set(chart.moon.possible_signs) == {"白羊座", "金牛座"}
    assert chart.moon.sign is None


def test_day_precision_includes_both_occurrences_of_dst_repeat():
    chart = WesternCalculator().calculate(WesternBirthInput(
        2024, 11, 3, timezone="America/New_York"
    ))
    start, end = map(datetime.fromisoformat, chart.utc_interval)
    assert (end - start).total_seconds() == 25 * 3600


def test_fold_changes_the_actual_utc_instant_and_moon_longitude():
    calculator = WesternCalculator()
    first = WesternBirthInput(2024, 11, 3, 1, 30, timezone="America/New_York", fold=0)
    left = calculator.calculate(first)
    right = calculator.calculate(replace(first, fold=1))
    assert left.instant_utc != right.instant_utc
    assert left.moon.longitude_deg != right.moon.longitude_deg


def test_geocentric_positions_do_not_apply_place_or_true_solar_time_corrections():
    calculator = WesternCalculator()
    plain = calculator.calculate(exact_birth())
    located = calculator.calculate(exact_birth(longitude=121.5, latitude=31.2))
    assert plain.sun == located.sun and plain.moon == located.moon


@pytest.mark.parametrize("values", [
    {"year": 1899}, {"year": 2101}, {"minute": 15}, {"fold": 0},
    {"timezone": "Invalid/Timezone"}, {"hour": True},
])
def test_western_input_rejects_invalid_date_only_or_range(values):
    with pytest.raises(ValueError):
        WesternBirthInput(**{"year": 1990, "month": 2, "day": 1, **values})


@pytest.mark.parametrize("attribute,value", [
    ("name", ""), ("algorithm_version", ""), ("accuracy_arcminutes", 0),
    ("accuracy_arcminutes", float("nan")),
])
def test_calculator_rejects_missing_provider_provenance(attribute, value):
    provider = ConstantProvider(15)
    setattr(provider, attribute, value)
    with pytest.raises(ValueError, match="provider"):
        WesternCalculator(provider).calculate(exact_birth())


def test_calculator_rejects_nonfinite_provider_position():
    with pytest.raises(ValueError, match="黄经"):
        WesternCalculator(ConstantProvider(float("nan"))).calculate(exact_birth())


def test_real_provider_requires_no_network(monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("offline ephemeris attempted a network request")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    chart = WesternCalculator().calculate(exact_birth())
    assert chart.sun.sign == "水瓶座"


def test_provider_rejects_timezone_naive_instant():
    with pytest.raises(ValueError, match="时区"):
        AstronomyEngineProvider().longitudes(datetime(1990, 2, 1, 4))


REFERENCE = json.loads((Path(__file__).parent / "fixtures" / "western_reference.json").read_text())


@pytest.mark.parametrize("sample", REFERENCE["samples"], ids=lambda row: row["utc"])
def test_real_positions_match_independent_swiss_reference(sample):
    instant = datetime.fromisoformat(sample["utc"]).astimezone(UTC)
    time = astronomy.Time.Make(instant.year, instant.month, instant.day, instant.hour, instant.minute, 0)
    assert time.tt + 2451545.0 == pytest.approx(sample["jd_tt"], abs=1e-8, rel=0)
    chart = WesternCalculator().calculate(WesternBirthInput(
        instant.year, instant.month, instant.day, instant.hour, instant.minute, timezone="UTC"
    ))
    for body in ("sun", "moon"):
        actual = getattr(chart, body).longitude_deg
        expected = sample[f"{body}_longitude_deg"]
        difference = abs((actual - expected + 180) % 360 - 180)
        assert difference <= REFERENCE["tolerance_degrees"]
