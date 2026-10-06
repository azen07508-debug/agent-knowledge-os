"""八字策略的来源、假设和结果契约。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import sxtwl

from engines.bazi.models import Chart
from engines.bazi.sxtwl_provider import BRANCHES, STEMS, solar_term_jds


@dataclass(frozen=True)
class StrategyContext:
    school: str
    policy: str
    version: str
    assumptions: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("school", "policy", "version"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} 不能为空。")


@dataclass(frozen=True)
class StrategyResult:
    context: StrategyContext
    evidence: tuple[str, ...]
    confidence: float
    conflicts: tuple[str, ...]
    approximate: bool


@dataclass(frozen=True)
class DayunPeriod:
    index: int
    heavenly_stem: str
    earthly_branch: str

    def __getitem__(self, key: str) -> int | str:
        if key not in ("index", "heavenly_stem", "earthly_branch"):
            raise KeyError(key)
        return getattr(self, key)


@dataclass(frozen=True)
class DayunResult(StrategyResult):
    direction: str
    start_age: float
    periods: tuple[DayunPeriod, ...]


class Strategy(Protocol):
    context: StrategyContext

    def calculate(self, chart: Chart) -> StrategyResult:
        """根据命盘计算结构化策略结果。"""


class DayunStrategy(Protocol):
    context: StrategyContext

    def calculate(self, chart: Chart) -> DayunResult:
        """根据命盘计算结构化大运结果。"""


def _jie_terms(year: int) -> tuple[tuple[float, int], ...]:
    """出生前后三年内的“节”（奇数节气序号），按时间升序。"""
    return tuple(
        (jd, index)
        for jd, index in solar_term_jds(year - 1, year, year + 1)
        if index % 2
    )


class _DayunPolicyBase:
    """大运策略公共推导；子类只声明顺逆依据与起运基准两个流派维度。"""

    stem_source = "year"
    start_reference = "directional_jie"

    def calculate(self, chart: Chart) -> DayunResult:
        gender = chart.birth.gender
        if gender is None:
            raise ValueError("大运策略需要 gender，不能猜测顺逆。")

        stem = chart.pillars[0].heavenly_stem if self.stem_source == "year" else chart.pillars[2].heavenly_stem
        yang = STEMS.index(stem) % 2 == 0
        forward = (gender in ("男", "male")) == yang
        direction = "forward" if forward else "backward"

        month_stem = chart.pillars[1].heavenly_stem
        month_branch = chart.pillars[1].earthly_branch
        month_index = next(
            index
            for index in range(60)
            if STEMS[index % 10] == month_stem and BRANCHES[index % 12] == month_branch
        )
        step = 1 if forward else -1
        periods = tuple(
            DayunPeriod(
                index=index,
                heavenly_stem=STEMS[(month_index + step * index) % 10],
                earthly_branch=BRANCHES[(month_index + step * index) % 12],
            )
            for index in range(1, 9)
        )

        birth_jd = sxtwl.toJD(sxtwl.Time(
            chart.birth.year, chart.birth.month, chart.birth.day,
            chart.birth.hour, chart.birth.minute, 0,
        ))
        jies = _jie_terms(chart.birth.year)
        if self.start_reference == "lichun":
            reference_jd = min(
                (jd for jd, index in jies if index == 3),
                key=lambda jd: abs(jd - birth_jd),
            )
        else:
            reaching = [jd for jd, _ in jies if jd > birth_jd] if forward else [
                jd for jd, _ in jies if jd < birth_jd
            ]
            reference_jd = min(reaching) if forward else max(reaching)

        return DayunResult(
            context=self.context,
            evidence=(f"Chart {self.stem_source}柱天干", "Chart 月柱", "Chart.birth.gender", "sxtwl 节气"),
            confidence=0.5,
            conflicts=("起运按出生时刻与节气间隔近似计算", "精确起运时刻未计算"),
            approximate=True,
            direction=direction,
            start_age=round(abs(reference_jd - birth_jd) / 3, 4),
            periods=periods,
        )


class ClassicalApproxDayunPolicy(_DayunPolicyBase):
    """按年干阴阳定顺逆、按方向对应节气定起运的经典近似策略。"""

    name = "classical_approx_v1"
    context = StrategyContext(
        school="classical",
        policy=name,
        version="1",
        assumptions=("顺逆按年干阴阳", "起运取顺行未来节或逆行过去节", "三天折一年近似"),
    )


class DayStemDayunPolicy(_DayunPolicyBase):
    """按日干阴阳定顺逆的流派变体，用于暴露顺逆口径差异。"""

    name = "day_stem_approx_v1"
    stem_source = "day"
    context = StrategyContext(
        school="classical",
        policy=name,
        version="1",
        assumptions=("顺逆按日干阴阳", "起运取顺行未来节或逆行过去节", "三天折一年近似"),
    )


class LichunDayunPolicy(_DayunPolicyBase):
    """以立春为起运基准的流派变体，用于暴露起运口径差异。"""

    name = "lichun_start_approx_v1"
    start_reference = "lichun"
    context = StrategyContext(
        school="classical",
        policy=name,
        version="1",
        assumptions=("顺逆按年干阴阳", "起运基准取最近立春", "三天折一年近似"),
    )
