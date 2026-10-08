"""MingLi Agent 的应用服务层。

统一编排排盘、证据、Analyst 和 Critic；API/Web 层只调用这里，不直接拼装
命理业务对象。默认不接外部 LLM，保证本地离线可运行。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from typing import Any

from agents.mingli import AnalystAgent, CriticAgent
from agents.report import ReportGenerator
from engines.bazi import BaziCalculator, BirthInput, SxtwlBaziProvider
from engines.bazi.event_window import event_windows
from engines.bazi.strategy_compare import compare_results
from engines.bazi.strategy_registry import StrategyRegistry
from engines.bazi.time_engine import LiuMonthContext, liu_month_at
from engines.ziwei import ZiweiCalculator
from knowledge.default_rules import default_registry
from knowledge.evidence import build_evidence, extract_facts
from runtime.user_memory import UserMemory


@dataclass(frozen=True)
class AnalysisResponse:
    chart: dict[str, Any]
    analysis: dict[str, Any] | None
    critique: dict[str, Any] | None
    strategy: dict[str, Any] | None = None
    conflicts: dict[str, Any] | None = None
    report: str | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MingLiService:
    """本地命理服务；所有输出都保留 provider、规则和证据来源。"""

    def __init__(self, registry=None, memory: UserMemory | None = None) -> None:
        self.calculator = BaziCalculator(SxtwlBaziProvider())
        self.ziwei_calculator = ZiweiCalculator()
        self.memory = memory or UserMemory()
        self.registry = registry or default_registry()
        self.strategy_registry = StrategyRegistry()
        self.analyst = AnalystAgent(self.registry)
        self.critic = CriticAgent(self.registry)
        self.report_generator = ReportGenerator()

    @staticmethod
    def _liu_month(chart, target_date: str | None) -> LiuMonthContext | None:
        if target_date is None:
            return None
        try:
            target = date.fromisoformat(target_date)
        except ValueError as error:
            raise ValueError("target_date 必须为 YYYY-MM-DD 格式。") from error
        return liu_month_at(chart, target)

    @staticmethod
    def _validate_selector(school: str | None, policy: str | None, version: str | None) -> None:
        """school、policy、version 必须同给或同缺，且不得是空白。"""
        selector = (school, policy, version)
        if any(value is None for value in selector) and not all(value is None for value in selector):
            raise ValueError("school、policy、version 必须同时提供，且不能为空或空白。")
        if any(value is not None and not value.strip() for value in selector):
            raise ValueError("school、policy、version 不能为空或空白。")

    def windows(
        self, birth_data: dict[str, Any], target_year: int, relation: str = "六冲"
    ) -> dict[str, Any]:
        """返回指定年份内命中结构关系的流月窗口；只给结构事实，不判吉凶。"""
        chart = self.calculator.calculate_chart(BirthInput(**birth_data))
        found = event_windows(chart, target_year, relation)
        return {
            "relation": relation,
            "windows": [asdict(window) for window in found],
        }

    def ziwei(self, birth_data: dict[str, Any], *, leap_month: str = "split") -> dict[str, Any]:
        """紫微斗数本命盘；只给结构事实，不判吉凶，也不排大限流年。"""
        chart = self.ziwei_calculator.calculate(birth_data, leap_month=leap_month)
        return {"chart": chart.to_dict()}

    def save_profile(
        self,
        user_id: str,
        birth_data: dict[str, Any],
        *,
        school: str | None = None,
        policy: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        """保存出生档案与策略偏好；出生信息先过 BirthInput 校验。"""
        BirthInput(**birth_data)
        self._validate_selector(school, policy, version)
        profile = {"birth": birth_data, "school": school, "policy": policy, "version": version}
        return self.memory.save_profile(user_id, profile)

    def recall(self, user_id: str) -> dict[str, Any] | None:
        """返回出生档案与咨询历史；用户不存在时返回 None。"""
        profile = self.memory.profile(user_id)
        if profile is None:
            return None
        return {"user_id": user_id, "profile": profile, "history": self.memory.history(user_id)}

    def analyze_from_memory(
        self, user_id: str, question: str, *, target_date: str | None = None
    ) -> AnalysisResponse:
        """用已保存的出生档案直接分析，不必再传一次出生信息。"""
        profile = self.memory.profile(user_id)
        if profile is None:
            raise ValueError(f"没有找到 {user_id} 的用户记忆，请先保存出生档案。")
        response = self.analyze(
            profile["birth"],
            question,
            school=profile.get("school"),
            policy=profile.get("policy"),
            version=profile.get("version"),
            target_date=target_date,
        )
        # 命盘可随时重算，只留可复述的结论与 provenance
        self.memory.record(
            user_id,
            {
                "question": question,
                "analysis": response.analysis,
                "report": response.report,
                "strategy": response.strategy,
                "conflicts": response.conflicts,
                "recorded_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        return response

    def analyze(
        self,
        birth_data: dict[str, Any],
        question: str,
        *,
        school: str | None = None,
        policy: str | None = None,
        version: str | None = None,
        target_date: str | None = None,
    ) -> AnalysisResponse:
        if not question.strip():
            raise ValueError("问题不能为空")
        birth = BirthInput(**birth_data)
        chart = self.calculator.calculate_chart(birth)
        liu_month = self._liu_month(chart, target_date)
        self._validate_selector(school, policy, version)

        liu_month_meta = asdict(liu_month) if liu_month is not None else None
        if all(value is None for value in (school, policy, version)):
            return AnalysisResponse(
                chart=chart.to_dict(),
                analysis=None,
                critique=None,
                metadata={
                    "strategy_selection": "required",
                    "message": "未执行策略；请显式选择 school、policy、version。当前无默认策略。",
                    "facts": [
                        fact.__dict__ for fact in extract_facts(chart, liu_month)
                    ],
                    "liu_month": liu_month_meta,
                },
            )

        analysis = self.analyst.analyze(chart, question, liu_month)

        strategy = None
        conflict_report = None
        result = self.strategy_registry.run(
            chart, school=school, policy=policy, version=version
        )
        conflict_report = compare_results((result,))
        evidence = build_evidence(
            chart,
            self.registry,
            topic=question,
            strategy_context=result.context,
            liu_month=liu_month,
        )
        analysis = replace(analysis, evidence=evidence)
        strategy = asdict(result)
        metadata = {
            "strategy_selection": "explicit",
            "selector": {"school": school, "policy": policy, "version": version},
            "liu_month": liu_month_meta,
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
