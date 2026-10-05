"""八字时间轴基础能力：流年和显式的大运策略接口。"""

from __future__ import annotations

from dataclasses import dataclass

import sxtwl

from engines.bazi.models import Chart
from engines.bazi.strategies import ClassicalApproxDayunPolicy, DayunResult, DayunStrategy
from engines.bazi.strategy_registry import StrategyRegistry
from engines.bazi.sxtwl_provider import BRANCHES, STEMS

__all__ = [
    "ClassicalApproxDayunPolicy",
    "DayunPolicy",
    "DayunResult",
    "DayunStrategy",
    "LiuMonthContext",
    "StrategyRegistry",
    "YearContext",
    "liu_month_contexts",
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


@dataclass(frozen=True)
class LiuMonthContext:
    year: int
    month_index: int
    heavenly_stem: str
    earthly_branch: str
    solar_term: str
    start_jd: float
    chart_provider: str


LIU_MONTH_TERMS = (
    (3, "立春"), (5, "惊蛰"), (7, "清明"), (9, "立夏"),
    (11, "芒种"), (13, "小暑"), (15, "立秋"), (17, "白露"),
    (19, "寒露"), (21, "立冬"), (23, "大雪"), (1, "小寒"),
)


def liu_month_contexts(chart: Chart, year: int) -> tuple[LiuMonthContext, ...]:
    if year < 1:
        raise ValueError("year 必须为正整数。")
    terms = {}
    for item in sxtwl.getJieQiByYear(year):
        terms.setdefault(item.jqIndex, item)
    terms[1] = next(item for item in sxtwl.getJieQiByYear(year + 1) if item.jqIndex == 1)
    year_stem = STEMS[(year - 4) % 60 % 10]
    first_stem = ("丙", "戊", "庚", "壬", "甲")[(STEMS.index(year_stem) // 2) % 5]
    result = []
    for month_index, (term_index, term_name) in enumerate(LIU_MONTH_TERMS):
        term = terms[term_index]
        stem = STEMS[(STEMS.index(first_stem) + month_index) % 10]
        branch = BRANCHES[(2 + month_index) % 12]
        result.append(LiuMonthContext(
            year, month_index, stem, branch, term_name, float(term.jd), chart.provider
        ))
    return tuple(result)


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
