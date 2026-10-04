"""命理 Analyst/Critic 的本地、可测试实现。"""

from __future__ import annotations

from dataclasses import dataclass

from engines.bazi.models import Chart
from knowledge.evidence import Evidence, build_evidence
from knowledge.rules import RuleRegistry


@dataclass(frozen=True)
class Analysis:
    question: str
    evidence: Evidence
    conclusion: str
    certainty_risk: bool = False


@dataclass(frozen=True)
class Critique:
    passed: bool
    issues: tuple[str, ...]


class AnalystAgent:
    """先构建证据，再生成保守的结构化说明。"""

    def __init__(self, registry: RuleRegistry) -> None:
        self.registry = registry

    def analyze(self, chart: Chart, question: str) -> Analysis:
        if not question.strip():
            raise ValueError("问题不能为空。")
        evidence = build_evidence(chart, self.registry, topic=question)
        if not evidence.matches:
            conclusion = "当前规则库没有匹配到足够结构证据，不能形成可靠结论。"
        else:
            summaries = "；".join(match.rule.conclusion for match in evidence.matches)
            conclusion = f"基于已匹配的结构规则：{summaries}"
        return Analysis(question, evidence, conclusion)


class CriticAgent:
    """检查结论是否越过证据边界。"""

    def critique(self, analysis: Analysis) -> Critique:
        issues: list[str] = []
        rule_ids = {match.rule.id for match in analysis.evidence.matches}
        if "一定" in analysis.conclusion or "必然" in analysis.conclusion:
            issues.append("结论包含确定性预测措辞")
        if not analysis.evidence.matches and analysis.conclusion.startswith("基于"):
            issues.append("结论声称有规则支持，但证据为空")
        if any(rule_id not in rule_ids for rule_id in analysis.evidence.to_dict()["rules"]):
            issues.append("存在无法追溯的规则引用")
        if analysis.evidence.conflicts:
            issues.append("存在规则冲突，必须向用户披露")
        return Critique(not issues, tuple(issues))
