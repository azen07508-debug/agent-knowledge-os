"""共享的民用时间与地点校验；不应用八字真太阳时修正。"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def calendar_datetime(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    for name, value, low, high in (
        ("year", year, 1, 9999), ("month", month, 1, 12), ("day", day, 1, 31),
        ("hour", hour, 0, 23), ("minute", minute, 0, 59),
    ):
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{name} 必须是 {low} 到 {high} 之间的整数。")
    try:
        return datetime(year, month, day, hour, minute)
    except ValueError as exc:
        raise ValueError(f"出生日期时间无效：{exc}") from exc


def validate_location(longitude: float | None, latitude: float | None) -> None:
    for name, value, limit in (("longitude", longitude, 180), ("latitude", latitude, 90)):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not -limit <= value <= limit or not math.isfinite(value)
        ):
            raise ValueError(f"{name} 必须是 {-limit} 到 {limit} 之间的有限数值。")


def timezone_info(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValueError("timezone 必须是有效的 IANA 时区，例如 Asia/Shanghai。") from exc


def local_time_to_utc(local: datetime, timezone: str, fold: int | None = None) -> datetime:
    """通过 UTC 往返识别 DST 缺口和重复时刻；fold=0/1 选择前/后一次。"""
    if fold is not None and (type(fold) is not int or fold not in (0, 1)):
        raise ValueError("fold 只能是 0、1 或 None。")
    zone = timezone_info(timezone)
    candidates: dict[int, datetime] = {}
    try:
        for choice in (0, 1):
            utc = local.replace(tzinfo=zone, fold=choice).astimezone(UTC)
            if utc.astimezone(zone).replace(tzinfo=None) == local:
                candidates[choice] = utc
    except OverflowError as exc:
        raise ValueError("出生时间换算为 UTC 后超出支持的日期范围。") from exc
    if not candidates:
        raise ValueError("出生时刻在该时区不存在（夏令时或时区跳变），请核对时间。")
    if len(set(candidates.values())) > 1 and fold is None:
        raise ValueError("出生时刻在该时区重复，请用 fold=0 或 fold=1 选择前一次或后一次。")
    return candidates[0 if fold is None else fold]


def local_day_interval(day: date, timezone: str) -> tuple[datetime, datetime]:
    """返回民用日对应的 UTC 半开区间；支持午夜 DST 缺口与整日跳过。"""
    zone = timezone_info(timezone)

    def first_instant(value: date) -> datetime:
        local = datetime.combine(value, datetime.min.time())
        for minute in range(24 * 60):
            candidate = local + timedelta(minutes=minute)
            for fold in (0, 1):
                utc = candidate.replace(tzinfo=zone, fold=fold).astimezone(UTC)
                if utc.astimezone(zone).replace(tzinfo=None) == candidate:
                    return utc
        raise ValueError("出生日期在该时区不存在（整日跳过），请核对日期。")

    try:
        start = first_instant(day)
        # 下一日期可能被整体跳过，但仍需要当前民用日的真实结束时刻。
        end_day = day + timedelta(days=1)
        for _ in range(3):
            try:
                return start, first_instant(end_day)
            except ValueError:
                end_day += timedelta(days=1)
    except OverflowError as exc:
        raise ValueError("出生日期换算超出支持的日期范围。") from exc
    raise ValueError("无法确定该时区的出生日期范围。")


def validate_query_year(year: int, *, maximum: int = 9999) -> None:
    if type(year) is not int or not 1 <= year <= maximum:
        raise ValueError(f"year 必须是 1 到 {maximum} 之间的整数。")
