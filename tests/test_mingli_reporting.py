"""报告层和安全闸门契约测试。"""

from dataclasses import replace

from agents.mingli import AnalystAgent, CriticAgent
from agents.report import ReportGenerator
from engines.bazi import BirthInput, SxtwlBaziProvider
from engines.bazi.strategies import StrategyContext
from knowledge.default_rules import default_registry


def chart():
    return SxtwlBaziProvider().calculate(BirthInput(1990, 2, 1, 12))


def test_report_has_fixed_sections_and_strategy_metadata():
    context = StrategyContext("classical", "policy-v1", "1.0", ("假设一",))
    analysis = AnalystAgent(default_registry()).analyze(chart(), "事业")
    analysis = replace(analysis, evidence=replace(analysis.evidence, strategy_context=context))

    report = ReportGenerator().render(analysis)

    for section in ("输入口径", "事实", "策略", "规则", "结论", "冲突", "限制"):
        assert f"## {section}" in report
    assert "classical" in report
    assert "policy-v1" in report
    assert "假设一" in report


def test_report_discloses_each_strategy_on_conflict():
    context = StrategyContext("school-a", "policy-a", "1", ())
    analysis = AnalystAgent(default_registry()).analyze(chart(), "事业")
    analysis = replace(analysis, evidence=replace(analysis.evidence, strategy_context=context))
    conflict_report = type("Conflict", (), {
        "has_conflict": True,
        "summary": "发现冲突",
        "results": (),
        "conflicts": (),
    })()

    report = ReportGenerator().render(analysis, conflict_report)

    assert "school-a" in report
    assert "冲突" in report


def test_critic_rejects_all_dangerous_certainty_words():
    analysis = AnalystAgent(default_registry()).analyze(chart(), "事业")
    for word in ("必然", "一定", "保证", "概率"):
        critique = CriticAgent().critique(replace(analysis, conclusion=f"结果{word}发生"))
        assert not critique.passed
        assert any(word in issue for issue in critique.issues)


def test_low_evidence_report_does_not_make_deterministic_prediction():
    analysis = AnalystAgent(default_registry()).analyze(chart(), "事业")
    analysis = replace(
        analysis,
        conclusion="事业会成功",
        evidence=replace(analysis.evidence, strength=0.2),
    )

    report = ReportGenerator().render(analysis)

    assert "事业会成功" not in report
    assert "证据强度较低" in report
