"""Phase 1：provider 发现与能力声明测试。"""

from engines.bazi import BaziCalculator
from engines.bazi.providers import inspect_optional_providers, provider_diagnostics
from tests.test_bazi_engine_contract import FixtureProvider


def test_optional_provider_probe_is_local_and_structured():
    statuses = inspect_optional_providers()

    assert statuses
    assert {status.name for status in statuses} == {"sxtwl", "lunar-rs"}
    assert all(isinstance(status.installed, bool) for status in statuses)
    assert all(status.verified is False for status in statuses)


def test_diagnostics_never_claims_unverified_provider_as_ready():
    result = provider_diagnostics()

    assert result["ok"] is False
    assert "warning" in result
    assert all(item["verified"] is False for item in result["providers"])


def test_calculator_capabilities_default_to_false():
    calculator = BaziCalculator(FixtureProvider())

    assert calculator.capabilities() == {
        "supports_true_solar_time": False,
        "supports_dayun": False,
        "supports_relations": False,
    }


def test_calculator_capabilities_are_explicit():
    provider = FixtureProvider()
    provider.supports_true_solar_time = True
    provider.supports_dayun = True

    assert BaziCalculator(provider).capabilities() == {
        "supports_true_solar_time": True,
        "supports_dayun": True,
        "supports_relations": False,
    }
