"""八字排盘稳定接口。

当前仓库尚未安装或内置天文历 provider，因此默认计算器会明确失败，
不会返回猜测的四柱。真实 provider 接入后只需实现 ``calculate`` 契约。
"""

from __future__ import annotations

from typing import Protocol

from engines.bazi.models import BirthInput, Chart


class EngineUnavailableError(RuntimeError):
    """需要的历法计算 provider 不可用。"""


class BaziProvider(Protocol):
    """第三方或自研排盘算法的最小契约。"""

    name: str
    algorithm_version: str

    def calculate(self, birth: BirthInput) -> Chart:
        """根据出生信息计算命盘。"""


class ProviderCapabilities(Protocol):
    """provider 应声明的计算能力，供上层避免误用。"""

    supports_true_solar_time: bool
    supports_dayun: bool
    supports_relations: bool


class BaziCalculator:
    """对 provider 做统一校验和生命周期封装。"""

    def __init__(self, provider: BaziProvider | None = None) -> None:
        self.provider = provider

    def calculate_chart(self, birth: BirthInput) -> Chart:
        if not isinstance(birth, BirthInput):
            raise TypeError("birth 必须是 BirthInput。")
        if self.provider is None:
            raise EngineUnavailableError(
                "未配置八字历法 provider；当前不会猜测四柱。"
            )
        chart = self.provider.calculate(birth)
        if not isinstance(chart, Chart):
            raise TypeError("BaziProvider.calculate() 必须返回 Chart。")
        if chart.birth != birth:
            raise ValueError("provider 返回的 Chart.birth 与输入不一致。")
        if chart.provider != self.provider.name:
            raise ValueError("Chart.provider 必须与 provider.name 一致。")
        if chart.algorithm_version != self.provider.algorithm_version:
            raise ValueError("Chart.algorithm_version 必须与 provider 版本一致。")
        return chart

    def capabilities(self) -> dict[str, bool]:
        """返回 provider 能力；未声明的能力按 False 处理。"""
        if self.provider is None:
            return {
                "supports_true_solar_time": False,
                "supports_dayun": False,
                "supports_relations": False,
            }
        return {
            name: bool(getattr(self.provider, name, False))
            for name in (
                "supports_true_solar_time",
                "supports_dayun",
                "supports_relations",
            )
        }
