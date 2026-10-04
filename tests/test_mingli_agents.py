"""Analyst/Critic 的本地契约测试。"""

from dataclasses import replace

from agents.mingli import AnalystAgent, CriticAgent
from engines.bazi import BirthInput, SxtwlBaziProvider
from knowledge.default_rules import default_registry


def chart():
    return SxtwlBaziProvider().calculate(BirthInput(1990, 2, 1, 12))


def test_analyst_returns_evidence_bounded_conclusion():
    analysis = AnalystAgent(default_registry()).analyze(chart(), "事业")

    assert analysis.question == "事业"
    assert analysis.evidence.topic == "事业"
    assert "不能形成可靠结论" in analysis.conclusion or "结构规则" in analysis.conclusion


def test_critic_flags_deterministic_language():
    analysis = AnalystAgent(default_registry()).analyze(chart(), "事业")
    unsafe = replace(analysis, conclusion="你一定会成功")

    critique = CriticAgent().critique(unsafe)

    assert critique.passed is False
    assert "确定性" in critique.issues[0]


def test_critic_requires_conflict_disclosure():
    analysis = AnalystAgent(default_registry()).analyze(chart(), "事业")
    conflict = replace(analysis, evidence=replace(analysis.evidence, conflicts=(("A", "B"),)))

    critique = CriticAgent().critique(conflict)

    assert critique.passed is False
    assert any("冲突" in issue for issue in critique.issues)
