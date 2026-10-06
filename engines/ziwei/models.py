"""紫微斗数引擎的领域数据模型；只定义契约，不实现历法与安星算法。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from engines.bazi.models import BirthInput
from engines.bazi.strategies import StrategyContext

# 十二宫按「相对命宫的宫位序」排列：命宫顺时针依次为父母、福德……逆时针为兄弟、夫妻……
PALACE_NAMES = (
    "命宫",
    "父母",
    "福德",
    "田宅",
    "官禄",
    "仆役",
    "迁移",
    "疾厄",
    "财帛",
    "子女",
    "夫妻",
    "兄弟",
)


@dataclass(frozen=True)
class Palace:
    """单宫：宫位干支与落在本宫的星曜（主星在前，按安星顺序）。"""

    index: int
    name: str
    heavenly_stem: str
    earthly_branch: str
    stars: tuple[str, ...]


@dataclass(frozen=True)
class ZiweiChart:
    """紫微斗数本命盘；mutagens 是生年四化，键为星曜名。"""

    birth: BirthInput
    palaces: tuple[Palace, ...]
    soul_index: int
    body_index: int
    five_element_class: str
    lunar: tuple[int, int, int, bool]
    mutagens: dict[str, str]
    context: StrategyContext
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
