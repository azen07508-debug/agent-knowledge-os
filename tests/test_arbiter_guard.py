from runtime.arbiter_guard import ArbiterGuard


def test_arbiter_guard_init(tmp_path):
    guard = ArbiterGuard(vault_path=tmp_path)

    assert guard.default_budget == 8000
    assert isinstance(guard.status(), dict)


def test_request_budget_returns_result(tmp_path):
    guard = ArbiterGuard(vault_path=tmp_path)
    result = guard.request_budget("测试 Agent", 100)

    assert "allowed" in result
    assert "message" in result
    assert (tmp_path / "05-Agents" / "arbiter-budget-log.md").exists()


def test_missing_arbiter_has_friendly_message(tmp_path):
    guard = ArbiterGuard(vault_path=tmp_path)
    result = guard.request_budget("测试 Agent", 100)

    if not guard.available:
        assert "arbiter-lite" in result["message"]
