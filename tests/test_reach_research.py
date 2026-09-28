"""Phase 4：Agent-Reach 调研接入（全部用假命令，不联网）。"""

from types import SimpleNamespace

import pytest

from runtime.reach_research import ReachResearch, extract_sources

WEB_OUTPUT = """\
# 搜索结果
1. https://example.com/agent-memory 关于记忆分层的讨论。
2. https://example.com/agent-memory 同一条重复出现。
3. GitHub: https://github.com/EverMind-AI/EverOS（正文。）
"""


def fake_which(available=("mcporter", "gh", "curl")):
    return lambda name: f"/usr/local/bin/{name}" if name in available else None


def fake_runner(stdout=WEB_OUTPUT, returncode=0, stderr="", calls=None):
    def run(argv, timeout):
        if calls is not None:
            calls.append((argv, timeout))
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    return run


def make(tmp_path, runner=None, which=None, **kwargs):
    return ReachResearch(
        vault_path=tmp_path,
        runner=runner or fake_runner(),
        which=which or fake_which(),
        **kwargs,
    )


# ── fetch ───────────────────────────────────────────────────────────────


def test_fetch_returns_digest_and_deduplicated_sources(tmp_path):
    fetched = make(tmp_path).fetch("memory layer")

    assert fetched["ok"] is True
    assert fetched["channel"] == "web"
    assert fetched["sources"] == [
        "https://example.com/agent-memory",
        "https://github.com/EverMind-AI/EverOS",
    ]
    assert fetched["digest"].startswith("# 搜索结果")


def test_fetch_truncates_long_digest(tmp_path):
    long_output = "x" * 5000
    fetched = make(tmp_path, runner=fake_runner(stdout=long_output)).fetch("q")

    assert fetched["ok"] is True
    assert len(fetched["digest"]) == 1501  # DIGEST_CHARS + 省略号
    assert fetched["digest"].endswith("…")


def test_fetch_reports_missing_command_without_raising(tmp_path):
    fetched = make(tmp_path, which=fake_which(available=())).fetch("memory layer")

    assert fetched["ok"] is False
    assert "找不到命令 mcporter" in fetched["message"]


def test_fetch_reports_nonzero_exit_and_empty_output(tmp_path):
    failed = make(tmp_path, runner=fake_runner(stdout="", returncode=3, stderr="boom")).fetch("q")
    empty = make(tmp_path, runner=fake_runner(stdout="   ")).fetch("q")

    assert failed["ok"] is False and "退出码 3" in failed["message"]
    assert empty["ok"] is False and "空结果" in empty["message"]


def test_fetch_rejects_unknown_channel(tmp_path):
    with pytest.raises(ValueError, match="未知调研通道"):
        make(tmp_path).fetch("q", channel="xiaohongshu")


def test_fetch_builds_expected_commands(tmp_path):
    calls = []
    reach = make(tmp_path, runner=fake_runner(calls=calls))

    reach.fetch("agent memory", channel="github", limit=3)
    reach.fetch("https://example.com/post", channel="page")
    reach.fetch("agent memory", channel="web", limit=5)

    argv = [call[0] for call in calls]
    assert argv[0][:3] == ["gh", "search", "repos"] and argv[0][-1] == "3"
    assert argv[1] == ["curl", "-sL", "https://r.jina.ai/https://example.com/post"]
    assert argv[2] == ["mcporter", "call", "exa.web_search_exa", "query=agent memory", "numResults=5"]


# ── research：写入 11-Research ──────────────────────────────────────────


def test_research_writes_conclusions_and_sources(tmp_path):
    reach = make(tmp_path)

    record = reach.research(
        topic="Agent-Reach",
        conclusions=["多后端路由按平台分发", "零配置通道覆盖搜索与代码"],
        query="agent-reach 多后端路由",
        unverified=["小红书通道需登录态"],
    )

    note = tmp_path / "11-Research" / "研究-Agent-Reach.md"
    text = note.read_text(encoding="utf-8")

    assert record["ok"] is True and note.exists()
    assert "- 多后端路由按平台分发" in text
    assert "- 小红书通道需登录态" in text
    assert "https://example.com/agent-memory" in text
    assert "source: https://example.com/agent-memory" in text  # frontmatter source = 首个来源
    assert "# 搜索结果" not in text  # 原文不进记忆
    assert record["fetched"]["channel"] == "web"
    assert record["fetched"]["digest_chars"] > 0


def test_research_merges_caller_sources_before_fetched_ones(tmp_path):
    reach = make(tmp_path)

    record = reach.research(topic="Agent-Reach", conclusions=["c"], query="q", sources="https://hand-written.example/1")
    text = (tmp_path / "11-Research" / "研究-Agent-Reach.md").read_text(encoding="utf-8")

    sources_line = [line for line in text.splitlines() if line.startswith("- https://hand-written")][0]
    assert sources_line.startswith("- https://hand-written.example/1")
    assert record["fetched"]["sources"][0] == "https://hand-written.example/1"


def test_research_does_not_write_when_fetch_fails(tmp_path):
    reach = make(tmp_path, which=fake_which(available=()))

    with pytest.raises(RuntimeError, match="联网调研失败，未写入记忆"):
        reach.research(topic="Agent-Reach", conclusions=["c"], query="q")

    assert not (tmp_path / "11-Research").exists()


def test_research_refuses_sourceless_conclusion(tmp_path):
    reach = make(tmp_path, runner=fake_runner(stdout="没有任何链接的结果"))

    with pytest.raises(RuntimeError, match="没有可用来源 URL"):
        reach.research(topic="Agent-Reach", conclusions=["c"], query="q")

    assert not (tmp_path / "11-Research").exists()


# ── 工具函数 ────────────────────────────────────────────────────────────


def test_extract_sources_strips_trailing_punctuation():
    assert extract_sources("见 https://a.com/x。另 https://b.com/y, 以及 https://c.com/z)") == [
        "https://a.com/x",
        "https://b.com/y",
        "https://c.com/z",
    ]


def test_error_text_is_not_treated_as_material(tmp_path):
    reach = make(tmp_path, runner=fake_runner(stdout="web_search_exa error (503): Exa is temporarily over capacity."))

    fetched = reach.fetch("q")

    assert fetched["ok"] is False
    assert "报错文本" in fetched["message"]


def test_rate_limit_notice_with_urls_is_not_material(tmp_path):
    stdout = (
        "You've hit Exa's free MCP rate limit. To continue using without limits, create your own Exa API key.\n"
        "Fix: Create API key at https://dashboard.exa.ai/api-keys"
    )
    reach = make(tmp_path, runner=fake_runner(stdout=stdout))

    fetched = reach.fetch("q")

    assert fetched["ok"] is False
    assert "报错文本" in fetched["message"]


def test_github_channel_builds_repo_urls_from_tsv(tmp_path):
    stdout = (
        "obsidianmd/obsidian-releases\tCommunity plugins list\tpublic\t2026-09-28\n"
        "kepano/obsidian-skills\tAgent skills. Fixes errors fast\tpublic\t2026-09-28\n"
    )
    reach = make(tmp_path, runner=fake_runner(stdout=stdout))

    fetched = reach.fetch("obsidian", channel="github")

    assert fetched["ok"] is True  # 描述里含 error 但有来源，不是报错文本
    assert fetched["sources"] == [
        "https://github.com/obsidianmd/obsidian-releases",
        "https://github.com/kepano/obsidian-skills",
    ]


def test_github_research_records_repo_urls(tmp_path):
    stdout = "owner/repo\tA helper\tpublic\t2026-09-28\n"
    reach = make(tmp_path, runner=fake_runner(stdout=stdout))

    reach.research(topic="调研", conclusions=["可参考"], query="helper", channel="github")

    text = (tmp_path / "11-Research" / "研究-调研.md").read_text(encoding="utf-8")
    assert "- https://github.com/owner/repo" in text
    assert "source: https://github.com/owner/repo" in text
