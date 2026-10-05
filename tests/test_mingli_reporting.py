"""报告层和安全闸门契约测试。"""

from dataclasses import replace

from agents.mingli import AnalystAgent, CriticAgent
from agents.report import ReportGenerator
from engines.bazi import BirthInput, SxtwlBaziProvider
from engines.bazi.strategies import StrategyContext, StrategyResult
from engines.bazi.strategy_compare import compare_results
from knowledge.default_rules import default_registry
from knowledge.evidence import Fact
from knowledge.rules import RuleRegistry


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
    left_context = StrategyContext("school-a", "policy-a", "1", ())
    right_context = StrategyContext("school-b", "policy-b", "2", ())
    analysis = AnalystAgent(default_registry()).analyze(chart(), "事业")
    analysis = replace(analysis, evidence=replace(analysis.evidence, strategy_context=left_context))
    conflict_report = compare_results(
        (
            StrategyResult(left_context, ("fact-a",), 0.8, ("left-limit",), False),
            StrategyResult(right_context, ("fact-b",), 0.4, ("right-limit",), True),
        )
    )

    report = ReportGenerator().render(analysis, conflict_report)

    assert "school-a" in report and "school-b" in report
    assert "fact-a" in report and "fact-b" in report
    assert "confidence" in report and "approximate" in report
    assert "differences" in report
    assert "冲突" in report


def test_report_honestly_handles_conflict_without_results():
    analysis = AnalystAgent(default_registry()).analyze(chart(), "事业")
    conflict_report = type("Conflict", (), {
        "has_conflict": True, "summary": "发现冲突", "results": (), "conflicts": (),
    })()

    report = ReportGenerator().render(analysis, conflict_report)

    assert "缺少策略结果" in report
    assert "无法声称结果已保留" in report


def test_critic_rejects_all_dangerous_certainty_words():
    analysis = AnalystAgent(default_registry()).analyze(chart(), "事业")
    for word in ("必然", "一定", "保证", "概率"):
        critique = CriticAgent().critique(replace(analysis, conclusion=f"结果{word}发生"))
        assert not critique.passed
        assert any(word in issue for issue in critique.issues)


def test_critic_checks_rules_against_registry_and_visible_text():
    analysis = AnalystAgent(default_registry()).analyze(chart(), "事业")
    rule = default_registry().list()[0]
    analysis = replace(
        analysis,
        evidence=replace(
            analysis.evidence,
            matches=(type("Match", (), {"rule": rule})(),),
        ),
    )
    empty_registry = RuleRegistry()
    critic = CriticAgent(empty_registry)

    critique = critic.critique(analysis, visible_text="规则结论：结果一定发生")

    assert not critique.passed
    assert any("不存在" in issue or "注册" in issue for issue in critique.issues)
    assert any("一定" in issue for issue in critique.issues)


def test_critic_does_not_flag_fixed_probability_disclaimer():
    analysis = AnalystAgent(default_registry()).analyze(chart(), "事业")

    critique = CriticAgent(default_registry()).critique(
        analysis, visible_text="证据强度不等同于概率。"
    )

    assert critique.passed


def test_report_blocks_dangerous_rule_conclusion_text():
    analysis = AnalystAgent(default_registry()).analyze(chart(), "事业")
    rule = default_registry().list()[0]
    dangerous_rule = replace(rule, conclusion="结果一定发生")
    match = type("Match", (), {"rule": dangerous_rule})()
    analysis = replace(analysis, evidence=replace(analysis.evidence, matches=(match,)))

    report = ReportGenerator().render(analysis)

    assert "结果一定发生" not in report
    assert "已拦截危险措辞" in report


def test_report_sanitizes_all_user_visible_external_fields():
    analysis = AnalystAgent(default_registry()).analyze("事业".join(()) or chart(), "问题一定")
    context = StrategyContext("流派一定", "policy保证", "概率", ("假设必然",))
    rule = default_registry().list()[0]
    dangerous_rule = replace(rule, source="来源一定")
    match = type("Match", (), {"rule": dangerous_rule})()
    evidence = replace(
        analysis.evidence,
        facts=(Fact("fact", "值保证", "来源概率"),),
        matches=(match,),
        strategy_context=context,
    )
    report = ReportGenerator().render(replace(analysis, evidence=evidence))

    assert "已拦截危险措辞" in report
    assert "问题一定" not in report
    assert "值保证" not in report
    assert "来源概率" not in report
    assert "流派一定" not in report
    assert "证据强度不等同于概率" in report


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
