"""大运策略的显式注册与选择。"""

from __future__ import annotations

from collections.abc import Iterable

from engines.bazi.models import Chart
from engines.bazi.strategies import (
    ClassicalApproxDayunPolicy,
    DayunStrategy,
    StrategyContext,
    StrategyResult,
)

StrategyKey = tuple[str, str, str]


class StrategyRegistry:
    """按 ``(school, policy, version)`` 唯一寻址的策略注册表。

    注册表只接受调用方明确给出的 key；不会根据 school 或 policy 猜测版本，
    也不会在缺少 key 时选取默认策略。
    """

    def __init__(self, strategies: Iterable[DayunStrategy] | None = None) -> None:
        self._strategies: dict[StrategyKey, DayunStrategy] = {}
        self.register(ClassicalApproxDayunPolicy())
        for strategy in strategies or ():
            self.register(strategy)

    def register(self, strategy: DayunStrategy) -> None:
        """注册策略；相同 provenance key 不允许覆盖。"""
        key = self._key(strategy.context)
        if key in self._strategies:
            raise ValueError(f"策略已注册：{'/'.join(key)}")
        self._strategies[key] = strategy

    def get(self, school: str, policy: str, version: str) -> DayunStrategy:
        """按完整显式 key 获取策略。"""
        key = (school, policy, version)
        try:
            return self._strategies[key]
        except KeyError as error:
            raise KeyError(f"未找到策略：{'/'.join(key)}") from error

    def list(self) -> tuple[DayunStrategy, ...]:
        """返回当前注册策略的只读快照。"""
        return tuple(self._strategies.values())

    def run(
        self,
        chart: Chart,
        *,
        school: str,
        policy: str,
        version: str,
    ) -> StrategyResult:
        """使用完整显式 key 运行策略，并保留策略自身 provenance。"""
        return self.get(school, policy, version).calculate(chart)

    @staticmethod
    def _key(context: StrategyContext) -> StrategyKey:
        return (context.school, context.policy, context.version)


__all__ = ["StrategyKey", "StrategyRegistry"]
