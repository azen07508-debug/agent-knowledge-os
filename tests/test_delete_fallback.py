from types import SimpleNamespace

from runtime.opencli_x_backend import OpenCliXBackend
from runtime.x_adapter import XAdapter


def test_opencli_delete_falls_back_to_twitter_cli(monkeypatch):
    class Fallback:
        available = True

        def delete(self, post_id):
            return {"ok": True, "id": post_id}

    monkeypatch.setattr("runtime.twitter_backend.TwitterCliXBackend", lambda: Fallback())
    backend = OpenCliXBackend(runner=lambda argv, timeout: SimpleNamespace(returncode=1, stdout="", stderr="menu missing"))
    result = XAdapter(backend=backend).delete("123")
    assert result == {"ok": True, "id": "123", "fallback": "twitter-cli"}


def test_delete_reports_both_backends_failed(monkeypatch):
    class Fallback:
        available = True

        def delete(self, post_id):
            return {"ok": False, "message": "credentials missing"}

    monkeypatch.setattr("runtime.twitter_backend.TwitterCliXBackend", lambda: Fallback())
    backend = OpenCliXBackend(runner=lambda argv, timeout: SimpleNamespace(returncode=1, stdout="", stderr="menu missing"))
    result = XAdapter(backend=backend).delete("123")
    assert result["ok"] is False
    assert "credentials missing" in result["fallback_message"]
