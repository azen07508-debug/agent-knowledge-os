"""agent-knowledge-os demo 入口。"""

from __future__ import annotations

from pathlib import Path

from agents import CoderAgent, PlannerAgent, ResearcherAgent, ReviewerAgent
from runtime.arbiter_guard import ArbiterGuard
from runtime.everos_memory import EverOSMemory
from runtime.obsidian_exporter import ObsidianExporter


DEMO_TASK = "分析 EverOS + Arbiter + Obsidian 如何结合，构建 Codex 驱动的 AI 知识库系统"


def format_result(result: dict) -> str:
    """把 Agent 结果转成适合写入 Markdown 的中文内容。"""
    lines = [
        f"## 摘要\n\n{result['summary']}",
        f"## 详情\n\n{result['details']}",
        "## 知识点",
        *[f"- {item}" for item in result.get("knowledge_points", [])],
        "## 错误或风险",
        *[f"- {item}" for item in result.get("errors", []) or ["暂无。"]],
        "## 下一步",
        *[f"- {item}" for item in result.get("next_actions", [])],
    ]
    return "\n\n".join(lines)


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    vault_path = project_root / "obsidian_vault"

    arbiter = ArbiterGuard(vault_path=vault_path)
    everos = EverOSMemory()
    exporter = ObsidianExporter(vault_path=vault_path)

    agents = [PlannerAgent(), ResearcherAgent(), CoderAgent(), ReviewerAgent()]
    results: list[dict] = []
    generated_paths: list[Path] = []

    for agent in agents:
        budget = arbiter.request_budget(agent.name, agent.default_budget)
        if not budget["allowed"]:
            print(f"预算不足，跳过 {agent.name}：{budget['message']}")
            continue
        result = agent.run(DEMO_TASK, {"previous_results": results})
        results.append(result)
        everos_result = everos.add_memory(agent.name, DEMO_TASK, result)
        if not everos_result.get("ok"):
            print(everos_result.get("message", "EverOS 写入失败，本次继续执行本地 demo。"))

    planner_result, researcher_result, coder_result, reviewer_result = results

    generated_paths.append(
        exporter.write_project_note("Agent-Knowledge-OS", "项目计划", format_result(planner_result))
    )
    generated_paths.append(
        exporter.write_concept_card("长期记忆系统", format_result(researcher_result), ["concept", "memory"])
    )
    generated_paths.append(
        exporter.write_skill_card("Codex驱动开发", format_result(coder_result), ["skill", "codex"])
    )
    generated_paths.append(
        exporter.write_error_card(
            "本地部署常见错误",
            "\n".join(reviewer_result.get("errors", [])),
            reviewer_result["details"],
            ["error", "local-deploy"],
        )
    )
    generated_paths.append(
        exporter.write_repo_analysis("EverOS-Arbiter-组合分析", format_result(researcher_result))
    )

    print("Arbiter 状态：")
    print(arbiter.status())
    print("生成的 Markdown 文件：")
    for path in generated_paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
