#!/usr/bin/env python3
"""用 CreatorOS Phase 1 的 9 类长期记忆初始化 vault，并演示检索与降级。

默认幂等：已初始化过就直接退出，只有加 --force 才重写示例数据。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime.creator_memory import CATEGORIES, CreatorMemoryLayer

ACCOUNT = {
    "账号定位": "AI / Web3 / 开源工具 的实测型内容账号",
    "目标受众": "开发者、AI Agent 玩家、Web3 用户",
    "内容领域": "AI 工具、开源项目、Agent 基础设施",
    "内容支柱": "项目实测、项目拆解、工作流复盘",
    "表达风格": "实测 > 空谈；数据 > 猜测；项目拆解 > 新闻搬运",
    "长期目标": "沉淀一套可复用的开源项目评测方法论",
    "禁止内容": "无实测的收益承诺、蹭热点的标题党",
    "平台差异": "X 走 Thread 长度；小红书走图文卡片；国内平台不搬运未验证结论",
    "账号阶段": "冷启动期，先验证内容类型，不追粉丝数",
}


def seed(layer: CreatorMemoryLayer) -> list[dict]:
    records = [
        layer.save_account(ACCOUNT),
        layer.save_strategy(
            current="以「真实项目拆解 + 实测证据」为主线，先在 X 验证内容类型，再复制到国内平台。",
            pillars=["项目实测", "项目拆解", "工作流复盘"],
            direction="先做深一个垂直（Agent 工具），不做泛 AI 新闻。",
            verified=["项目实测类 Thread 的互动高于纯新闻类（样本 1，观察级）"],
            pending=["小红书图文拆解是否复用同一套选题", "口播形式是否适合抖音"],
            paused=["蹭热点快讯"],
            state="已观察",
        ),
        layer.save_research(
            topic="Agent-Reach",
            conclusions=["覆盖 16 个平台的多后端路由，6 个渠道零配置可用", "定位是内容获取层，不做加工和写操作"],
            sources=["https://github.com/…/agent-reach（README 与 SKILL.md）"],
            verified=["`agent-reach doctor --json` 可查看各平台由哪个后端服务"],
            unverified=["零配置渠道的信息质量是否足够做选题"],
            studied_at="2026-09-28",
        ),
        layer.save_content(
            topic="Agent-Reach",
            platform="X",
            form="Thread",
            hook="我拿一个 16 平台的调研工具，实际跑了一遍 6 个渠道。",
            core_point="真实项目拆解 + 实际使用体验，比转述新闻更适合当前账号。",
            performance="曝光 12,000，互动 453（2026-09-28）",
            lessons=["首条给出实测数据的开场，读完率高于概念开场"],
            date="2026-09-28",
        ),
        layer.save_experiment(
            hypothesis="项目实测类 Thread 比新闻类 Thread 更适合账号",
            variables={"主题": "Agent-Reach", "Hook": "首条用实测数据开场", "长度": "6 条", "发布时间": "晚间"},
            expected="互动率高于账号历史均值",
            actual="曝光 12,000 / 互动 453，高于账号均值；对照组（新闻类）同期更低",
            evidence="2026-09-28 两条内容后台数据对比",
            conclusion="暂时支持",
            confidence="低",
            next_action="再跑 5 条同类内容，补齐样本后再升级结论",
            number=1,
        ),
        layer.save_analytics(
            observation="最近 5 条内容里，项目拆解类的平均互动率高于新闻类。",
            candidate_insight="项目拆解可能是当前账号更合适的内容类型",
            sample_size=5,
            confidence="低",
            metrics={"平均互动率（拆解类）": "高于账号均值", "平均互动率（新闻类）": "低于账号均值"},
        ),
        layer.save_insight(
            observation="直接讲 AI 新闻的互动明显低于拆一个真实 GitHub 项目并实测。",
            evidence="2026-09-28 前后多条内容对比：新闻类低于账号均值，实测类曝光 12,000 / 互动 453。",
            status="观察",
            topic="内容类型",
            confidence="低",
        ),
        layer.save_agent_experience(
            agent="Research Agent",
            experience="热点聚合类来源噪音很高，直接喂给 Content Agent 会写出同质化内容。",
            evidence="两次选题调研中，聚合页结论高度重复。",
        ),
        layer.save_decision(
            subject="AI 生成标题",
            decision="未采用",
            reason="人工判断过度营销，与「实测 > 空谈」的账号定位冲突。",
            date="2026-09-28",
        ),
    ]
    return records


def main() -> int:
    vault_path = PROJECT_ROOT / "obsidian_vault"
    force = "--force" in sys.argv[1:]
    account_note = vault_path / "09-Account" / "账号画像.md"
    if account_note.exists() and not force:
        print(f"已初始化过（{account_note}），示例数据不再重复写入。如需重新写入请加 --force。")
        return 0

    layer = CreatorMemoryLayer(vault_path=vault_path)

    records = seed(layer)
    print("已写入记忆：")
    for record in records:
        everos = record["everos"]
        state = "EverOS 已同步" if everos.get("ok") else everos.get("message", "EverOS 跳过")
        print(f"  [{record['category']}] {record['path']}  <- {state}")
        if "decision" in record:
            print(f"      + 决策记录：{record['decision']['path']}")

    print("\n类别覆盖：")
    for category in CATEGORIES:
        print(f"  {category.key}: {category.name} -> {category.folder}")

    print("\n检索演示：")
    recall = layer.recall("项目实测")
    print(f"  来源：{recall['source']}")
    for match in recall.get("matches", []):
        print(f"  - {match['path']}（命中 {match['score']} 次）")

    print("\nEverOS flush：")
    for item in layer.flush():
        result = item["result"]
        print(f"  {item['session_id']}: {result.get('message') or result.get('data')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
