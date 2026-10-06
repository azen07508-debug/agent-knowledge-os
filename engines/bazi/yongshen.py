"""扶抑用神的显式近似策略。

用神是流派差异最大的判断之一，这里只实现扶抑法一条口径：先用
``classical_strength_v1`` 得到旺衰标签，再按喜忌给出用神候选。
中和命局不硬凑用神，直接留空并记录冲突。
"""

from __future__ import annotations

from dataclasses import dataclass

from engines.bazi.models import Chart
from engines.bazi.strategies import StrategyContext, StrategyResult
from engines.bazi.strength import GENERATES, ClassicalStrengthPolicy
from engines.bazi.sxtwl_provider import ELEMENTS, HIDDEN_STEMS

ELEMENT_ORDER = ("木", "火", "土", "金", "水")


@dataclass(frozen=True)
class YongshenResult(StrategyResult):
    strength_label: str
    strength_score: float
    favorable: tuple[str, ...]
    unfavorable: tuple[str, ...]
    candidates: tuple[str, ...]


class ClassicalYongshenPolicy:
    """按扶抑法从旺衰结论推导用神候选。"""

    name = "classical_fuyi_yongshen_v1"
    context = StrategyContext(
        school="classical",
        policy=name,
        version="1",
        assumptions=(
            "按扶抑法：身强喜克泄耗，身弱喜生扶",
            "用神候选取喜神五行中命局出现次数最少者",
            "旺衰来自 classical_strength_v1，口径变化会改变用神",
            "不处理调候、通关、病药、从格",
        ),
    )

    def calculate(self, chart: Chart) -> YongshenResult:
        strength = ClassicalStrengthPolicy().calculate(chart)
        day_element = ELEMENTS[chart.day_master]
        supporting = {day_element, *(e for e in ELEMENT_ORDER if GENERATES[e] == day_element)}
        counting = {element: 0 for element in ELEMENT_ORDER}
        for pillar in chart.pillars:
            counting[ELEMENTS[pillar.heavenly_stem]] += 1
            for hidden in HIDDEN_STEMS[pillar.earthly_branch]:
                counting[ELEMENTS[hidden]] += 1

        conflicts = ["用神依赖 classical_strength_v1 的近似旺衰结论"]
        if strength.label == "身强":
            favorable_set = set(ELEMENT_ORDER) - supporting
        elif strength.label == "身弱":
            favorable_set = supporting
        else:
            favorable_set = set()
            conflicts.append("中和命局，扶抑法不足以单独确定用神，用神候选留空")

        favorable = tuple(e for e in ELEMENT_ORDER if e in favorable_set)
        unfavorable = tuple(
            e for e in ELEMENT_ORDER if favorable_set and e not in favorable_set
        )
        candidates = ()
        if favorable:
            least = min(counting[element] for element in favorable)
            candidates = tuple(e for e in favorable if counting[e] == least)

        return YongshenResult(
            context=self.context,
            evidence=(
                "classical_strength_v1 的旺衰结论",
                "Chart 天干与地支藏干五行分布",
                "扶抑法喜忌口径",
            ),
            confidence=0.3,
            conflicts=tuple(conflicts),
            approximate=True,
            strength_label=strength.label,
            strength_score=strength.score,
            favorable=favorable,
            unfavorable=unfavorable,
            candidates=candidates,
        )
