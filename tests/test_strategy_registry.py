"""显式大运策略注册表测试。"""

import pytest

from engines.bazi import BirthInput, SxtwlBaziProvider
from engines.bazi.strategies import ClassicalApproxDayunPolicy
from engines.bazi.strategy_registry import StrategyRegistry


def chart():
    return SxtwlBaziProvider().calculate(BirthInput(1990, 2, 1, 12, gender="男"))


def test_registry_rejects_duplicate_strategy_key():
    registry = StrategyRegistry()

    with pytest.raises(ValueError, match="已注册"):
        registry.register(ClassicalApproxDayunPolicy())


def test_registry_missing_strategy_has_explicit_error():
    registry = StrategyRegistry()

    with pytest.raises(KeyError, match="classical/dayun/1"):
        registry.get("classical", "dayun", "1")


def test_registry_runs_explicit_strategy_and_preserves_provenance():
    registry = StrategyRegistry()

    result = registry.run(chart(), school="classical", policy="classical_approx_v1", version="1")

    assert result.context.school == "classical"
    assert result.context.policy == "classical_approx_v1"
    assert result.context.version == "1"
    assert result.approximate is True


def test_registry_allows_different_policies_in_same_school():
    first = ClassicalApproxDayunPolicy()

    class OtherPolicy(ClassicalApproxDayunPolicy):
        name = "other_v1"
        context = first.context.__class__(
            school="classical",
            policy=name,
            version="1",
            assumptions=first.context.assumptions,
        )

    registry = StrategyRegistry()
    registry.register(OtherPolicy())

    assert len(registry.list()) == 4


def test_registry_ships_school_variants_for_direction_and_start_age():
    registry = StrategyRegistry()

    keys = {(item.context.policy, item.context.assumptions) for item in registry.list()}

    assert {policy for policy, _ in keys} == {
        "classical_approx_v1",
        "day_stem_approx_v1",
        "lichun_start_approx_v1",
    }
    assert any("日干" in note for _, notes in keys for note in notes)
    assert any("立春" in note for _, notes in keys for note in notes)


def test_registry_requires_explicit_key_when_running():
    registry = StrategyRegistry()

    with pytest.raises(TypeError):
        registry.run(chart())
