"""Astronomy Engine 离线适配器；不调用地理查询或外部星历服务。"""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.metadata import version

import astronomy


class AstronomyEngineProvider:
    name = "astronomy-engine"
    algorithm_version = f"astronomy-engine-{version('astronomy-engine')}-western-v2"
    accuracy_arcminutes = 1.0

    def longitudes(self, instant: datetime) -> tuple[float, float]:
        """统一换算 UTC，返回真春分点/真黄道面（日期坐标系）的地心黄经。"""
        if instant.tzinfo is None:
            raise ValueError("instant 必须包含时区。")
        instant = instant.astimezone(UTC)
        time = astronomy.Time.Make(
            instant.year,
            instant.month,
            instant.day,
            instant.hour,
            instant.minute,
            instant.second + instant.microsecond / 1_000_000,
        )
        return astronomy.SunPosition(time).elon, astronomy.EclipticGeoMoon(time).lon

    def planet_longitudes(self, instant: datetime) -> dict[str, float]:
        from engines.western.geometry import astro_time

        time = astro_time(instant)
        names = ("Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")
        return {
            name.lower(): astronomy.Ecliptic(
                astronomy.GeoVector(getattr(astronomy.Body, name), time, True)
            ).elon
            for name in names
        }
