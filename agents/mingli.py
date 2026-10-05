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

    def __init__(self, registry: RuleRegistry | None = None) -> None:
        self.registry = registry

    def critique(
        self,
        analysis: Analysis,
        *,
        visible_text: str = "",
        conflict_report: object | None = None,
    ) -> Critique:
        issues: list[str] = []
        dangerous_words = ("必然", "一定", "保证", "概率")
        text = "\n".join(
            (
                analysis.conclusion,
                *(match.rule.conclusion for match in analysis.evidence.matches),
                visible_text,
                repr(conflict_report),
            )
        ).replace("证据强度不等同于概率", "")
        found_words = tuple(word for word in dangerous_words if word in text)
        if found_words:
            issues.append(f"结论包含确定性/危险措辞：{'、'.join(found_words)}")
        if not analysis.evidence.matches and analysis.conclusion.startswith("基于"):
            issues.append("结论声称有规则支持，但证据为空")
        if self.registry is not None:
            missing: list[str] = []
            inconsistent: list[str] = []
            for match in analysis.evidence.matches:
                try:
                    registered = self.registry.get(match.rule.id)
                except KeyError:
                    missing.append(match.rule.id)
                else:
                    if registered != match.rule:
                        inconsistent.append(match.rule.id)
            if missing:
                issues.append(f"规则注册表中不存在引用：{'、'.join(sorted(missing))}")
            if inconsistent:
                issues.append(f"证据规则与注册表内容不一致：{'、'.join(sorted(inconsistent))}")
        if analysis.evidence.conflicts:
            issues.append("存在规则冲突，必须向用户披露")
        if any(not match.rule.source.strip() for match in analysis.evidence.matches):
            issues.append("存在缺少来源的规则引用")
        if analysis.evidence.strength < 0.5 and any(
            word in analysis.conclusion for word in ("会", "将", "成功", "失败")
        ):
            issues.append("证据强度较低，不得输出确定性预测")
        return Critique(not issues, tuple(issues))
