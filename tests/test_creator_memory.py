import pytest

from runtime.creator_memory import (
    CATEGORIES,
    CONFIDENCE,
    EXPERIMENT_CONCLUSION,
    INSIGHT_STATUS,
    MAX_CHARS,
    STRATEGY_STATE,
    CreatorMemoryLayer,
)

ACCOUNT = {
    "账号定位": "AI 工具实测",
    "目标受众": "开发者",
    "内容领域": "开源项目",
    "内容支柱": "项目实测",
    "表达风格": "实测 > 空谈",
    "长期目标": "沉淀评测方法论",
    "禁止内容": "收益承诺",
    "平台差异": "X 走 Thread，小红书走图文",
    "账号阶段": "冷启动",
}


def make_layer(tmp_path) -> CreatorMemoryLayer:
    return CreatorMemoryLayer(vault_path=tmp_path)


# ── 分类结构 ──────────────────────────────────────────────────────────────


def test_nine_categories_match_phase1_spec():
    assert [category.key for category in CATEGORIES] == [
        "account",
        "strategy",
        "research",
        "content",
        "experiment",
        "analytics",
        "decision",
        "agent",
        "insight",
    ]
    assert [category.folder for category in CATEGORIES] == [
        "09-Account",
        "10-Strategy",
        "11-Research",
        "12-Content",
        "13-Experiments",
        "14-Analytics",
        "15-Decisions",
        "16-Agent",
        "17-Insights",
    ]


def test_account_and_strategy_are_single_overwrite_notes():
    assert CATEGORIES[0].overwrite is True
    assert CATEGORIES[1].overwrite is True
    assert CATEGORIES[2].overwrite is False


# ── 通用校验 ──────────────────────────────────────────────────────────────


def test_unknown_category_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="未知记忆类别"):
        make_layer(tmp_path).remember("whatever", "标题", {"观察": "x"})


def test_missing_required_field_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="缺少必填字段"):
        make_layer(tmp_path).save_decision(subject="选题", decision="放弃", reason="")


def test_oversized_memory_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="超过上限"):
        make_layer(tmp_path).save_insight(observation="x" * MAX_CHARS, evidence="y")
    assert not (tmp_path / "17-Insights").exists()


# ── Account：不可被随意修改 ───────────────────────────────────────────────


def test_account_created_once(tmp_path):
    layer = make_layer(tmp_path)
    record = layer.save_account(ACCOUNT)

    assert (tmp_path / "09-Account" / "账号画像.md").exists()
    assert record["category"] == "account"


def test_account_update_requires_reason_and_writes_decision(tmp_path):
    layer = make_layer(tmp_path)
    layer.save_account(ACCOUNT)

    with pytest.raises(ValueError, match="必须提供 reason"):
        layer.save_account({**ACCOUNT, "账号定位": "改定位"})

    record = layer.update_account({**ACCOUNT, "账号定位": "改定位"}, reason="受众反馈偏开发者")
    assert record["decision"]["category"] == "decision"
    decisions = layer.list_notes("decision")
    assert len(decisions) == 1
    assert "受众反馈偏开发者" in (tmp_path / decisions[0]).read_text(encoding="utf-8")


def test_account_requires_all_nine_fields(tmp_path):
    with pytest.raises(ValueError, match="缺少必填字段"):
        make_layer(tmp_path).save_account({"账号定位": "AI 工具实测"})


# ── Strategy ─────────────────────────────────────────────────────────────


def test_strategy_state_must_be_recognized(tmp_path):
    layer = make_layer(tmp_path)
    with pytest.raises(ValueError, match="策略状态"):
        layer.save_strategy(current="c", pillars=["p"], direction="d", state="肯定有效")

    record = layer.save_strategy(current="c", pillars=["p"], direction="d", state="假设")
    assert (tmp_path / "10-Strategy" / "当前内容策略.md").exists()
    assert "decision" not in record


def test_strategy_change_creates_decision(tmp_path):
    layer = make_layer(tmp_path)
    record = layer.save_strategy(
        current="以项目实测为主",
        pillars=["项目实测"],
        direction="垂直做深",
        change_reason="新闻类互动持续走低",
        state="已确认",
    )

    assert record["decision"]["category"] == "decision"
    assert len(layer.list_notes("decision")) == 1


# ── Research / Content ──────────────────────────────────────────────────


def test_research_requires_sources(tmp_path):
    layer = make_layer(tmp_path)
    with pytest.raises(ValueError, match="缺少必填字段"):
        layer.remember("research", "研究-Agent-Reach", {"主题": "Agent-Reach"})

    layer.save_research(
        topic="Agent-Reach",
        conclusions=["c1", "c2"],
        sources=["https://github.com/…"],
        verified=["f1"],
        unverified=["h1"],
    )
    text = (tmp_path / "11-Research" / "研究-Agent-Reach.md").read_text(encoding="utf-8")
    assert "- c1" in text and "未验证信息" in text and "研究时间" in text


def test_content_memory_keeps_summary_not_full_post(tmp_path):
    layer = make_layer(tmp_path)
    layer.save_content(
        topic="Agent-Reach",
        platform="X",
        form="Thread",
        hook="实测开场",
        core_point="项目拆解更适合当前账号",
        performance="曝光 12,000 / 互动 453",
        lessons=["首条给数据"],
        date="2026-09-28",
    )
    text = (tmp_path / "12-Content" / "2026-09-28-X-Agent-Reach.md").read_text(encoding="utf-8")

    assert "## Hook" in text and "## 后续经验" in text


# ── Experiment ───────────────────────────────────────────────────────────


def test_experiment_requires_full_schema(tmp_path):
    layer = make_layer(tmp_path)
    with pytest.raises(ValueError, match="缺少必填字段"):
        layer.remember("experiment", "Experiment-001", {"编号": "Experiment #001", "假设": "h"})

    record = layer.save_experiment(
        hypothesis="实测类 Thread 更适合账号",
        variables=["主题", "Hook"],
        expected="互动率更高",
        actual="高于均值",
        evidence="两条内容对比",
        conclusion="暂时支持",
        confidence="低",
        next_action="再跑 5 条",
    )
    text = (tmp_path / "13-Experiments" / "Experiment-001.md").read_text(encoding="utf-8")

    assert "Experiment #001" in text
    assert "## 预期结果" in text and "## 证据" in text and "## 下一步" in text
    assert record["title"] == "Experiment-001"


def test_experiment_enums_are_bounded(tmp_path):
    layer = make_layer(tmp_path)
    with pytest.raises(ValueError, match="实验结论"):
        layer.save_experiment(hypothesis="h", variables=["v"], expected="e", conclusion="爆款秘诀")
    with pytest.raises(ValueError, match="置信度"):
        layer.save_experiment(
            hypothesis="h", variables=["v"], expected="e", conclusion="数据不足", confidence="极高"
        )

    assert EXPERIMENT_CONCLUSION == ("暂时支持", "暂时不支持", "数据不足")
    assert CONFIDENCE == ("低", "中", "高")


def test_experiment_number_increments(tmp_path):
    layer = make_layer(tmp_path)
    layer.save_experiment(hypothesis="h1", variables=["v"], expected="e", conclusion="数据不足")
    layer.save_experiment(hypothesis="h2", variables=["v"], expected="e", conclusion="数据不足")

    assert (tmp_path / "13-Experiments" / "Experiment-002.md").exists()


# ── Analytics：不直接改策略 ──────────────────────────────────────────────


def test_analytics_produces_candidate_insight_only(tmp_path):
    layer = make_layer(tmp_path)
    record = layer.save_analytics(
        observation="5 条项目拆解内容平均互动率更高",
        candidate_insight="项目拆解可能更适合当前账号",
        sample_size=5,
        confidence="低",
    )

    text = (tmp_path / "14-Analytics" / record["title"]).with_suffix(".md").read_text(encoding="utf-8")
    assert "候选 Insight" in text
    assert "待 Memory Review" in text
    assert "样本量\n5" in text


def test_analytics_confidence_is_bounded(tmp_path):
    with pytest.raises(ValueError, match="置信度"):
        make_layer(tmp_path).save_analytics(
            observation="o", candidate_insight="i", sample_size=1, confidence="极高"
        )


# ── Insight ─────────────────────────────────────────────────────────────


def test_insight_cannot_become_permanent_rule(tmp_path):
    layer = make_layer(tmp_path)
    with pytest.raises(ValueError, match="永久规则"):
        layer.save_insight(observation="实测类更有效", evidence="一次数据", status="永久规则")

    layer.save_insight(observation="实测类更有效", evidence="多条对比", status="已验证", confidence="中")
    text = (tmp_path / "17-Insights" / layer.list_notes("insight")[0].split("/")[-1]).read_text(encoding="utf-8")
    assert "## 状态" in text and "## 置信度" in text
    assert INSIGHT_STATUS == ("观察", "待验证", "已验证")
    assert STRATEGY_STATE == ("已确认", "已观察", "假设", "未知")


# ── Agent / Decision ────────────────────────────────────────────────────


def test_agent_experience_and_decision(tmp_path):
    layer = make_layer(tmp_path)
    layer.save_agent_experience(agent="Content Agent", experience="项目介绍容易写成宣传稿", evidence="两次返工")
    layer.save_decision(subject="AI 生成标题", decision="未采用", reason="过度营销", date="2026-09-28")

    assert (tmp_path / "16-Agent").exists()
    text = (tmp_path / "15-Decisions" / "2026-09-28-决策-AI 生成标题.md").read_text(encoding="utf-8")
    assert "过度营销" in text


# ── 生命周期：Retrieve / Archive ────────────────────────────────────────


def test_recall_falls_back_to_local_vault(tmp_path):
    layer = make_layer(tmp_path)
    layer.save_research(topic="Agent-Reach", conclusions=["多后端路由"], sources=["github"])
    result = layer.recall("多后端路由")

    assert result["source"] == "obsidian"
    assert result["matches"][0]["path"].startswith("11-Research/")


def test_archive_moves_note_and_marks_status(tmp_path):
    layer = make_layer(tmp_path)
    layer.save_agent_experience(agent="X Agent", experience="Thread 前两条密度影响读完率")
    note = layer.list_notes("agent")[0].split("/")[-1].removesuffix(".md")

    result = layer.archive("agent", note)

    assert result["archived_to"].startswith("99-Archive/16-Agent/")
    assert not (tmp_path / "16-Agent" / f"{note}.md").exists()
    archived = (tmp_path / result["archived_to"]).read_text(encoding="utf-8")
    assert "status: archived" in archived
    assert layer.list_notes("agent") == []


def test_archive_rejects_missing_and_existing_target(tmp_path):
    layer = make_layer(tmp_path)
    layer.save_agent_experience(agent="X Agent", experience="e")
    note = layer.list_notes("agent")[0].split("/")[-1].removesuffix(".md")

    with pytest.raises(FileNotFoundError):
        layer.archive("agent", "不存在的笔记")

    layer.archive("agent", note)
    layer.save_agent_experience(agent="X Agent", experience="同名重写")
    with pytest.raises(FileExistsError):
        layer.archive("agent", note)
