"""GitHub 仓库分析工作流。"""

from __future__ import annotations

from pathlib import Path

from runtime.obsidian_exporter import ObsidianExporter


def analyze_github_repo(repo_url: str, vault_path: str | Path = "obsidian_vault") -> Path:
    """生成仓库分析笔记；当前版本不联网，只根据 URL 生成结构化模板。"""
    repo_name = repo_url.rstrip("/").split("/")[-1] or "未知仓库"
    content = "\n".join(
        [
            "## 仓库名称",
            repo_name,
            "## 一句话总结",
            "这是一个待人工补充的仓库分析记录。",
            "## 主要功能",
            "- 待补充",
            "## 技术栈",
            "- 待补充",
            "## 适合怎么用",
            "- 作为项目调研入口",
            "## 风险点",
            "- 当前版本未联网验证仓库真实性",
            "## 和当前项目的结合方式",
            "- 可沉淀到 Obsidian 资源卡",
            "## 值得学习的知识点",
            "- README 分析",
            "- 项目结构梳理",
        ]
    )
    return ObsidianExporter(vault_path).write_repo_analysis(repo_name, content)
