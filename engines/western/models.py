"""西方日月落座契约；未知出生时间保留为 None。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from engines.birth_time import (
    calendar_datetime,
    local_time_to_utc,
    timezone_info,
    validate_location,
)

SIGNS = (
    "白羊座", "金牛座", "双子座", "巨蟹座", "狮子座", "处女座",
    "天秤座", "天蝎座", "射手座", "摩羯座", "水瓶座", "双鱼座",
)
SIGN_NAMES = (
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
)


@dataclass(frozen=True)
class WesternBirthInput:
    year: int
    month: int
    day: int
    hour: int | None = None
    minute: int = 0
    longitude: float | None = None
    latitude: float | None = None
    timezone: str = "Asia/Shanghai"
    gender: str | None = None
    fold: int | None = None

    def __post_init__(self) -> None:
        local = calendar_datetime(
            self.year, self.month, self.day, 0 if self.hour is None else self.hour, self.minute
        )
        if not 1900 <= self.year <= 2100:
            raise ValueError("西方星座首期支持 1900 到 2100 年。")
        validate_location(self.longitude, self.latitude)
        timezone_info(self.timezone)
        if self.gender not in (None, "男", "女", "male", "female"):
            raise ValueError("gender 只能是 男、女、male、female 或 None。")
        if self.hour is None:
            if self.minute != 0 or self.fold is not None:
                raise ValueError("仅知道日期时，请省略 hour、minute 和 fold。")
        else:
            local_time_to_utc(local, self.timezone, self.fold)


@dataclass(frozen=True)
class BodyPosition:
    body: str
    longitude_deg: float | None
    degree_in_sign: float | None
    sign: str | None
    sign_en: str | None
    possible_signs: tuple[str, ...]
    near_boundary: bool


@dataclass(frozen=True)
class WesternChart:
    birth: WesternBirthInput
    sun: BodyPosition
    moon: BodyPosition
    time_precision: str
    instant_utc: str | None
    utc_interval: tuple[str, str] | None
    provider: str
    algorithm_version: str
    zodiac: str
    coordinate_frame: str
    time_model: str
    accuracy_arcminutes: float
    assumptions: tuple[str, ...]

    ascendant: BodyPosition | None = None
    house_system: str = "whole_sign"
    houses: tuple[dict[str, Any], ...] = ()
    planets: tuple[BodyPosition, ...] = ()
    aspects: tuple[dict[str, Any], ...] = ()
    unavailable: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
