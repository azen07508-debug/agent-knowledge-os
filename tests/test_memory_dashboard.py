"""Phase 20：Memory Dashboard——记忆系统的 7 个视图。"""

from runtime import dashboard, memory_dashboard
from runtime.memory_api import MemoryAPI

ACCOUNT = {
    "账号定位": "AI 记忆系统实测",
    "目标受众": "开发者",
    "内容支柱": "项目实测",
    "表达风格": "实测 > 空谈",
    "长期目标": "沉淀评测方法论",
    "禁止内容": "收益承诺",
    "平台差异": "X 走 Thread",
    "账号阶段": "冷启动",
    "内容领域": "开源知识库",
}

STRATEGY = {
    "当前内容策略": "围绕记忆系统做项目实测",
    "内容支柱": "项目实测",
    "目标方向": "沉淀评测方法论",
    "状态": "Confirmed",
    "策略变更原因": "首次建立",
}


def populated(tmp_path) -> MemoryAPI:
    memory = MemoryAPI(vault_path=tmp_path / "vault")
    memory.create("account", "账号画像", ACCOUNT)
    memory.create("strategy", "当前内容策略", STRATEGY)
    memory.recordObservation(topic="content_type:thread",
                             observation="thread 类互动率高于单帖",
                             evidence="post_ids=t0,t1,t2")
    memory.recordHypothesis(hypothesis="小红书图文能复用同一套选题",
                            variables=["平台", "内容形式"], expected="互动率接近 X 的 80%",
                            next_action="发布 3 条小红书图文收集数据", source="manual")
    memory.recordDecision(subject="是否做泛 AI 新闻", decision="不做",
                          reason="与账号定位冲突，先做深垂直", date="2026-09-20")
    memory.create("agent", "2026-09-29-Agent-发布", {"Agent": "Publisher", "经验": "TIMEOUT 先对账再重试"})
    return memory


def views(memory):
    return {section["title"]: section for section in memory_dashboard.collect(memory)}


# ── 七个视图 ────────────────────────────────────────────────────────────


def test_seven_views_in_plan_order(tmp_path):
    collected = memory_dashboard.collect(populated(tmp_path))

    assert [section["title"] for section in collected] == list(memory_dashboard.VIEWS)
    assert all(section["count"] >= 0 and section["columns"] for section in collected)


def test_account_view_answers_who_we_are(tmp_path):
    view = views(populated(tmp_path))["Account Memory"]

    assert view["count"] == len(ACCOUNT)
    assert ["账号定位", "AI 记忆系统实测"] in view["rows"]


def test_strategy_view_answers_what_we_do_now(tmp_path):
    view = views(populated(tmp_path))["Strategy Memory"]

    assert ["当前内容策略", "围绕记忆系统做项目实测"] in view["rows"]
    assert "只读" in view["note"]


def test_learned_patterns_marks_pending_as_unverified(tmp_path):
    view = views(populated(tmp_path))["Learned Patterns"]

    assert view["count"] == 1
    row = view["rows"][0]
    assert row[0] == "content_type:thread" and row[1] == "thread 类互动率高于单帖"
    assert row[2] == "pending"                        # 观察还没复核
    assert "未经复核" in view["note"]


def test_experiments_decisions_and_agent_knowledge_views(tmp_path):
    collected = views(populated(tmp_path))

    experiment = collected["Experiments"]
    assert experiment["count"] == 1
    assert "小红书图文能复用同一套选题" in str(experiment["rows"])

    decision = collected["Decisions"]
    assert ["2026-09-20", "是否做泛 AI 新闻", "不做",
            "与账号定位冲突，先做深垂直"] in decision["rows"]

    agent = collected["Agent Knowledge"]
    assert agent["count"] == 1
    assert "TIMEOUT 先对账再重试" in str(agent["rows"])


def test_memory_health_lists_all_six_issue_types(tmp_path):
    view = views(populated(tmp_path))["Memory Health"]

    assert [row[0] for row in view["rows"]] == list(memory_dashboard.HEALTH_LABELS.values())
    no_source = next(row for row in view["rows"] if row[0] == "无来源结论")
    assert int(no_source[1]) >= 1                      # 观察没写来源 → 如实计入（单元格统一是字符串）
    assert "只读报告" in view["note"]


def test_empty_vault_keeps_all_views_without_inventing_rows(tmp_path):
    collected = views(MemoryAPI(vault_path=tmp_path / "empty"))

    assert list(collected) == list(memory_dashboard.VIEWS)
    for name in ("Account Memory", "Strategy Memory", "Learned Patterns",
                 "Experiments", "Decisions", "Agent Knowledge"):
        assert collected[name]["rows"] == [], name
    health = collected["Memory Health"]
    assert len(health["rows"]) == 6
    assert all(int(row[1]) == 0 for row in health["rows"])  # 空库就是 0，不编问题


# ── 接进 Phase 19 的 Memory 页 ──────────────────────────────────────────


def test_dashboard_memory_page_hosts_the_seven_views(tmp_path):
    memory = populated(tmp_path)
    data = dashboard.collect(memory=memory)

    titles = [section["title"] for section in data["pages"]["Memory"]]

    assert titles == list(memory_dashboard.VIEWS)
    page = dashboard.render(data)
    assert "Learned Patterns" in page and "Memory Health" in page
