"""共享输入：超大值、时区、DST、民用日长短与跳日。"""

from datetime import UTC, date, datetime

import pytest

from engines.bazi import BirthInput
from engines.birth_time import local_day_interval, local_time_to_utc


@pytest.mark.parametrize("values", [
    {"month": 10**30}, {"day": -10**30}, {"hour": 10**30}, {"minute": 10**30},
    {"year": True}, {"month": 2.0}, {"hour": "12"},
    {"longitude": float("nan")}, {"latitude": float("inf")},
    {"longitude": 10**1000}, {"latitude": True},
    {"timezone": "No/Such_Zone"}, {"timezone": ""}, {"timezone": "/etc/passwd"},
    {"fold": True}, {"fold": 2},
])
def test_birth_input_rejects_invalid_components_as_value_error(values):
    birth = {"year": 1990, "month": 2, "day": 1, "hour": 12, **values}
    with pytest.raises(ValueError):
        BirthInput(**birth)


def test_dst_gap_is_rejected():
    with pytest.raises(ValueError, match="不存在"):
        BirthInput(2024, 3, 10, 2, 30, timezone="America/New_York")


def test_dst_ambiguity_requires_explicit_fold():
    with pytest.raises(ValueError, match="fold"):
        BirthInput(2024, 11, 3, 1, 30, timezone="America/New_York")
    local = datetime(2024, 11, 3, 1, 30)
    assert local_time_to_utc(local, "America/New_York", 0) == datetime(2024, 11, 3, 5, 30, tzinfo=UTC)
    assert local_time_to_utc(local, "America/New_York", 1) == datetime(2024, 11, 3, 6, 30, tzinfo=UTC)


@pytest.mark.parametrize("day,hours", [(date(2024, 3, 10), 23), (date(2024, 11, 3), 25)])
def test_day_interval_respects_dst_day_length(day, hours):
    start, end = local_day_interval(day, "America/New_York")
    assert (end - start).total_seconds() == hours * 3600


def test_midnight_gap_starts_at_first_existing_instant():
    start, end = local_day_interval(date(2024, 9, 8), "America/Santiago")
    assert start == datetime(2024, 9, 8, 4, tzinfo=UTC)
    assert (end - start).total_seconds() == 23 * 3600


def test_skipped_date_is_rejected_and_preceding_day_remains_valid():
    with pytest.raises(ValueError, match="整日跳过"):
        local_day_interval(date(2011, 12, 30), "Pacific/Apia")
    start, end = local_day_interval(date(2011, 12, 29), "Pacific/Apia")
    assert (end - start).total_seconds() == 24 * 3600
