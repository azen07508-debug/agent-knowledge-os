"""Phase 10：OpenCLI 后端（命令拼装 / 登录态检查 / 输出解析）。"""

import json
from types import SimpleNamespace

from runtime.opencli_x_backend import NO_SCHEDULE, NOT_LOGGED_IN, OpenCliXBackend
from runtime.x_adapter import XAdapter, default_x_adapter

SEARCH_JSON = json.dumps(
    [
        {"id": "111", "author": "@dev", "text": "冷暖热三层结构", "created_at": "2026-09-28",
         "likes": 53, "views": "9379", "url": "https://x.com/i/status/111"},
        {"id": "222", "author": "bob", "text": "另一条", "created_at": ""},
        {"id": "333"},  # 无文本也无链接/作者 -> 应被丢掉
    ],
    ensure_ascii=False,
)

TWEETS_JSON = json.dumps(
    [
        {"id": "99", "author": "me", "text": "我的推文", "likes": 3, "retweets": 1,
         "replies": 0, "views": "385274", "url": "https://x.com/i/status/99"},
        {"id": "98", "author": "me", "text": "另一条", "likes": 0, "retweets": 0,
         "replies": 0, "views": "10"},
    ]
)


def fake_runner(stdout="", returncode=0, stderr="", calls=None, boom=False, routes=None):
    """routes: {argv[1]: stdout}，按子命令返回不同输出（如 whoami / search）。"""

    def run(argv, timeout):
        if calls is not None:
            calls.append({"argv": argv, "timeout": timeout})
        if boom:
            raise RuntimeError("浏览器扩展未连接")
        if routes and len(argv) > 2 and argv[2] in routes:
            return SimpleNamespace(returncode=0, stdout=routes[argv[2]], stderr="")
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    return run


def make(stdout="", **kwargs) -> OpenCliXBackend:
    kwargs.setdefault("runner", fake_runner(stdout=stdout))
    return OpenCliXBackend(**kwargs)


def test_available_follows_which():
    assert OpenCliXBackend(which=lambda _: "/usr/local/bin/opencli").available is True
    assert OpenCliXBackend(which=lambda _: None).available is False


def test_search_command_and_normalization():
    calls = []
    backend = make(stdout=SEARCH_JSON, runner=fake_runner(stdout=SEARCH_JSON, calls=calls))

    result = backend.search("obsidian", limit=5)

    assert result["ok"] is True
    assert calls[0]["argv"] == ["opencli", "twitter", "search", "obsidian", "--limit", "5", "-f", "json"]
    items = result["items"]
    assert len(items) == 2  # 无文本无链接的那条被丢掉
    assert items[0] == {
        "url": "https://x.com/i/status/111",
        "author": "dev",  # 去掉 @
        "text": "冷暖热三层结构",
        "time": "2026-09-28",
    }
    assert items[1]["url"] == "https://x.com/bob/status/222"  # 没给 url 按作者+ID 拼


def test_timeline_command():
    calls = []
    backend = make(runner=fake_runner(stdout="[]", calls=calls))

    backend.timeline(limit=7)

    assert calls[0]["argv"] == ["opencli", "twitter", "timeline", "--limit", "7", "-f", "json"]


def test_mentions_uses_own_handle():
    calls = []
    routes = {"whoami": json.dumps({"logged_in": True, "username": "AZEN_BTC"}),
              "search": "[]"}
    backend = make(runner=fake_runner(calls=calls, routes=routes))

    result = backend.mentions(limit=5)

    assert result["ok"] is True
    assert calls[0]["argv"] == ["opencli", "twitter", "whoami", "-f", "json"]
    assert calls[1]["argv"][1:4] == ["twitter", "search", "@AZEN_BTC"]
    assert calls[1]["argv"][-4:] == ["--limit", "5", "-f", "json"]


def test_mentions_when_not_logged_in():
    routes = {"whoami": json.dumps({"logged_in": False, "site": "twitter"})}
    backend = make(runner=fake_runner(routes=routes))

    result = backend.mentions()

    assert result["ok"] is False and result["message"] == NOT_LOGGED_IN


def test_post_success_returns_id_and_url():
    calls = []
    stdout = json.dumps({"status": "ok", "message": "posted", "id": "42",
                         "url": "https://x.com/i/status/42"})
    backend = make(runner=fake_runner(stdout=stdout, calls=calls))

    result = backend.post("要发的内容")

    assert result == {"ok": True, "id": "42", "url": "https://x.com/i/status/42"}
    assert calls[0]["argv"] == ["opencli", "twitter", "post", "要发的内容", "-f", "json"]


def test_post_error_status_is_failure():
    stdout = json.dumps({"status": "error", "message": "Rate limit exceeded"})
    backend = make(stdout=stdout)

    result = backend.post("内容")

    assert result["ok"] is False and result["message"] == "Rate limit exceeded"


def test_post_failure_carries_stderr():
    backend = make(runner=fake_runner(returncode=1, stderr="扩展未连接"))

    result = backend.post("内容")

    assert result["ok"] is False and "扩展未连接" in result["message"]


def test_post_timeout_reconciles_against_timeline():
    """opencli 超时不等于没发出：最近时间线里有这条就认（真实发帖栽在这过）。"""
    landed = json.dumps([
        {"id": "777", "author": "me",
         "text": "来源：https://t.co/JLmBxqC9Tm（1181 star）",   # X 把链接改写成了 t.co
         "url": "https://x.com/me/status/777"},
    ])

    def runner(argv, timeout):
        if argv[2] == "post":
            return SimpleNamespace(returncode=75, stdout="", stderr="twitter post timed out after 15s")
        return SimpleNamespace(returncode=0, stdout=landed, stderr="")

    backend = OpenCliXBackend(runner=runner)

    result = backend.post("来源：https://github.com/a/b（1181 star）")

    assert result == {"ok": True, "id": "777", "url": "https://x.com/me/status/777"}


def test_post_failure_without_timeline_match_keeps_original_error():
    def runner(argv, timeout):
        if argv[2] == "post":
            return SimpleNamespace(returncode=75, stdout="", stderr="twitter post timed out after 15s")
        return SimpleNamespace(returncode=0, stdout="[]", stderr="")

    backend = OpenCliXBackend(runner=runner)

    result = backend.post("没发出的内容")

    assert result["ok"] is False and "退出码 75" in result["message"]


def test_schedule_is_honestly_unsupported():
    result = make().schedule("内容", "2026-09-30 09:00")

    assert result["ok"] is False and result["message"] == NO_SCHEDULE


def test_analytics_finds_own_tweet_and_coerces_numbers():
    calls = []
    backend = make(runner=fake_runner(stdout=TWEETS_JSON, calls=calls))

    result = backend.analytics("99")

    assert result["ok"] is True
    assert result["metrics"] == {"likes": 3, "reposts": 1, "replies": 0, "views": 385274}
    assert calls[0]["argv"][1:3] == ["twitter", "tweets"]


def test_analytics_unknown_post_says_so():
    backend = make(stdout=TWEETS_JSON)

    result = backend.analytics("nope")

    assert result["ok"] is False and "nope" in result["message"]


def test_runner_exception_becomes_failure():
    backend = make(runner=fake_runner(boom=True))

    result = backend.search("q")

    assert result["ok"] is False and "调用失败" in result["message"]


def test_non_json_output_is_not_guessed():
    backend = make(stdout="Search results\n1. tweet")

    result = backend.search("q")

    assert result["ok"] is False and "不是 JSON" in result["message"]


def test_default_x_adapter_prefers_opencli():
    adapter = default_x_adapter(which=lambda _: "/usr/local/bin/opencli")

    assert isinstance(adapter.backend, OpenCliXBackend)
    assert adapter.configured is True


def test_x_adapter_uses_opencli_end_to_end():
    backend = make(stdout=json.dumps({"status": "ok", "id": "7", "url": "u"}))
    adapter = XAdapter(backend=backend, dry_run=False)

    result = adapter.post("真实发送")

    assert result["ok"] is True and result["id"] == "7"

    found = XAdapter(backend=make(stdout=SEARCH_JSON)).search("obsidian")
    assert found["ok"] is True and found["count"] == 2
