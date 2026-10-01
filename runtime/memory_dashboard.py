"""Phase 20：Memory Dashboard——记忆系统最终该拥有的 7 个视图。

    Account Memory   账号现在是谁
    Strategy Memory  现在采取什么策略
    Learned Patterns 已经观察到什么
    Experiments      正在验证什么
    Decisions        过去为什么这样决定
    Agent Knowledge  Agent 学到了什么
    Memory Health    重复 / 过时 / 冲突 / 无来源 / 低置信度 / 元数据非法

边界：
- 只读：不写记忆、不改状态、不替人复核；输出与 Phase 19 dashboard 同构
  （title/columns/rows/note/count），直接当 section 渲染。
- 诚实：没数据的视图 rows 为空（页面显示「暂无数据」）；pending 观察明确标注
  「未经复核」，不冒充已验证结论。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from runtime.memory_api import MemoryAPI

VIEWS = (
    "Account Memory", "Strategy Memory", "Learned Patterns",
    "Experiments", "Decisions", "Agent Knowledge", "Memory Health",
)

HEALTH_LABELS = {
    "duplicate": "重复记忆",
    "conflict": "相互冲突",
    "stale": "过时记忆",
    "no_source": "无来源结论",
    "low_confidence": "低置信度结论",
    "invalid_metadata": "元数据非法",
}


def collect(memory: MemoryAPI) -> list[dict[str, Any]]:
    """7 个视图 → dashboard section 列表（顺序即 PLAN 顺序）。"""
    account = _fixed(memory, "account")
    strategy = _fixed(memory, "strategy")

    return [
        _view("Account Memory", "账号现在是谁", ["字段", "值"],
              [[key, value] for key, value in account.get("sections", {}).items()],
              "" if account.get("sections") else "还没有账号画像：缺画像时选题契合度只能判 UNKNOWN。"),
        _view("Strategy Memory", "现在采取什么策略", ["字段", "值"],
              [[key, value] for key, value in strategy.get("sections", {}).items()],
              "改策略必须人工 update + recordDecision，本页只读。" if strategy.get("sections") else ""),
        _view("Learned Patterns", "已经观察到什么", ["主题", "观察", "状态", "置信度"],
              [[entry["sections"].get("主题", ""), entry["sections"].get("观察", ""),
                entry["frontmatter"].get("status", ""), entry["frontmatter"].get("confidence", "")]
               for entry in _entries(memory, "insight")],
              "状态 pending = 待 Memory Review 的观察，未经复核不算已验证结论。"),
        _view("Experiments", "正在验证什么", ["编号", "假设", "预期结果", "结论", "状态"],
              [[entry["sections"].get("编号", "") or "—", entry["sections"].get("假设", ""),
                entry["sections"].get("预期结果", ""), entry["sections"].get("结论", ""),
                entry["frontmatter"].get("status", "")]
               for entry in _entries(memory, "experiment")],
              "status=active 表示仍在验证；结论为空即实验未收口。"),
        _view("Decisions", "过去为什么这样决定", ["日期", "事项", "决策", "原因"],
              [[entry["sections"].get("日期", ""), entry["sections"].get("事项", ""),
                entry["sections"].get("决策", ""), entry["sections"].get("原因", "")]
               for entry in _entries(memory, "decision")],
              "每次策略变更都应有一条 Decision 记录原因。"),
        _view("Agent Knowledge", "Agent 学到了什么", ["Agent", "经验", "状态"],
              [[entry["sections"].get("Agent", ""), entry["sections"].get("经验", ""),
                entry["frontmatter"].get("status", "")]
               for entry in _entries(memory, "agent")],
              "来自 16-Agent 的经验笔记；Archived 的不在此列。"),
        _health_view(memory),
    ]


def _view(title: str, subtitle: str, columns: list[str], rows: list[list[Any]],
          note: str) -> dict[str, Any]:
    return {
        "title": title,
        "columns": columns,
        "rows": [[_cell(value) for value in row] for row in rows],
        "note": f"{subtitle}　{note}".strip(),
        "count": len(rows),
    }


def _cell(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, (dict, list)):
        return str(value)
    return str(value)


def _fixed(memory: MemoryAPI, category: str) -> dict[str, Any]:
    """固定标题的视图（账号画像 / 当前策略）。"""
    found = _safe(lambda: memory.get(category), {"ok": False})
    if not found.get("ok"):
        return {"sections": {}, "frontmatter": {}}
    return {"sections": found.get("sections") or {},
            "frontmatter": found.get("frontmatter") or {}}


def _entries(memory: MemoryAPI, category: str) -> list[dict[str, Any]]:
    """某个分类下的在用笔记（frontmatter + sections），按标题排序。"""
    entries: list[dict[str, Any]] = []
    for path in _safe(lambda: memory.list_notes(category), []):
        title = Path(path).stem
        found = _safe(lambda: memory.get(category, title), {"ok": False})
        if not found.get("ok"):
            continue
        entries.append({"title": title,
                        "frontmatter": found.get("frontmatter") or {},
                        "sections": found.get("sections") or {}})
    return entries


def _health_view(memory: MemoryAPI) -> dict[str, Any]:
    health = _safe(lambda: memory.health(), {})
    summary = health.get("summary") or {}
    issues = health.get("issues") or {}
    rows = []
    for key, label in HEALTH_LABELS.items():
        count = int(summary.get(key, 0))
        rows.append([label, count, _representative(issues.get(key) or [])])
    note = (
        f"已巡检 {health.get('checked', 0)} 条笔记（不含 99-Archive）；"
        "只读报告，处置由人或 Memory Review 决定。"
    )
    return _view("Memory Health", "记忆体检", ["问题类型", "数量", "代表文件"], rows, note)


def _representative(issue_list: list[dict[str, Any]]) -> str:
    if not issue_list:
        return "—"
    first = issue_list[0]
    if first.get("path"):
        return str(first["path"])
    paths = first.get("paths") or []
    return str(paths[0]) if paths else "—"


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default
