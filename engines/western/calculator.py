"""日月落座与未知时间的候选范围；不输出上升、宫位或吉凶解释。"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Protocol

from engines.birth_time import calendar_datetime, local_day_interval, local_time_to_utc
from engines.western.models import SIGN_NAMES, SIGNS, BodyPosition, WesternBirthInput, WesternChart
from engines.western.provider import AstronomyEngineProvider


class WesternProvider(Protocol):
    name: str
    algorithm_version: str
    accuracy_arcminutes: float

    def longitudes(self, instant: datetime) -> tuple[float, float]: ...


def _position(body: str, values: list[float], tolerance: float, exact: bool) -> BodyPosition:
    indexes = []
    near_boundary = False
    for value in values:
        if not math.isfinite(value):
            raise ValueError("provider 返回了无效黄经。")
        value %= 360
        center = int(value // 30)
        choices = [center]
        if value % 30 <= tolerance:
            choices.insert(0, (center - 1) % 12)
            near_boundary = True
        if 30 - value % 30 <= tolerance:
            choices.append((center + 1) % 12)
            near_boundary = True
        indexes.extend(choices)
    candidates = tuple(dict.fromkeys(indexes))
    index = candidates[0] if len(candidates) == 1 else None
    longitude = values[0] % 360 if exact else None
    return BodyPosition(
        body=body,
        longitude_deg=longitude,
        degree_in_sign=longitude % 30 if longitude is not None else None,
        sign=SIGNS[index] if index is not None else None,
        sign_en=SIGN_NAMES[index] if index is not None else None,
        possible_signs=tuple(SIGNS[index] for index in candidates),
        near_boundary=near_boundary,
    )


class WesternCalculator:
    def __init__(self, provider: WesternProvider | None = None) -> None:
        self.provider = provider if provider is not None else AstronomyEngineProvider()

    def calculate(self, birth: WesternBirthInput) -> WesternChart:
        if not isinstance(birth, WesternBirthInput):
            raise TypeError("birth 必须是 WesternBirthInput。")
        provider = self.provider
        if not provider.name or not provider.algorithm_version:
            raise ValueError("provider 必须声明名称和算法版本。")
        if not math.isfinite(provider.accuracy_arcminutes) or provider.accuracy_arcminutes <= 0:
            raise ValueError("provider 必须声明正的计算误差范围。")
        exact = birth.hour is not None
        if exact:
            local = calendar_datetime(birth.year, birth.month, birth.day, birth.hour, birth.minute)
            instant = local_time_to_utc(local, birth.timezone, birth.fold)
            instants = [instant]
            utc_interval = None
        else:
            local = calendar_datetime(birth.year, birth.month, birth.day, 0, 0)
            start, end = local_day_interval(local.date(), birth.timezone)
            # 日月不会在半小时内跨过一个完整星座；采样并纳入终点前一瞬。
            instants = []
            current = start
            while current < end:
                instants.append(current)
                current += timedelta(minutes=30)
            instants.append(end - timedelta(microseconds=1))
            utc_interval = (start.isoformat(), end.isoformat())
        values = [provider.longitudes(instant) for instant in instants]
        tolerance = provider.accuracy_arcminutes / 60
        return WesternChart(
            birth=birth,
            sun=_position("sun", [pair[0] for pair in values], tolerance, exact),
            moon=_position("moon", [pair[1] for pair in values], tolerance, exact),
            time_precision="minute" if exact else "day",
            instant_utc=instants[0].isoformat() if exact else None,
            utc_interval=utc_interval,
            provider=provider.name,
            algorithm_version=provider.algorithm_version,
            zodiac="tropical",
            coordinate_frame="geocentric_true_ecliptic_of_date",
            time_model="UTC approximated as UT1; TT via Espenak-Meeus DeltaT",
            accuracy_arcminutes=provider.accuracy_arcminutes,
            assumptions=(
                "回归黄道：春分点起，每 30° 为一个星座；不按固定公历日期表判断。",
                "地心日月位置；不使用出生地视差，不应用八字真太阳时修正。",
                "UTC 近似 UT1；TT 使用 Espenak-Meeus ΔT 估算。未来 ΔT 的不确定性不包含在标称 1 角分位置误差内。",
                "星座交界在计算误差范围内时返回相邻候选，不强行判定。",
                "仅日期输入按当地民用日每 30 分钟及结束前一瞬计算候选，不补出生时刻。",
                "首期范围 1900–2100 年；不含上升、宫位、相位或解释性结论。",
            ),
        )
