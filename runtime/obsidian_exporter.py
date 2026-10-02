"""Obsidian Markdown 导出器。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


class ObsidianExporter:
    """把 Agent 结果写入本地 Obsidian vault。"""

    def __init__(self, vault_path: str | Path = "obsidian_vault") -> None:
        self.vault_path = Path(vault_path)
        self.vault_path.mkdir(parents=True, exist_ok=True)

    def _safe_filename(self, title: str) -> str:
        cleaned = re.sub(r'[\\/:*?"<>|]', "-", title).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned or "未命名笔记"

    def _frontmatter(
        self,
        note_type: str,
        tags: list[str] | None,
        status: str,
        created: str,
        updated: str,
        confidence: str,
        source: str,
    ) -> str:
        tag_lines = "\n".join(f"  - {tag}" for tag in (tags or []))
        if not tag_lines:
            tag_lines = "  - knowledge"
        return (
            "---\n"
            f"type: {note_type}\n"
            f"status: {status}\n"
            f"created: {created}\n"
            f"updated: {updated}\n"
            f"confidence: {confidence}\n"
            "tags:\n"
            f"{tag_lines}\n"
            f"source: {source}\n"
            "related: []\n"
            "---\n\n"
        )

    def note_path(self, folder: str, title: str) -> Path:
        """返回某标题的落盘路径（不写入），用于判断是否已存在。"""
        return self.vault_path / folder / f"{self._safe_filename(title)}.md"

    def write_note(
        self,
        folder: str,
        title: str,
        content: str,
        note_type: str = "note",
        tags: list[str] | None = None,
        status: str = "active",
        created: str | None = None,
        updated: str | None = None,
        confidence: str = "MEDIUM",
        source: str = "agent-knowledge-os",
    ) -> Path:
        """写入 Markdown 笔记并返回路径。

        created/updated 缺省为当前时间；status 取值 active/pending/archived/superseded。
        """
        path = self.note_path(folder, title)
        path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        frontmatter = self._frontmatter(
            note_type,
            tags,
            status=status,
            created=created or now,
            updated=updated or now,
            confidence=confidence,
            source=source,
        )
        path.write_text(frontmatter + f"# {title}\n\n{content.strip()}\n", encoding="utf-8")
        return path

    def write_project_note(self, project_name: str, title: str, content: str) -> Path:
        return self.write_note(f"01-Projects/{project_name}", title, content, "project", ["project"])

    def write_concept_card(self, title: str, content: str, tags: list[str] | None = None) -> Path:
        return self.write_note("03-Concepts", title, content, "concept", tags or ["concept"])

    def write_skill_card(self, title: str, content: str, tags: list[str] | None = None) -> Path:
        return self.write_note("02-Skills", title, content, "skill", tags or ["skill"])

    def write_error_card(self, title: str, error_text: str, solution: str, tags: list[str] | None = None) -> Path:
        content = f"## 报错原文\n\n{error_text}\n\n## 解决方案\n\n{solution}"
        return self.write_note("04-Errors", title, content, "error", tags or ["error"])

    def write_repo_analysis(self, repo_name: str, content: str) -> Path:
        return self.write_note("06-Resources/GitHub-Repos", repo_name, content, "repo-analysis", ["github", "repo-analysis"])

    def write_daily_review(self, content: str) -> Path:
        date_title = datetime.now().strftime("%Y-%m-%d-每日复盘")
        return self.write_note("08-Daily", date_title, content, "daily-review", ["daily-review"])


def parse_note(text: str) -> tuple[dict[str, object], dict[str, str]]:
    """把一条笔记解析成 (frontmatter, sections)，供读取与内容比对使用。"""
    frontmatter: dict[str, object] = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            _parse_frontmatter(text[4:end], frontmatter)
            body = text[end + len("\n---\n") :]

    sections: dict[str, str] = {}
    current: str | None = None
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = ""
        elif current is not None:
            sections[current] = f"{sections[current]}\n{line}".strip("\n")
    return frontmatter, {key: value.strip() for key, value in sections.items()}


def _parse_frontmatter(raw: str, out: dict[str, object]) -> None:
    key: str | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line[:1] in (" ", "\t") and key:
            item = line.strip()
            if item.startswith("- "):
                item = item[2:]
            bucket = out.get(key)
            if not isinstance(bucket, list):
                bucket = [bucket] if bucket else []
                out[key] = bucket
            bucket.append(item)
            continue
        name, _, value = line.partition(":")
        key = name.strip()
        out[key] = value.strip() or []
