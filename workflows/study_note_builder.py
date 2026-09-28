"""学习笔记生成工作流。"""

from __future__ import annotations

from pathlib import Path

from runtime.obsidian_exporter import ObsidianExporter


def build_study_notes(topic: str, vault_path: str | Path = "obsidian_vault") -> list[Path]:
    """围绕学习主题生成概念卡、技能卡和 Prompt 卡。"""
    exporter = ObsidianExporter(vault_path)
    concept = exporter.write_concept_card(topic, f"## 一句话解释\n\n{topic} 的核心概念待补充。", ["concept"])
    skill = exporter.write_skill_card(f"{topic} 实践技能", "## 操作步骤\n\n1. 明确目标。\n2. 本地验证。\n3. 写入复盘。", ["skill"])
    prompt = exporter.write_note(
        "07-Prompts",
        f"{topic} Prompt",
        "## 使用场景\n\n用于生成结构化学习笔记。\n\n## Prompt 正文\n\n请围绕主题输出概念、步骤、风险和练习。",
        "prompt",
        ["prompt"],
    )
    return [concept, skill, prompt]
