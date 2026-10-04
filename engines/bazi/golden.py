"""八字 golden case 与 differential comparison 工具。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engines.bazi.models import BirthInput, Chart


@dataclass(frozen=True)
class GoldenCase:
    """固定输入与预期命盘字段；预期数据必须标明来源。"""

    case_id: str
    birth: BirthInput
    expected: dict[str, Any]
    source: str
    note: str = ""

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("GoldenCase 必须有 case_id。")
        if not self.source.strip():
            raise ValueError("GoldenCase 必须标明 source。")
        if not self.expected:
            raise ValueError("GoldenCase 必须至少包含一个 expected 字段。")


def compare_chart(chart: Chart, expected: dict[str, Any]) -> list[str]:
    """比较已计算命盘的明确字段，返回可读差异列表。"""
    differences: list[str] = []
    for field, expected_value in expected.items():
        if field == "pillars":
            actual_value = [
                {
                    "name": pillar.name,
                    "heavenly_stem": pillar.heavenly_stem,
                    "earthly_branch": pillar.earthly_branch,
                }
                for pillar in chart.pillars
            ]
        else:
            actual_value = getattr(chart, field, None)
        if actual_value != expected_value:
            differences.append(f"{field}: expected={expected_value!r}, actual={actual_value!r}")
    return differences


def assert_chart_matches(chart: Chart, case: GoldenCase) -> None:
    """命盘不匹配时抛出包含 case 来源的断言错误。"""
    differences = compare_chart(chart, case.expected)
    if differences:
        detail = "\n".join(f"- {difference}" for difference in differences)
        raise AssertionError(f"golden case {case.case_id} 不匹配（来源：{case.source}）：\n{detail}")
