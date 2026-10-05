"""八字时间轴基础能力：流年和显式的大运策略接口。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from engines.bazi.models import Chart
from engines.bazi.sxtwl_provider import BRANCHES, POLARITY, STEMS


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


class ClassicalApproxDayunPolicy(DayunPolicy):
    """传统顺逆与三日折一年规则的显式近似实现。

    这是可替换策略，不宣称覆盖所有流派；起运点按出生时刻到相邻节气
    的日期差估算，真实生产使用前必须用 golden cases 校核。
    """

    name = "classical_approx_v1"

    def calculate(self, chart: Chart) -> tuple[dict[str, object], ...]:
        if chart.birth.gender not in ("男", "女", "male", "female"):
            raise ValueError("计算大运需要 gender；不同流派的顺逆规则必须显式选择。")
        year_stem = chart.pillars[0].heavenly_stem
        male = chart.birth.gender in ("男", "male")
        forward = (POLARITY[year_stem] == "阳") == male
        month_index = _pillar_index(chart.pillars[1].heavenly_stem, chart.pillars[1].earthly_branch)
        direction = 1 if forward else -1
        start_age = _approx_start_age(chart.birth, forward)
        return tuple(
            {
                "sequence": sequence,
                "heavenly_stem": STEMS[(month_index + direction * sequence * 10) % 10],
                "earthly_branch": BRANCHES[(month_index + direction * sequence * 10) % 12],
                "start_age_years": round(start_age + (sequence - 1) * 10, 2),
                "direction": "forward" if forward else "backward",
                "policy": self.name,
                "approximate": True,
            }
            for sequence in range(1, 9)
        )


def _pillar_index(stem: str, branch: str) -> int:
    return next(index for index in range(60) if index % 10 == STEMS.index(stem) and index % 12 == BRANCHES.index(branch))


def _approx_start_age(birth, forward: bool) -> float:
    birth_dt = datetime(birth.year, birth.month, birth.day, birth.hour, birth.minute)
    boundary = datetime(birth.year + (1 if forward else 0), 2, 4)
    if not forward:
        boundary = datetime(birth.year, 2, 4)
        if birth_dt < boundary:
            boundary = datetime(birth.year - 1, 2, 4)
    days = abs((boundary - birth_dt).total_seconds()) / 86400
    return days / 3


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
