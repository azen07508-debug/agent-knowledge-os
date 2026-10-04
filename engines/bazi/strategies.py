"""八字策略的来源、假设和结果契约。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from engines.bazi.models import Chart
from engines.bazi.sxtwl_provider import BRANCHES, STEMS


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


class DayunStrategy(Protocol):
    context: StrategyContext

    def calculate(self, chart: Chart) -> DayunResult:
        """根据命盘计算结构化大运结果。"""


class ClassicalApproxDayunPolicy:
    """按月柱和年干阴阳推导的显式近似大运策略。

    该策略只提供可追溯的序列近似，不声称精确起运日期。
    """

    name = "classical_approx_v1"
    context = StrategyContext(
        school="classical",
        policy=name,
        version="1",
        assumptions=("按月柱顺逆推导", "起运年龄按三天一岁近似", "不计算精确起运时刻"),
    )

    def calculate(self, chart: Chart) -> DayunResult:
        gender = chart.birth.gender
        if gender is None:
            raise ValueError("大运策略需要 gender，不能猜测顺逆。")

        year_stem = chart.pillars[0].heavenly_stem
        month_stem = chart.pillars[1].heavenly_stem
        month_branch = chart.pillars[1].earthly_branch
        yang_year = STEMS.index(year_stem) % 2 == 0
        male = gender in ("男", "male")
        forward = male == yang_year
        direction = "forward" if forward else "backward"
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
        return DayunResult(
            context=self.context,
            evidence=("Chart.birth.gender", "Chart 年柱天干阴阳", "Chart 月柱"),
            confidence=0.5,
            conflicts=("精确起运日期未计算",),
            approximate=True,
            direction=direction,
            start_age=3.0,
            periods=periods,
        )
