"""八字时间轴基础能力：流年和显式的大运策略接口。"""

from __future__ import annotations

from dataclasses import dataclass

from engines.bazi.models import Chart
from engines.bazi.strategies import ClassicalApproxDayunPolicy, DayunResult, DayunStrategy
from engines.bazi.sxtwl_provider import BRANCHES, STEMS

__all__ = [
    "ClassicalApproxDayunPolicy",
    "DayunPolicy",
    "DayunResult",
    "DayunStrategy",
    "YearContext",
    "sexagenary_year",
    "year_context",
    "year_contexts",
]


@dataclass(frozen=True)
class YearContext:
    year: int
    heavenly_stem: str
    earthly_branch: str
    sexagenary_index: int
    chart_provider: str


class DayunPolicy:
    """大运计算策略的显式边界；未选择流派前不提供默认顺逆。"""

    name = "unspecified"

    def calculate(self, chart: Chart) -> tuple[dict[str, object], ...]:
        raise NotImplementedError("尚未选择大运顺逆和起运策略。")


def sexagenary_year(year: int) -> tuple[str, str, int]:
    """返回公历年份对应的干支年；立春分界由上层 Chart 日期负责。"""
    index = (year - 4) % 60
    return STEMS[index % 10], BRANCHES[index % 12], index


def year_context(chart: Chart, year: int) -> YearContext:
    stem, branch, index = sexagenary_year(year)
    return YearContext(year, stem, branch, index, chart.provider)


def year_contexts(chart: Chart, start_year: int, end_year: int) -> tuple[YearContext, ...]:
    if start_year > end_year:
        raise ValueError("start_year 不能大于 end_year。")
    return tuple(year_context(chart, year) for year in range(start_year, end_year + 1))
