"""Phase 11：X 内容工作流（URL / Topic / Research → Thread → 发布）。"""

import pytest

from agents import XWorkflow
from agents.content import ContentAgent
from runtime.content_store import ContentStore
from runtime.human_review import approve
from runtime.memory_api import MemoryAPI
from runtime.reach_research import ReachResearch
from runtime.research_store import ResearchStore
from runtime.x_adapter import XAdapter

PAGE_OUTPUT = """\
# Obsidian 记忆分层实测

冷热三层结构，热层放 3 条规则，冷层放收藏。

建议：先做本地检索，别急着上向量库。

参考：https://example.com/docs
"""

ACCOUNT = {
    "账号定位": "AI 工具实测",
    "目标受众": "开发者",
    "内容领域": "开源项目",
    "内容支柱": "项目实测",
    "表达风格": "实测 > 空谈",
    "长期目标": "沉淀评测方法论",
    "禁止内容": "收益承诺、标题党",
    "平台差异": "X 走 Thread",
    "账号阶段": "冷启动",
}


def fake_which(available=("curl",)):
    return lambda name: f"/usr/local/bin/{name}" if name in available else None


def fake_runner(stdout=PAGE_OUTPUT, returncode=0, stderr=""):
    def run(argv, timeout):
        from types import SimpleNamespace

        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    return run


class OkBackend:
    def post(self, text: str):
        return {"ok": True, "id": "p1"}


class FailBackend:
    def post(self, text: str):
        return {"ok": False, "message": "X API 拒绝：内容重复"}


def make_workflow(tmp_path, which=None, backend=None, dry_run=True) -> XWorkflow:
    memory = MemoryAPI(vault_path=tmp_path)
    memory.create("account", "账号画像", ACCOUNT)
    store = ContentStore(tmp_path / "content.sqlite3")
    reach = ReachResearch(
        memory=memory,
        store=ResearchStore(":memory:"),
        runner=fake_runner(),
        which=which or fake_which(),
    )
    return XWorkflow(
        reach=reach,
        store=store,
        memory=memory,
        x=XAdapter(backend=backend if backend is not None else OkBackend(), dry_run=dry_run),
        content_agent=ContentAgent(store=store, memory=memory),
    )


# ── candidate_from_page ────────────────────────────────────────────────


def test_candidate_from_page_extracts_title_facts_and_opinions():
    from agents.x_workflow import candidate_from_page

    candidate = candidate_from_page("https://example.com/post", PAGE_OUTPUT)

    assert candidate["topic"] == "Obsidian 记忆分层实测"  # 取标题行
    assert candidate["sources"] == ["https://example.com/post"]
    assert any("3 条规则" in fact for fact in candidate["facts"])
    assert any("建议" in opinion for opinion in candidate["opinions"])
    assert candidate["evidence"][0]["quote"]  # 有证据摘录


# ── URL → Thread ───────────────────────────────────────────────────────


def test_url_to_draft_produces_reviewable_draft(tmp_path):
    wf = make_workflow(tmp_path)

    result = wf.url_to_draft("https://example.com/post")

    assert result["errors"] == []
    content = result["content"]
    assert content is not None
    assert "https://example.com/post" in content["sources"]
    assert content["status"] in ("REVIEW", "DRAFT")
    assert content["hook"]
    assert result["pending_human_review"] == (content["status"] == "REVIEW")
    assert wf.store.get(content["id"]) is not None  # 落库


def test_url_to_draft_reports_fetch_failure(tmp_path):
    wf = make_workflow(tmp_path, which=fake_which(available=()))

    result = wf.url_to_draft("https://example.com/post")

    assert result["content"] is None
    assert result["errors"] and "工作流失败" in result["summary"]


# ── Topic → Thread ─────────────────────────────────────────────────────


def test_topic_to_thread_reuses_content_agent(tmp_path):
    wf = make_workflow(tmp_path)
    candidate = {
        "topic": "Obsidian 记忆分层",
        "angle": "冷暖热三层实测",
        "angles": ["冷暖热三层实测"],
        "audience": "开发者",
        "sources": ["https://a.com/1"],
        "evidence": [{"url": "https://a.com/1", "quote": "热层 3 条规则"}],
        "facts": ["热层 3 条规则"],
        "opinions": [],
    }

    result = wf.topic_to_thread(candidate)

    assert result["content"]["status"] in ("REVIEW", "DRAFT")
    assert wf.store.count() >= 1


# ── Research → Original Post ───────────────────────────────────────────


def test_research_to_post_builds_original_post(tmp_path):
    wf = make_workflow(tmp_path)
    wf.memory.create("research", "研究-工具分层", {
        "主题": "工具分层",
        "关键结论": "结论一：热层 3 条规则\n结论二：冷层放原始收藏",
        "重要来源": "https://a.com/1",
        "研究时间": "2026-09-29",
    })

    result = wf.research_to_post("工具分层")

    content = result["content"]
    assert content["status"] in ("REVIEW", "DRAFT")
    assert content["claims"] == ["结论一：热层 3 条规则", "结论二：冷层放原始收藏"]
    assert content["sources"] == ["https://a.com/1"]
    assert all(item["ok"] for item in result["checks"].values())  # 结论都能在证据摘录里找到出处


def test_research_to_post_missing_note_fails_cleanly(tmp_path):
    wf = make_workflow(tmp_path)

    result = wf.research_to_post("不存在的主题")

    assert result["content"] is None
    assert "不存在" in result["errors"][0]


def test_research_lines_are_cleaned_of_markdown_prefixes(tmp_path):
    wf = make_workflow(tmp_path)
    wf.memory.create("research", "研究-带列表前缀", {
        "主题": "带列表前缀",
        "关键结论": "- 结论一：热层 3 条规则\n- 结论二：冷层放原始收藏",
        "重要来源": "- https://a.com/1",
        "研究时间": "2026-09-29",
    })

    result = wf.research_to_post("带列表前缀")
    content = result["content"]

    assert content["claims"] == ["结论一：热层 3 条规则", "结论二：冷层放原始收藏"]
    assert content["sources"] == ["https://a.com/1"]  # 不带 "- " 前缀
    assert not content["hook"].startswith("-")


# ── 发布闸门 ────────────────────────────────────────────────────────────


def test_publish_requires_approved_status(tmp_path):
    wf = make_workflow(tmp_path)
    draft = wf.topic_to_thread({
        "topic": "选题", "angle": "a", "angles": ["a"], "audience": "开发者",
        "sources": ["https://a.com/1"],
        "evidence": [{"url": "https://a.com/1", "quote": "热层 3 条规则"}],
        "facts": ["热层 3 条规则"], "opinions": [],
    })
    content_id = draft["content"]["id"]

    result = wf.publish(content_id)  # 可能还没 APPROVED

    if draft["content"]["status"] != "APPROVED":
        assert result["ok"] is False
        assert "未通过人审" in result["message"]
        assert wf.store.get(content_id).status != "PUBLISHED"


def _approved_draft(wf) -> str:
    draft = wf.topic_to_thread({
        "topic": "选题", "angle": "a", "angles": ["a"], "audience": "开发者",
        "sources": ["https://a.com/1"],
        "evidence": [{"url": "https://a.com/1", "quote": "热层 3 条规则"}],
        "facts": ["热层 3 条规则"], "opinions": [],
    })
    content_id = draft["content"]["id"]
    if wf.store.get(content_id).status != "REVIEW":
        pytest.skip("草稿因检查未过停在 DRAFT，人审路径在 test_human_review 覆盖")
    approve(wf.store, content_id, reviewer="admin", note="来源核对无误")
    return content_id


def test_publish_dry_run_keeps_approved_status(tmp_path):
    """演练没真发：不许把没发生的事写成已发生，状态保持 APPROVED。"""
    wf = make_workflow(tmp_path)
    content_id = _approved_draft(wf)

    result = wf.publish(content_id)

    assert result["ok"] is True and result["dry_run"] is True
    assert "未真实发送" in result["message"]
    saved = wf.store.get(content_id)
    assert saved.status == "APPROVED"                 # 演练不改状态
    assert saved.platform_versions == {}


def test_publish_real_send_marks_published(tmp_path):
    wf = make_workflow(tmp_path, backend=OkBackend(), dry_run=False)
    content_id = _approved_draft(wf)

    result = wf.publish(content_id, dry_run=False)

    assert result["ok"] is True and result["dry_run"] is False
    assert wf.store.get(content_id).status == "PUBLISHED"
    assert wf.store.get(content_id).platform_versions == {"X": "Thread"}


def test_publish_failure_keeps_approved_status(tmp_path):
    wf = make_workflow(tmp_path, backend=FailBackend(), dry_run=False)
    draft = wf.topic_to_thread({
        "topic": "选题", "angle": "a", "angles": ["a"], "audience": "开发者",
        "sources": ["https://a.com/1"],
        "evidence": [{"url": "https://a.com/1", "quote": "热层 3 条规则"}],
        "facts": ["热层 3 条规则"], "opinions": [],
    })
    content_id = draft["content"]["id"]
    if wf.store.get(content_id).status == "REVIEW":
        approve(wf.store, content_id, reviewer="admin")
    else:
        pytest.skip("草稿因检查未过停在 DRAFT")

    result = wf.publish(content_id)

    assert result["ok"] is False and "拒绝" in result["message"]
    assert wf.store.get(content_id).status == "APPROVED"  # 发送失败不改状态


def test_publish_unknown_content_raises(tmp_path):
    wf = make_workflow(tmp_path)

    with pytest.raises(FileNotFoundError):
        wf.publish("no-such-id")
