"""CreatorOS Memory API（Phase 2）。

后续 Agent（Research / Content / Analytics / Publisher）只通过本模块读写长期记忆，
不要直接打开 obsidian_vault 下的文件：写入规则、边界校验、更新与归档语义都集中在这一层。

    from runtime.memory_api import MemoryAPI

    memory = MemoryAPI()
    memory.search("项目实测", category="insight")
    memory.get("account")
    memory.create("decision", "2026-09-28-决策-x", {...})
    memory.update("strategy", "当前内容策略", {"当前内容策略": "..."})
    memory.archive("insight", "2026-09-28-观察-内容类型")
    memory.recordObservation(topic=..., observation=..., evidence=...)
    memory.recordHypothesis(hypothesis=..., expected=...)
    memory.recordExperiment(...)
    memory.recordDecision(...)
    memory.recordInsight(...)

检索优先走 EverOS，服务不可用时降级为 vault 全文匹配；写入永远先落 Obsidian。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from runtime.creator_memory import (
    CATEGORY_BY_KEY,
    CONFIDENCE_LEVEL,
    STATUS,
    UNKNOWN_SOURCE,
    CreatorMemoryLayer,
    MemoryCategory,
    render_sections,
)
from runtime.everos_memory import DEFAULT_OWNER_ID, EverOSMemory
from runtime.obsidian_exporter import parse_note

DEFAULT_VAULT = Path(__file__).resolve().parents[1] / "obsidian_vault"

ACCOUNT_KEY = "account"


class MemoryAPI:
    """CreatorOS 的统一记忆入口：CRUD + 领域记录方法。"""

    def __init__(
        self,
        vault_path: str | Path | None = None,
        everos: EverOSMemory | None = None,
        owner_id: str = DEFAULT_OWNER_ID,
    ) -> None:
        self.layer = CreatorMemoryLayer(vault_path or DEFAULT_VAULT, everos=everos, owner_id=owner_id)

    # ── 基础 CRUD ────────────────────────────────────────────────────────

    def create(
        self,
        category: str,
        title: str,
        sections: Mapping[str, Any],
        tags: list[str] | None = None,
        status: str = "active",
        confidence: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """新建一条记忆。Account 属于固定单篇，已存在时会要求改用 update。"""
        if self._spec(category).key == ACCOUNT_KEY:
            return self.layer.save_account(sections, source=source)
        return self.layer.remember(
            category,
            title,
            sections,
            tags,
            status=status,
            confidence=confidence,
            source=source,
        )

    def get(self, category: str, title: str | None = None) -> dict[str, Any]:
        """读取一条记忆，返回 frontmatter 与结构化 sections；不存在返回 ok=False。"""
        spec = self._spec(category)
        note_title = spec.fixed_title or title
        if not note_title:
            raise ValueError(f"{spec.name}不是固定单篇，get 必须提供 title。")
        path = self.layer.exporter.note_path(spec.folder, note_title)
        if not path.exists():
            return {
                "ok": False,
                "category": category,
                "title": note_title,
                "message": f"记忆不存在：{spec.folder}/{note_title}",
            }
        frontmatter, sections = parse_note(path.read_text(encoding="utf-8"))
        return {
            "ok": True,
            "category": category,
            "title": note_title,
            "path": str(path.relative_to(self.layer.vault_path)),
            "frontmatter": frontmatter,
            "sections": sections,
        }

    def update(
        self,
        category: str,
        title: str | None,
        sections: Mapping[str, Any],
        reason: str | None = None,
        status: str | None = None,
        confidence: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """合并更新一条已有记忆：保留 created，不改变状态/置信度/来源（除非显式传）。

        Account 更新必须带 reason，会同时产生 Decision Record。
        """
        spec = self._spec(category)
        if spec.key == ACCOUNT_KEY:
            return self.layer.save_account(sections, reason=reason, source=source)

        note_title = spec.fixed_title or title
        if not note_title:
            raise ValueError(f"{spec.name}不是固定单篇，update 必须提供 title。")
        current = self.get(category, note_title)
        if not current["ok"]:
            raise FileNotFoundError(current["message"])

        frontmatter = current["frontmatter"]
        merged = {**current["sections"], **{key: str(value) for key, value in sections.items()}}
        tags = frontmatter.get("tags") if isinstance(frontmatter.get("tags"), list) else None
        record = self.layer.remember(
            category,
            note_title,
            merged,
            tags=tags,
            status=status or str(frontmatter.get("status") or "active"),
            created=str(frontmatter.get("created")) if frontmatter.get("created") else None,
            confidence=confidence or _fm_value(frontmatter, "confidence"),
            source=source or _fm_value(frontmatter, "source"),
            in_place=True,
        )
        record["updated_from"] = current["path"]
        return record

    def list_notes(self, category: str) -> list[str]:
        """列出某类别的在用记忆路径（不含已归档）；只读。"""
        return self.layer.list_notes(category)

    def search(self, query: str, category: str | None = None, top_k: int = 5) -> dict[str, Any]:
        """检索记忆。指定 category 时只在该类别内做本地匹配。"""
        if category:
            spec = self._spec(category)
            return {
                "ok": True,
                "source": "obsidian",
                "query": query,
                "category": category,
                "matches": self.layer.search_local(query, top_k, folder=spec.folder),
            }
        return self.layer.recall(query, top_k)

    def archive(self, category: str, title: str) -> dict[str, Any]:
        """归档一条记忆：移入 99-Archive 并把 status 改为 archived。"""
        return self.layer.archive(category, title)

    def review(
        self,
        category: str,
        title: str | None,
        approved: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Memory Review：通过 -> active；驳回 -> 归档（不进入在用集合），理由写进笔记。"""
        sections = {"复核意见": reason} if reason else {}
        if approved:
            return self.update(category, title, sections, status="active")

        spec = self._spec(category)
        note_title = spec.fixed_title or title
        if not note_title:
            raise ValueError(f"{spec.name}不是固定单篇，review 必须提供 title。")
        if reason:
            self.update(category, title, sections, status="archived")
        return self.archive(category, note_title)

    def supersede(self, category: str, title: str | None, reason: str) -> dict[str, Any]:
        """标记一条记忆已被后续结论取代：status -> superseded，取代原因必须写明。"""
        if not (reason or "").strip():
            raise ValueError("取代一条记忆必须写明原因，否则等于悄悄失忆。")
        return self.update(category, title, {"取代原因": reason}, status="superseded")

    # ── 治理（Phase 3） ──────────────────────────────────────────────────

    def health(self, stale_days: int = 90) -> dict[str, Any]:
        """Memory Health 巡检：重复、过时、冲突、无来源、低置信度、元数据非法。

        只扫 09-17 九个记忆目录（已归档的在 99-Archive，天然不参与）。
        只读不改，问题以清单形式返回，由人或 Memory Review 决定处置。
        """
        issues: dict[str, list[dict[str, Any]]] = {
            "duplicate": [],
            "conflict": [],
            "stale": [],
            "no_source": [],
            "low_confidence": [],
            "invalid_metadata": [],
        }
        entries = self._entries()
        now = datetime.now()

        by_body: dict[tuple[str, str], list[dict[str, Any]]] = {}
        by_topic: dict[tuple[str, str], list[tuple[dict[str, Any], str]]] = {}

        for entry in entries:
            frontmatter, sections = entry["frontmatter"], entry["sections"]
            status = str(frontmatter.get("status") or "")
            confidence = str(frontmatter.get("confidence") or "")
            source = str(frontmatter.get("source") or "").strip()

            if status not in STATUS or confidence not in CONFIDENCE_LEVEL:
                issues["invalid_metadata"].append(
                    {"path": entry["path"], "status": status or "缺失", "confidence": confidence or "缺失"}
                )
            if source in ("", UNKNOWN_SOURCE):
                issues["no_source"].append({"path": entry["path"], "category": entry["category"]})
            if confidence == "LOW" and status in ("active", "pending"):
                issues["low_confidence"].append({"path": entry["path"], "category": entry["category"]})

            updated = _parse_time(frontmatter.get("updated"))
            if status == "active" and updated and (now - updated).days > stale_days:
                issues["stale"].append({"path": entry["path"], "days": (now - updated).days})

            body = render_sections(sections)
            by_body.setdefault((entry["category"], body), []).append(entry)
            topic_key = _group_key(sections)
            if topic_key and status in ("active", "pending"):
                by_topic.setdefault((entry["category"], topic_key), []).append((entry, body))

        for (category, _body), duplicate_entries in by_body.items():
            if len(duplicate_entries) > 1:
                issues["duplicate"].append(
                    {"category": category, "paths": [e["path"] for e in duplicate_entries]}
                )
        for (category, topic_key), topic_entries in by_topic.items():
            if len(topic_entries) > 1 and len({body for _entry, body in topic_entries}) > 1:
                issues["conflict"].append(
                    {"category": category, "topic": topic_key,
                     "paths": [entry["path"] for entry, _ in topic_entries]}
                )

        return {
            "ok": True,
            "checked": len(entries),
            "summary": {key: len(value) for key, value in issues.items()},
            "issues": issues,
        }

    def _entries(self) -> list[dict[str, Any]]:
        """读取 9 个记忆目录下的全部笔记（不含 99-Archive）。"""
        entries: list[dict[str, Any]] = []
        for spec in CATEGORY_BY_KEY.values():
            folder = self.layer.vault_path / spec.folder
            if not folder.exists():
                continue
            for path in sorted(folder.glob("*.md")):
                frontmatter, sections = parse_note(path.read_text(encoding="utf-8"))
                entries.append(
                    {
                        "category": spec.key,
                        "title": path.stem,
                        "path": str(path.relative_to(self.layer.vault_path)),
                        "frontmatter": frontmatter,
                        "sections": sections,
                    }
                )
        return entries

    def _spec(self, category: str) -> MemoryCategory:
        spec = CATEGORY_BY_KEY.get(category)
        if spec is None:
            raise ValueError(f"未知记忆类别：{category}，可选：{', '.join(CATEGORY_BY_KEY)}")
        return spec

    # ── 领域记录方法 ─────────────────────────────────────────────────────

    def recordObservation(
        self,
        topic: str,
        observation: str,
        evidence: str,
        confidence: str = "低",
        source: str | None = None,
    ) -> dict[str, Any]:
        """记录一条原始观察（未复核），frontmatter status=pending。"""
        return self.layer.save_insight(
            observation=observation,
            evidence=evidence,
            status="观察",
            topic=topic,
            confidence=confidence,
            source=source,
        )

    def recordInsight(
        self,
        topic: str,
        insight: str,
        evidence: str,
        confidence: str = "中",
        status: str = "已验证",
        source: str | None = None,
    ) -> dict[str, Any]:
        """记录一条经过 Memory Review 的洞察。"""
        return self.layer.save_insight(
            observation=insight,
            evidence=evidence,
            status=status,
            topic=topic,
            confidence=confidence,
            source=source,
        )

    def recordDecision(
        self,
        subject: str,
        decision: str,
        reason: str,
        date: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """记录一条决策（为什么做、为什么没做）。"""
        return self.layer.save_decision(subject=subject, decision=decision, reason=reason, date=date, source=source)

    def recordExperiment(self, **kwargs: Any) -> dict[str, Any]:
        """记录一条实验，字段与 CreatorMemoryLayer.save_experiment 一致。"""
        return self.layer.save_experiment(**kwargs)

    def recordHypothesis(
        self,
        hypothesis: str,
        variables: Any = None,
        expected: str = "待定义",
        next_action: str = "设计实验收集数据",
        source: str | None = None,
    ) -> dict[str, Any]:
        """登记一个待验证假设：自动变成「数据不足」状态的实验，等数据回填。"""
        return self.layer.save_experiment(
            hypothesis=hypothesis,
            variables=variables if variables is not None else ["变量待定义"],
            expected=expected,
            actual="尚未回收数据",
            evidence="暂无",
            conclusion="数据不足",
            confidence="低",
            next_action=next_action,
            source=source,
        )


def _fm_value(frontmatter: Mapping[str, Any], key: str) -> str | None:
    """取 frontmatter 字段的非空字符串值，缺失返回 None。"""
    value = frontmatter.get(key)
    text = str(value).strip() if value is not None else ""
    return text or None


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _group_key(sections: Mapping[str, str]) -> str | None:
    """冲突检测的分组键：同一主题/事项/假设/Agent 下的多条记忆需要互相对得上。"""
    for key in ("主题", "事项", "假设", "Agent"):
        value = sections.get(key, "").strip()
        if value:
            return f"{key}:{value}"
    return None
