"""日期真黄道下的东方地平交点、整宫/等宫与明确容许度的相位。"""

from __future__ import annotations

import math
from datetime import datetime
from itertools import combinations

import astronomy

from engines.western.models import SIGNS

ASPECTS = ((0, "合相"), (60, "六合"), (90, "刑相"), (120, "拱相"), (180, "冲相"))


def astro_time(instant: datetime) -> astronomy.Time:
    from datetime import UTC

    if instant.tzinfo is None:
        raise ValueError("instant 必须包含时区。")
    t = instant.astimezone(UTC)
    return astronomy.Time.Make(
        t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1_000_000
    )


def ascendant(instant: datetime, longitude: float, latitude: float) -> float:
    """求黄道与地平面的交点，利用恒星时导数选正在升起的东方交点。"""
    if abs(latitude) >= 89:
        raise ValueError("上升与宫位暂不支持纬度绝对值达到 89° 的近极地地点。")
    t = astro_time(instant)
    rotation = astronomy.Rotation_ECT_EQD(t)
    x = astronomy.RotateVector(rotation, astronomy.Vector(1, 0, 0, t))
    y = astronomy.RotateVector(rotation, astronomy.Vector(0, 1, 0, t))
    theta = math.radians((astronomy.SiderealTime(t) * 15 + longitude) % 360)
    phi = math.radians(latitude)
    normal = (math.cos(phi) * math.cos(theta), math.cos(phi) * math.sin(theta), math.sin(phi))
    derivative = (-math.cos(phi) * math.sin(theta), math.cos(phi) * math.cos(theta), 0)

    def dot(v, n):
        return v.x * n[0] + v.y * n[1] + v.z * n[2]

    a, b = dot(x, normal), dot(y, normal)
    if math.hypot(a, b) < 1e-10:
        raise ValueError("该时刻地平面与黄道重合，无法唯一确定上升。")
    angle = math.atan2(-a, b)
    rising = dot(x, derivative) * math.cos(angle) + dot(y, derivative) * math.sin(angle)
    if abs(rising) < 1e-10:
        raise ValueError("该地点此时黄道与地平面相切，无法唯一确定上升。")
    if rising < 0:
        angle += math.pi
    return math.degrees(angle) % 360


def houses(angle: float, system: str, positions: dict[str, float]) -> tuple[dict, ...]:
    if system not in ("whole_sign", "equal"):
        raise ValueError("宫制仅支持 whole_sign（整宫制）或 equal（等宫制）。")
    start = math.floor(angle / 30) * 30 if system == "whole_sign" else angle
    result = []
    for i in range(12):
        cusp = (start + i * 30) % 360
        result.append(
            {
                "number": i + 1,
                "cusp_longitude_deg": cusp,
                "sign": SIGNS[int(cusp // 30)],
                "degree_in_sign": cusp % 30,
                "bodies": [
                    body
                    for body, value in positions.items()
                    if int(((value - start) % 360) // 30) == i
                ],
            }
        )
    return tuple(result)


def aspects(positions: dict[str, float]) -> tuple[dict, ...]:
    result = []
    for (left, a), (right, b) in combinations(positions.items(), 2):
        separation = abs((a - b + 180) % 360 - 180)
        orb_limit = 8.0 if {left, right} & {"sun", "moon"} else 6.0
        for angle, name in ASPECTS:
            orb = abs(separation - angle)
            if orb <= orb_limit:
                result.append(
                    {
                        "bodies": (left, right),
                        "name": name,
                        "angle_deg": angle,
                        "separation_deg": separation,
                        "orb_deg": orb,
                        "orb_limit_deg": orb_limit,
                    }
                )
                break
    return tuple(sorted(result, key=lambda row: row["orb_deg"]))
