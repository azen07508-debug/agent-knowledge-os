"""生成带证据边界的命理分析报告。"""

from __future__ import annotations

from typing import Any

from agents.mingli import Analysis


class ReportGenerator:
    """将分析、策略上下文和冲突报告渲染为固定章节的中文报告。"""

    _sections = ("输入口径", "事实", "策略", "规则", "结论", "冲突", "限制")

    def render(self, analysis: Analysis, conflict_report: Any | None = None) -> str:
        evidence = analysis.evidence
        context = evidence.strategy_context
        lines = [
            f"## 输入口径\n问题：{analysis.question}",
            "## 事实\n" + self._facts(evidence),
            "## 策略\n" + self._strategy(context),
            "## 规则\n" + self._rules(evidence),
            "## 结论\n" + self._conclusion(analysis),
            "## 冲突\n" + self._conflicts(evidence, conflict_report),
            "## 限制\n" + self._limits(evidence),
        ]
        return "\n\n".join(lines)

    @staticmethod
    def _facts(evidence: Any) -> str:
        if not evidence.facts:
            return "无可用事实。"
        return "；".join(f"{fact.type}={fact.value}（来源：{fact.source}）" for fact in evidence.facts)

    @staticmethod
    def _strategy(context: Any | None) -> str:
        if context is None:
            return "未指定流派或策略。"
        assumptions = "、".join(context.assumptions) if context.assumptions else "无"
        return (
            f"流派：{context.school}\n策略：{context.policy}\n版本：{context.version}\n"
            f"assumptions：{assumptions}"
        )

    @staticmethod
    def _rules(evidence: Any) -> str:
        if not evidence.matches:
            return "未匹配规则。"
        return "\n".join(
            f"- {match.rule.id}：{ReportGenerator._safe_text(match.rule.conclusion)}（来源：{match.rule.source}）"
            for match in evidence.matches
        )

    @staticmethod
    def _safe_text(text: str) -> str:
        dangerous = ("必然", "一定", "保证", "概率")
        if any(word in text for word in dangerous):
            return "已拦截危险措辞。"
        return text

    @staticmethod
    def _conclusion(analysis: Analysis) -> str:
        if analysis.evidence.strength < 0.5:
            return "证据强度较低，仅能提供限制说明，不能输出确定性预测。"
        return ReportGenerator._safe_text(analysis.conclusion)

    @staticmethod
    def _conflicts(evidence: Any, conflict_report: Any | None) -> str:
        if conflict_report is not None and getattr(conflict_report, "has_conflict", False):
            strategies = []
            for result in getattr(conflict_report, "results", ()):
                context = result.context
                strategies.append(
                    f"- provenance={context.school}/{context.policy}@{context.version}; "
                    f"evidence={ReportGenerator._safe_text(str(result.evidence))}; "
                    f"confidence={result.confidence}; approximate={result.approximate}; "
                    f"conflicts={ReportGenerator._safe_text(str(result.conflicts))}"
                )
            if not strategies:
                detail = "缺少策略结果，无法声称结果已保留。"
            else:
                detail = "\n".join(strategies)
            differences = getattr(conflict_report, "differences", None)
            if differences is None:
                differences = tuple(
                    getattr(conflict, "differences", {})
                    for conflict in getattr(conflict_report, "conflicts", ())
                )
            summary = ReportGenerator._safe_text(
                str(getattr(conflict_report, "summary", "存在策略冲突"))
            )
            conflict_lines = f"{summary}\n策略：{detail}"
            if differences is not None:
                conflict_lines += f"\ndifferences：{ReportGenerator._safe_text(str(differences))}"
            return conflict_lines
        if evidence.conflicts:
            return "；".join(f"{left} ↔ {right}" for left, right in evidence.conflicts)
        return "未发现冲突。"

    @staticmethod
    def _limits(evidence: Any) -> str:
        return f"证据强度：{evidence.strength}；证据强度不等同于概率。"


__all__ = ["ReportGenerator"]
