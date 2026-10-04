"""Phase 10：twitter-cli 后端（凭据注入 / 命令拼装 / 输出解析）。"""

import json
from types import SimpleNamespace

import pytest

from runtime.twitter_backend import NO_SCHEDULE, TwitterCliXBackend, load_config
from runtime.x_adapter import XAdapter, default_x_adapter

SEARCH_JSON = json.dumps(
    [
        {"id_str": "1", "text": "冷暖热三层结构", "created_at": "2026-09-29 10:00:00 +0000",
         "user": {"screen_name": "dev"}},
        {"id": 2, "full_text": "另一条推文", "author": {"username": "bob"}},
        {"id_str": "3"},  # 既没文本也没链接 -> 应被丢掉
    ],
    ensure_ascii=False,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """凭据只来自测试自己给的 config/ env，保证与本机真实配置无关。"""
    monkeypatch.delenv("TWITTER_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWITTER_CT0", raising=False)


def write_config(tmp_path, **overrides) -> str:
    values = {"proxy": "http://127.0.0.1:7890", "twitter_auth_token": "tok-abc", "twitter_ct0": "ct0-def"}
    values.update(overrides)
    path = tmp_path / "config.yaml"
    path.write_text("\n".join(f"{key}: {value}" for key, value in values.items()) + "\n", encoding="utf-8")
    return str(path)


def fake_runner(stdout="", returncode=0, stderr="", calls=None, boom=False):
    def run(argv, timeout, env):
        if calls is not None:
            calls.append({"argv": argv, "timeout": timeout, "env": env})
        if boom:
            raise RuntimeError("x.com 连接被拒")
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    return run


def make(tmp_path, stdout="", runner=None, **kwargs) -> TwitterCliXBackend:
    kwargs.setdefault("config_path", write_config(tmp_path))
    kwargs["runner"] = runner if runner is not None else fake_runner(stdout=stdout)
    return TwitterCliXBackend(**kwargs)


# ── 凭据 ────────────────────────────────────────────────────────────────


def test_missing_credentials_fails_without_running_anything(tmp_path):
    calls = []
    backend = TwitterCliXBackend(runner=fake_runner(calls=calls), config_path=str(tmp_path / "none.yaml"))

    result = backend.search("obsidian")

    assert result["ok"] is False and "configure twitter-cookies" in result["message"]
    assert calls == []  # 没凭据连命令都不发


def test_credentials_come_from_config_and_injected_as_env(tmp_path):
    calls = []
    backend = make(tmp_path, runner=fake_runner(stdout=SEARCH_JSON, calls=calls))

    result = backend.search("obsidian", limit=5)

    assert result["ok"] is True
    env = calls[0]["env"]
    assert env["TWITTER_AUTH_TOKEN"] == "tok-abc" and env["TWITTER_CT0"] == "ct0-def"
    assert env["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert calls[0]["argv"] == ["twitter", "search", "obsidian", "-n", "5", "--json"]


def test_explicit_env_wins_over_config(tmp_path):
    calls = []
    backend = make(tmp_path, runner=fake_runner(stdout=SEARCH_JSON, calls=calls),
                   env={"TWITTER_AUTH_TOKEN": "explicit"})

    backend.search("q")

    assert calls[0]["env"]["TWITTER_AUTH_TOKEN"] == "explicit"
    assert calls[0]["env"]["TWITTER_CT0"] == "ct0-def"  # 缺的那个仍从 config 补


def test_available_reflects_credentials(tmp_path):
    assert make(tmp_path).available is True
    no_creds = TwitterCliXBackend(config_path=str(tmp_path / "none.yaml"))
    assert no_creds.available is False


def test_load_config_ignores_comments_and_blank_lines(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("# 注释\n\nproxy: http://127.0.0.1:7890\n", encoding="utf-8")

    assert load_config(path) == {"proxy": "http://127.0.0.1:7890"}
    assert load_config(tmp_path / "missing.yaml") == {}


# ── 读接口 ──────────────────────────────────────────────────────────────


def test_search_normalizes_items(tmp_path):
    backend = make(tmp_path, stdout=SEARCH_JSON)

    items = backend.search("obsidian")["items"]

    assert len(items) == 2  # 无文本无链接的那条被丢掉
    assert items[0] == {
        "url": "https://x.com/dev/status/1",
        "author": "dev",
        "text": "冷暖热三层结构",
        "time": "2026-09-29 10:00:00 +0000",
    }
    assert items[1]["author"] == "bob" and items[1]["text"] == "另一条推文"
    assert items[1]["url"] == "https://x.com/bob/status/2"  # 没给 url 就按作者+ID 拼


def test_timeline_command(tmp_path):
    calls = []
    backend = make(tmp_path, runner=fake_runner(stdout="[]", calls=calls))

    backend.timeline(limit=7)

    assert calls[0]["argv"] == ["twitter", "feed", "-n", "7", "--json"]


def test_mentions_looks_up_own_handle_first(tmp_path):
    calls = []

    def run(argv, timeout, env):
        calls.append(argv)
        stdout = json.dumps({"screen_name": "me"}) if argv[1] == "whoami" else "[]"
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    backend = make(tmp_path, runner=run)

    result = backend.mentions(limit=5)

    assert result["ok"] is True
    assert calls[0] == ["twitter", "whoami", "--json"]
    assert calls[1] == ["twitter", "search", "--to", "me", "-n", "5", "--json"]


def test_analytics_parses_metrics(tmp_path):
    stdout = json.dumps({"id_str": "99", "like_count": 3, "retweet_count": 1,
                         "reply_count": 0, "views": 100, "created_at": "x"})
    backend = make(tmp_path, stdout=stdout)

    result = backend.analytics("99")

    assert result["ok"] is True
    assert result["metrics"] == {"likes": 3, "reposts": 1, "replies": 0, "views": 100}


def test_analytics_without_metrics_says_so(tmp_path):
    backend = make(tmp_path, stdout=json.dumps({"id_str": "99"}))

    result = backend.analytics("99")

    assert result["ok"] is False and "互动指标" in result["message"]


# ── 写接口 ──────────────────────────────────────────────────────────────


def test_post_returns_tweet_id(tmp_path):
    calls = []
    backend = make(tmp_path, runner=fake_runner(stdout=json.dumps({"id_str": "42"}), calls=calls))

    result = backend.post("要发的内容")

    assert result == {"ok": True, "id": "42"}
    assert calls[0]["argv"] == ["twitter", "post", "要发的内容", "--json"]


def test_post_failure_carries_stderr(tmp_path):
    backend = make(tmp_path, runner=fake_runner(returncode=1, stderr="Duplicate request"))

    result = backend.post("内容")

    assert result["ok"] is False and "Duplicate request" in result["message"]


def test_delete_unknown_error_json_is_not_success(tmp_path):
    backend = make(tmp_path, stdout='{"status":"error","message":"permission denied"}')
    result = backend.delete("123")
    assert result["ok"] is False
    assert "permission denied" in result["message"]


def test_schedule_is_honestly_unsupported(tmp_path):
    backend = make(tmp_path)

    result = backend.schedule("内容", "2026-09-30 09:00")

    assert result["ok"] is False and result["message"] == NO_SCHEDULE


# ── 异常路径 ────────────────────────────────────────────────────────────


def test_runner_exception_becomes_failure(tmp_path):
    backend = make(tmp_path, runner=fake_runner(boom=True))

    result = backend.search("q")

    assert result["ok"] is False and "调用失败" in result["message"]


def test_non_json_output_is_not_guessed(tmp_path):
    backend = make(tmp_path, stdout="Search results for q\n1. tweet tweet tweet")

    result = backend.search("q")

    assert result["ok"] is False and "不是 JSON" in result["message"]


# ── default_x_adapter ───────────────────────────────────────────────────


def test_default_x_adapter_detects_credentials_without_opencli(tmp_path):
    no_browser = {"which": lambda _: None}  # 模拟本机没装 opencli，走 twitter-cli 凭据链路
    configured = default_x_adapter(config_path=write_config(tmp_path), **no_browser)
    plain = default_x_adapter(config_path=str(tmp_path / "none.yaml"), **no_browser)

    assert configured.backend is not None
    assert plain.backend is None and plain.configured is False


def test_x_adapter_uses_twitter_backend_end_to_end(tmp_path):
    backend = make(tmp_path, stdout=json.dumps({"id_str": "7"}))
    adapter = XAdapter(backend=backend, dry_run=False)

    result = adapter.post("真实发送")

    assert result["ok"] is True and result["id"] == "7"

    search_backend = make(tmp_path, stdout=SEARCH_JSON)
    found = XAdapter(backend=search_backend).search("obsidian")
    assert found["ok"] is True and found["count"] == 2
