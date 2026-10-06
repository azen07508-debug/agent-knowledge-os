"""事件窗口：按节气流月边界和地支结构关系筛选时间区间。

窗口只是结构事实的时间切片，不携带吉凶判断；每条窗口记录节气边界、
命盘命中支和关系来源，供后续规则或人工复核使用。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import sxtwl

from engines.bazi.models import Chart
from engines.bazi.sxtwl_provider import BRANCH_RELATIONS, branch_relation
from engines.bazi.time_engine import liu_month_contexts

RELATION_SOURCE = "地支关系表（算法定义，待流派解释核校）"


@dataclass(frozen=True)
class EventWindow:
    start: date
    end: date
    month_index: int
    heavenly_stem: str
    earthly_branch: str
    solar_term: str
    matched: tuple[tuple[str, str], ...]
    provider: str
    relation_source: str


def _jd_to_date(jd: float) -> date:
    day = sxtwl.JD2DD(jd)
    return date(day.getYear(), day.getMonth(), day.getDay())


def event_windows(
    chart: Chart, year: int, relation: str = "六冲"
) -> tuple[EventWindow, ...]:
    if relation not in BRANCH_RELATIONS:
        raise ValueError(f"未知关系：{relation}")
    if year < 1:
        raise ValueError("year 必须为正整数。")

    months = liu_month_contexts(chart, year)
    boundaries = [item.start_jd for item in months]
    boundaries.append(liu_month_contexts(chart, year + 1)[0].start_jd)

    natal = tuple(pillar.earthly_branch for pillar in chart.pillars)
    windows = []
    for position, item in enumerate(months):
        matched = tuple(
            dict.fromkeys(
                (relation, branch)
                for branch in natal
                if branch_relation(item.earthly_branch, branch) == relation
            )
        )
        if matched:
            windows.append(
                EventWindow(
                    start=_jd_to_date(item.start_jd),
                    end=_jd_to_date(boundaries[position + 1]),
                    month_index=item.month_index,
                    heavenly_stem=item.heavenly_stem,
                    earthly_branch=item.earthly_branch,
                    solar_term=item.solar_term,
                    matched=matched,
                    provider=item.chart_provider,
                    relation_source=RELATION_SOURCE,
                )
            )
    return tuple(windows)
