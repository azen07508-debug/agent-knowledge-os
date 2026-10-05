"""MingLi Agent 的应用服务层。

统一编排排盘、证据、Analyst 和 Critic；API/Web 层只调用这里，不直接拼装
命理业务对象。默认不接外部 LLM，保证本地离线可运行。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

from agents.mingli import AnalystAgent, CriticAgent
from agents.report import ReportGenerator
from engines.bazi import BaziCalculator, BirthInput, SxtwlBaziProvider
from engines.bazi.strategy_compare import compare_results
from engines.bazi.strategy_registry import StrategyRegistry
from knowledge.default_rules import default_registry
from knowledge.evidence import build_evidence


@dataclass(frozen=True)
class AnalysisResponse:
    chart: dict[str, Any]
    analysis: dict[str, Any]
    critique: dict[str, Any]
    strategy: dict[str, Any] | None = None
    conflicts: dict[str, Any] | None = None
    report: str | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MingLiService:
    """本地命理服务；所有输出都保留 provider、规则和证据来源。"""

    def __init__(self, registry=None) -> None:
        self.calculator = BaziCalculator(SxtwlBaziProvider())
        self.registry = registry or default_registry()
        self.strategy_registry = StrategyRegistry()
        self.analyst = AnalystAgent(self.registry)
        self.critic = CriticAgent(self.registry)
        self.report_generator = ReportGenerator()

    def analyze(
        self,
        birth_data: dict[str, Any],
        question: str,
        *,
        school: str | None = None,
        policy: str | None = None,
        version: str | None = None,
    ) -> AnalysisResponse:
        birth = BirthInput(**birth_data)
        chart = self.calculator.calculate_chart(birth)
        analysis = self.analyst.analyze(chart, question)
        selector = (school, policy, version)
        if any(value is not None for value in selector) and not all(selector):
            raise ValueError("school、policy、version 必须同时提供。")

        strategy = None
        conflict_report = None
        metadata = {
            "strategy_selection": "required",
            "message": "未执行策略；请显式选择 school、policy、version。当前无默认策略。",
        }
        if all(selector):
            result = self.strategy_registry.run(
                chart, school=school, policy=policy, version=version
            )
            conflict_report = compare_results((result,))
            evidence = build_evidence(
                chart,
                self.registry,
                topic=question,
                strategy_context=result.context,
            )
            analysis = replace(analysis, evidence=evidence)
            strategy = asdict(result)
            metadata = {
                "strategy_selection": "explicit",
                "selector": {"school": school, "policy": policy, "version": version},
            }
        critique = self.critic.critique(analysis)
        return AnalysisResponse(
            chart=chart.to_dict(),
            analysis={
                "question": analysis.question,
                "evidence": analysis.evidence.to_dict(),
                "conclusion": analysis.conclusion,
            },
            critique={"passed": critique.passed, "issues": list(critique.issues)},
            strategy=strategy,
            conflicts=conflict_report.to_dict() if conflict_report else None,
            report=self.report_generator.render(analysis, conflict_report),
            metadata=metadata,
        )
