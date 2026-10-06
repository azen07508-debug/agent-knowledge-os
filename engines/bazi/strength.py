"""日主旺衰的显式近似策略。

旺衰是流派差异显著的判断，这里只提供可复算的五行计数口径，并把口径本身
写进 assumptions；分数是结构计数，不是命主现实中的强弱概率。
"""

from __future__ import annotations

from dataclasses import dataclass

from engines.bazi.models import Chart
from engines.bazi.strategies import StrategyContext, StrategyResult
from engines.bazi.sxtwl_provider import ELEMENTS, HIDDEN_STEMS

GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
PILLAR_NAMES = ("年", "月", "日", "时")


@dataclass(frozen=True)
class StrengthResult(StrategyResult):
    label: str
    score: float
    support: float
    drain: float
    factors: tuple[str, ...]


class ClassicalStrengthPolicy:
    """按生扶与克泄耗计数判定旺衰，月令藏干权重加倍。"""

    name = "classical_strength_v1"
    context = StrategyContext(
        school="classical",
        policy=name,
        version="1",
        assumptions=(
            "按五行生扶与克泄耗计数",
            "月令藏干权重为其他地支的两倍",
            "生扶占比大于等于 0.6 判身强，小于等于 0.4 判身弱",
            "不处理合化、调候、从格等流派差异",
        ),
    )

    def calculate(self, chart: Chart) -> StrengthResult:
        day_element = ELEMENTS[chart.day_master]
        support = 0.0
        drain = 0.0
        factors: list[str] = []

        def add(position: str, element: str, weight: float) -> None:
            nonlocal support, drain
            if element == day_element or GENERATES[element] == day_element:
                support += weight
                role = "生扶"
            else:
                drain += weight
                role = "克泄耗"
            factors.append(f"{position}({element}){role}")

        for index, pillar in enumerate(chart.pillars):
            name = PILLAR_NAMES[index]
            if index != 2:
                add(f"{name}干{pillar.heavenly_stem}", ELEMENTS[pillar.heavenly_stem], 1.0)
            weight = 2.0 if index == 1 else 1.0
            for hidden in HIDDEN_STEMS[pillar.earthly_branch]:
                add(
                    f"{name}支{pillar.earthly_branch}藏{hidden}",
                    ELEMENTS[hidden],
                    weight,
                )

        total = support + drain
        score = round(support / total, 4) if total else 0.0
        if score >= 0.6:
            label = "身强"
        elif score <= 0.4:
            label = "身弱"
        else:
            label = "中和"
        return StrengthResult(
            context=self.context,
            evidence=("Chart 日主", "Chart 天干", "Chart 地支藏干", "月令藏干权重"),
            confidence=0.4,
            conflicts=("旺衰为五行计数近似，未处理合化、调候、从格等流派差异",),
            approximate=True,
            label=label,
            score=score,
            support=round(support, 4),
            drain=round(drain, 4),
            factors=tuple(factors),
        )
