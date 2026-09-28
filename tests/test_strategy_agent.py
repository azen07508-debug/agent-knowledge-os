"""Phase 7：Strategy Agent（记忆 → 策略判断）。"""

from datetime import datetime

from agents import StrategyAgent
from runtime.memory_api import MemoryAPI
from runtime.strategy import VERDICT_RECOMMEND, VERDICT_REJECT, VERDICT_JUDGE
from runtime.topic_engine import TopicEngine
from runtime.topics import TopicCandidate

ACCOUNT = {
    "账号定位": "AI 工具实测",
    "目标受众": "开发者",
    "内容领域": "开源项目",
    "内容支柱": "项目实测",
    "表达风格": "实测 > 空谈",
    "长期目标": "沉淀评测方法论",
    "禁止内容": "收益承诺",
    "平台差异": "X 走 Thread",
    "账号阶段": "冷启动",
}

STRATEGY = {
    "当前内容策略": "围绕 AI 工具实测做项目拆解",
    "内容支柱": "项目实测",
    "目标方向": "沉淀评测方法论",
    "状态": "Confirmed",
    "策略变更原因": "首次建立：围绕 AI 工具实测展开",
}

TODAY = datetime.now().strftime("%Y-%m-%d")


def candidate(**overrides) -> TopicCandidate:
    base = {
        "topic": "Obsidian 长期记忆分层实践",
        "category": "AI 工具",
        "sources": ["https://a.com/1"],
        "evidence": [{"url": "https://a.com/1", "quote": "热层 3 条规则"}],
        "facts": ["热层 3 条规则"],
        "opinions": [],
        "freshness": TODAY,
        "confidence": "LOW",
    }
    base.update(overrides)
    return TopicCandidate(**base)


def base_memory(tmp_path, strategy=STRATEGY) -> MemoryAPI:
    memory = MemoryAPI(vault_path=tmp_path)
    memory.create("account", "账号画像", ACCOUNT)
    if strategy is not None:
        memory.create("strategy", "当前内容策略", strategy)
    return memory


# ── 主链路 ──────────────────────────────────────────────────────────────


def test_full_pipeline_returns_briefs(tmp_path):
    memory = base_memory(tmp_path)
    agent = StrategyAgent(memory=memory)

    result = agent.run("判断选题", {"candidates": [candidate()]})

    assert result["agent"] == "Strategy Agent"
    assert result["errors"] == [] and result["warnings"] == []
    assert len(result["strategies"]) == 1
    brief = result["strategies"][0]
    for field in ("topic", "verdict", "answer", "strategy_basis", "history",
                  "observations", "caveats", "recommendation"):
        assert field in brief, field
    assert brief["verdict"] in (VERDICT_RECOMMEND, VERDICT_JUDGE, VERDICT_REJECT)
    assert brief["recommendation"]["topic"] == candidate().topic
    assert result["knowledge_points"]


def test_answer_explains_account_fit(tmp_path):
    agent = StrategyAgent(memory=base_memory(tmp_path))

    brief = agent.run("x", {"candidates": [candidate()]})["strategies"][0]

    assert brief["verdict"] == VERDICT_RECOMMEND  # 契合 HIGH 且无 blocker
    assert any("账号定位「AI 工具实测」" in line for line in brief["answer"])
    assert any("命中账号定位词" in line for line in brief["answer"])
    assert any("当前策略支撑" in line for line in brief["answer"])
    assert brief["strategy_basis"]  # 策略文本命中 AI 工具关键词
    assert brief["caveats"] == []  # Confirmed 策略 + 无观察


def test_verdict_reject_low_fit(tmp_path):
    agent = StrategyAgent(memory=base_memory(tmp_path))

    brief = agent.run("x", {"candidates": [candidate(topic="美食探店攻略", category="未分类")]})["strategies"][0]

    assert brief["verdict"] == VERDICT_REJECT
    assert any("没有直接关联" in line for line in brief["answer"])


def test_details_render_lists_judgments(tmp_path):
    agent = StrategyAgent(memory=base_memory(tmp_path))

    result = agent.run("x", {"candidates": [candidate()]})

    assert "## 策略判断" in result["details"]
    assert candidate().topic in result["details"]
    assert VERDICT_RECOMMEND in result["details"]


# ── 历史内容 / 历史表现 ─────────────────────────────────────────────────


def test_history_overlap_downgrades_verdict(tmp_path):
    memory = base_memory(tmp_path)
    memory.create("content", "插件实测", {
        "日期": "2026-09-01", "主题": "Obsidian 长期记忆分层实测", "平台": "X",
        "内容形式": "Thread", "Hook": "h", "核心观点": "c", "内容表现摘要": "一般",
    })
    agent = StrategyAgent(memory=memory)

    brief = agent.run("x", {"candidates": [candidate()]})["strategies"][0]

    assert brief["history"] and "插件实测" in brief["history"][0]
    assert brief["verdict"] == VERDICT_JUDGE  # 与已发内容重合，即使契合 HIGH 也要人工判断
    assert any("与已发内容重合" in line for line in brief["answer"])


def test_observations_are_cited_but_do_not_change_score(tmp_path):
    memory = base_memory(tmp_path)
    memory.create("analytics", "工具类复盘", {
        "观察": "AI 工具类内容互动率高于均值 30%", "候选 Insight": "工具类内容可能更吃香（待复核）",
        "样本量": "12", "置信度": "中",
    })
    memory.create("insight", "工具类更吃香", {
        "主题": "AI 工具选题表现更好", "观察": "o", "证据": "e", "状态": "观察", "置信度": "中",
    })
    raw = TopicEngine(memory=memory).recommend([candidate()])["recommendations"]
    agent = StrategyAgent(memory=memory)

    brief = agent.run("x", {"recommendations": raw})["strategies"][0]

    assert brief["recommendation"] == raw[0]  # 分数原样透传，观察不改评分
    assert any("互动率高于均值" in line for line in brief["observations"])
    assert any("AI 工具选题表现更好" in line for line in brief["observations"])
    assert any("Memory Review" in line for line in brief["caveats"])


def test_missing_strategy_yields_caveat(tmp_path):
    agent = StrategyAgent(memory=base_memory(tmp_path, strategy=None))

    brief = agent.run("x", {"candidates": [candidate()]})["strategies"][0]

    assert any("没有当前策略记忆" in line for line in brief["caveats"])
    assert brief["strategy_basis"] == []
    assert not any("当前策略支撑" in line for line in brief["answer"])


def test_non_confirmed_strategy_is_only_a_reference(tmp_path):
    strategy = {**STRATEGY, "状态": "Observed"}
    agent = StrategyAgent(memory=base_memory(tmp_path, strategy=strategy))

    brief = agent.run("x", {"candidates": [candidate()]})["strategies"][0]

    assert any("策略状态为「Observed」" in line for line in brief["caveats"])


# ── 输入与只读保证 ──────────────────────────────────────────────────────


def test_missing_input_returns_failure(tmp_path):
    agent = StrategyAgent(memory=base_memory(tmp_path))

    result = agent.run("x")

    assert result["summary"].startswith("缺少输入")
    assert result["errors"] and result["strategies"] == [] and result["recommendations"] == []


def test_run_does_not_write_memory(tmp_path):
    memory = base_memory(tmp_path)
    before = {c: memory.list_notes(c) for c in ("account", "strategy", "content", "analytics", "research")}
    agent = StrategyAgent(memory=memory)

    agent.run("x", {"candidates": [candidate()]})

    after = {c: memory.list_notes(c) for c in before}
    assert after == before
    research_dir = tmp_path / "11-Research"
    assert not research_dir.exists() or not list(research_dir.glob("*.md"))
