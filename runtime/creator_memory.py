"""CreatorOS 长期记忆层（Phase 1）。

职责：Store what the system has learned, not everything the system has seen.
只存经过筛选、验证、总结之后未来还用得上的东西，不存帖子原文、API 返回和数据库职责。

生命周期：Capture -> Normalize -> Validate -> Store -> Retrieve -> Update -> Archive
    Capture   各 save_* 方法接收调用方给出的事实
    Normalize 字段裁剪、列表转 bullet、补时间戳
    Validate  必填字段、枚举状态、单条长度上限
    Store     Obsidian 落盘（source of truth）+ EverOS 尽力同步
    Retrieve  recall() 先查 EverOS，降级为 vault 全文匹配
    Update    账号画像必须带 reason，自动产生 Decision Record
    Archive   移入 99-Archive 并把 status 改为 archived

分类与 CreatorOS Phase 1 规格一致：
    /Account /Strategy /Research /Content /Experiments
    /Analytics /Decisions /Agent /Insights
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from runtime.everos_memory import DEFAULT_OWNER_ID, EverOSMemory
from runtime.obsidian_exporter import ObsidianExporter, parse_note

MAX_CHARS = 4000
"""单条记忆上限：超限说明在塞原文或原始 API 返回，先总结再写入。"""

CONFIDENCE = ("低", "中", "高")
STRATEGY_STATE = ("已确认", "已观察", "假设", "未知")  # Confirmed / Observed / Hypothesis / Unknown
INSIGHT_STATUS = ("观察", "待验证", "已验证")
EXPERIMENT_CONCLUSION = ("暂时支持", "暂时不支持", "数据不足")

STATUS = ("active", "pending", "archived", "superseded")
"""治理状态：ACTIVE 在用 / PENDING 待复核 / ARCHIVED 已归档 / SUPERSEDED 已被取代。"""

CONFIDENCE_LEVEL = ("LOW", "MEDIUM", "HIGH")
"""frontmatter 里的置信度（Phase 3 规格枚举），正文仍写中文便于阅读。"""

CONFIDENCE_TO_LEVEL = {zh: level for zh, level in zip(CONFIDENCE, CONFIDENCE_LEVEL)}

STRATEGY_STATE_CONFIDENCE = {"已确认": "HIGH", "已观察": "MEDIUM", "假设": "LOW", "未知": "LOW"}

UNKNOWN_SOURCE = "unknown"
"""未标注来源时的显式占位值：Memory Health 据此找出无来源结论。"""

ARCHIVE_FOLDER = "99-Archive"
ACCOUNT_TITLE = "账号画像"


def confidence_level(value: str) -> str:
    """把中文置信度（低/中/高）映射为 LOW/MEDIUM/HIGH，已在英文枚举内则原样返回。"""
    if value in CONFIDENCE_LEVEL:
        return value
    if value in CONFIDENCE_TO_LEVEL:
        return CONFIDENCE_TO_LEVEL[value]
    raise ValueError(f"置信度只能是 {'/'.join(CONFIDENCE)} 或 {'/'.join(CONFIDENCE_LEVEL)}。")


def render_sections(sections: Mapping[str, str]) -> str:
    """把结构化字段渲染成 `## 小节` 形式的 Markdown 正文。"""
    return "\n\n".join(f"## {key}\n{value}".rstrip() for key, value in sections.items())


@dataclass(frozen=True)
class MemoryCategory:
    key: str
    name: str
    folder: str
    note_type: str
    required: tuple[str, ...]
    overwrite: bool = False
    fixed_title: str | None = None


CATEGORIES: tuple[MemoryCategory, ...] = (
    MemoryCategory(
        "account",
        "账号是谁",
        "09-Account",
        "account",
        (
            "账号定位",
            "目标受众",
            "内容领域",
            "内容支柱",
            "表达风格",
            "长期目标",
            "禁止内容",
            "平台差异",
            "账号阶段",
        ),
        overwrite=True,
        fixed_title="账号画像",
    ),
    MemoryCategory(
        "strategy",
        "当前策略",
        "10-Strategy",
        "strategy",
        ("当前内容策略", "内容支柱", "目标方向", "状态", "策略变更原因"),
        overwrite=True,
        fixed_title="当前内容策略",
    ),
    MemoryCategory(
        "research",
        "研究过什么",
        "11-Research",
        "research",
        ("主题", "关键结论", "重要来源", "研究时间"),
    ),
    MemoryCategory(
        "content",
        "发过什么",
        "12-Content",
        "content",
        ("日期", "主题", "平台", "内容形式", "Hook", "核心观点", "内容表现摘要"),
    ),
    MemoryCategory(
        "experiment",
        "验证什么",
        "13-Experiments",
        "experiment",
        ("编号", "假设", "变量", "预期结果", "结论", "置信度", "下一步"),
    ),
    MemoryCategory(
        "analytics",
        "数据说明什么",
        "14-Analytics",
        "analytics",
        ("观察", "候选 Insight", "样本量", "置信度"),
    ),
    MemoryCategory(
        "decision",
        "为什么这样决定",
        "15-Decisions",
        "decision",
        ("日期", "事项", "决策", "原因"),
    ),
    MemoryCategory(
        "agent",
        "Agent 学到什么",
        "16-Agent",
        "agent-experience",
        ("Agent", "经验"),
    ),
    MemoryCategory(
        "insight",
        "什么有效",
        "17-Insights",
        "insight",
        ("主题", "观察", "证据", "状态", "置信度"),
    ),
)

CATEGORY_BY_KEY: dict[str, MemoryCategory] = {category.key: category for category in CATEGORIES}


def _bullets(value: str | Iterable[str] | Mapping[str, str] | int | None) -> str:
    """把列表或键值对渲染成 Markdown 列表，空值返回占位符。"""
    if value is None:
        return "暂无"
    if isinstance(value, str):
        return value.strip() or "暂无"
    if isinstance(value, Mapping):
        items = [f"{key}：{item}" for key, item in value.items()]
    elif isinstance(value, int):  # 数量类字段直接渲染成一行，迭代 int 会炸
        items = [str(value)]
    else:
        items = [str(item) for item in value]
    items = [item for item in items if str(item).strip()]
    return "\n".join(f"- {item}" for item in items) or "暂无"


class CreatorMemoryLayer:
    """CreatorOS 的长期记忆层：写 Obsidian，检索走 EverOS，失败就降级。"""

    def __init__(
        self,
        vault_path: str | Path = "obsidian_vault",
        everos: EverOSMemory | None = None,
        owner_id: str = DEFAULT_OWNER_ID,
    ) -> None:
        self.exporter = ObsidianExporter(vault_path)
        self.vault_path: Path = self.exporter.vault_path
        self.everos = everos or EverOSMemory()
        self.owner_id = owner_id
        self._sessions: set[str] = set()

    # ── 生命周期：Normalize + Validate + Store ───────────────────────────

    def remember(
        self,
        category: str,
        title: str,
        sections: Mapping[str, Any],
        tags: list[str] | None = None,
        status: str = "active",
        created: str | None = None,
        updated: str | None = None,
        confidence: str | None = None,
        source: str | None = None,
        in_place: bool = False,
    ) -> dict[str, Any]:
        """按类别写入一条记忆：规范化、校验、落盘、尽力同步 EverOS。

        status/created/updated/confidence/source 透传给 frontmatter，供 update 保留原始元数据；
        in_place=True 表示原地改写同名笔记（update/复核/取代走这里），跳过同名内容比对。
        """
        spec = self._spec(category)
        if status not in STATUS:
            raise ValueError(f"记忆状态只能是 {'/'.join(STATUS)}。")
        normalized = {key: str(value).strip() for key, value in sections.items()}
        self._validate(spec, normalized)

        body = render_sections(normalized)
        if len(body) > MAX_CHARS:
            raise ValueError(
                f"单条记忆 {len(body)} 字符，超过上限 {MAX_CHARS}：本层只存总结后的经验，不存原文或 API 返回。"
            )

        note_title = spec.fixed_title or title
        existing = self.exporter.note_path(spec.folder, note_title)
        if not in_place and not spec.fixed_title and existing.exists():
            _, existing_sections = parse_note(existing.read_text(encoding="utf-8"))
            if existing_sections != normalized:
                # 同名不同内容会互相覆盖：按正文短哈希区分；内容相同则原地覆盖，保持幂等。
                note_title = f"{note_title}-{hashlib.sha1(body.encode('utf-8')).hexdigest()[:6]}"
        path = self.exporter.write_note(
            spec.folder,
            note_title,
            body,
            spec.note_type,
            tags or [spec.key],
            status=status,
            created=created,
            updated=updated,
            confidence=confidence_level(confidence) if confidence else "MEDIUM",
            source=source or UNKNOWN_SOURCE,
        )

        session_id = f"creator-memory-{category}"
        self._sessions.add(session_id)
        everos_result = self.everos.append(
            f"[{spec.name}] {note_title}\n{body}",
            session_id=session_id,
            sender_id=self.owner_id,
        )
        return {
            "ok": True,
            "category": category,
            "title": note_title,
            "path": str(path),
            "everos": everos_result,
        }

    def _spec(self, category: str) -> MemoryCategory:
        spec = CATEGORY_BY_KEY.get(category)
        if spec is None:
            raise ValueError(f"未知记忆类别：{category}，可选：{', '.join(CATEGORY_BY_KEY)}")
        return spec

    def _validate(self, spec: MemoryCategory, sections: Mapping[str, str]) -> None:
        missing = [field for field in spec.required if not sections.get(field, "").strip()]
        if missing:
            raise ValueError(f"{spec.name}缺少必填字段：{', '.join(missing)}")

    @staticmethod
    def _today() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    # ── 1.2 Account Memory ───────────────────────────────────────────────

    def save_account(
        self,
        profile: Mapping[str, Any],
        reason: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """创建或修改账号画像。

        画像已存在时必须给出 reason：重要修改会同时产生一条 Decision Record，
        避免 Agent 随意改动账号定位。
        """
        existing = self._account_note().exists()
        if existing and not (reason or "").strip():
            raise ValueError(
                "账号画像已存在，修改必须提供 reason（会自动产生 Decision Record）；"
                "请调用 update_account(profile, reason) 或 MemoryAPI.update(...)。"
            )
        record = self.remember(
            "account",
            ACCOUNT_TITLE,
            profile,
            ["account", "creator-os"],
            confidence="中",
            source=source,
        )
        if existing:
            record["decision"] = self.save_decision(
                subject="账号画像调整",
                decision="更新账号长期定位",
                reason=reason or "",
            )
        return record

    def update_account(self, profile: Mapping[str, Any], reason: str) -> dict[str, Any]:
        """修改账号画像的唯一入口：reason 必填，并落一条决策记录。"""
        if not (reason or "").strip():
            raise ValueError("账号画像修改必须写明原因。")
        return self.save_account(profile, reason=reason)

    def _account_note(self) -> Path:
        return self.vault_path / CATEGORY_BY_KEY["account"].folder / f"{ACCOUNT_TITLE}.md"

    # ── 1.3 Strategy Memory ──────────────────────────────────────────────

    def save_strategy(
        self,
        current: str,
        pillars: str | Iterable[str],
        direction: str,
        verified: str | Iterable[str] | None = None,
        pending: str | Iterable[str] | None = None,
        paused: str | Iterable[str] | None = None,
        change_reason: str = "首次建立策略",
        state: str = "已观察",
        source: str | None = None,
    ) -> dict[str, Any]:
        """保存当前内容策略。state 必须落在 已确认/已观察/假设/未知 之内。"""
        if state not in STRATEGY_STATE:
            raise ValueError(f"策略状态只能是 {'/'.join(STRATEGY_STATE)}，不能把猜测写成事实。")
        sections = {
            "当前内容策略": current,
            "内容支柱": _bullets(pillars),
            "目标方向": direction,
            "已验证策略": _bullets(verified),
            "待验证策略": _bullets(pending),
            "暂停策略": _bullets(paused),
            "状态": state,
            "策略变更原因": change_reason,
            "更新时间": self._today(),
        }
        record = self.remember(
            "strategy",
            "当前内容策略",
            sections,
            ["strategy"],
            confidence=STRATEGY_STATE_CONFIDENCE[state],
            source=source,
        )
        if change_reason and change_reason != "首次建立策略":
            record["decision"] = self.save_decision(
                subject="内容策略调整",
                decision=current,
                reason=change_reason,
            )
        return record

    # ── 1.4 Research Memory ──────────────────────────────────────────────

    def save_research(
        self,
        topic: str,
        conclusions: str | Iterable[str],
        sources: str | Iterable[str],
        verified: str | Iterable[str] | None = None,
        unverified: str | Iterable[str] | None = None,
        studied_at: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """保存研究结果：结论 + 来源 + 已验证/未验证边界，不存原始抓取数据。"""
        sections = {
            "主题": topic,
            "关键结论": _bullets(conclusions),
            "重要来源": _bullets(sources),
            "已验证信息": _bullets(verified),
            "未验证信息": _bullets(unverified),
            "研究时间": studied_at or self._today(),
        }
        return self.remember("research", f"研究-{topic}", sections, ["research"], source=source)

    # ── 1.5 Content Memory ───────────────────────────────────────────────

    def save_content(
        self,
        topic: str,
        platform: str,
        form: str,
        hook: str,
        core_point: str,
        performance: str = "暂无数据",
        lessons: str | Iterable[str] | None = None,
        date: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """保存一条已产出内容的摘要与经验，不存帖子全文。"""
        day = date or self._today()
        sections = {
            "日期": day,
            "主题": topic,
            "平台": platform,
            "内容形式": form,
            "Hook": hook,
            "核心观点": core_point,
            "内容表现摘要": performance,
            "后续经验": _bullets(lessons),
        }
        return self.remember("content", f"{day}-{platform}-{topic}", sections, ["content"], source=source)

    # ── 1.6 Experiment Memory ────────────────────────────────────────────

    def save_experiment(
        self,
        hypothesis: str,
        variables: Mapping[str, str] | Iterable[str],
        expected: str,
        conclusion: str,
        confidence: str = "低",
        actual: str = "尚未回收数据",
        evidence: str = "暂无",
        next_action: str = "继续收集样本",
        number: int | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """实验记录：结论只能是 暂时支持/暂时不支持/数据不足，置信度只能是 低/中/高。"""
        if conclusion not in EXPERIMENT_CONCLUSION:
            raise ValueError(f"实验结论只能是 {'/'.join(EXPERIMENT_CONCLUSION)}，不要把偶然结果写成定论。")
        if confidence not in CONFIDENCE:
            raise ValueError(f"置信度只能是 {'/'.join(CONFIDENCE)}。")
        experiment_number = number or self._next_experiment_number()
        sections = {
            "编号": f"Experiment #{experiment_number:03d}",
            "假设": hypothesis,
            "变量": _bullets(variables),
            "预期结果": expected,
            "实际结果": actual,
            "证据": evidence,
            "结论": conclusion,
            "置信度": confidence,
            "下一步": next_action,
            "记录时间": self._today(),
        }
        return self.remember(
            "experiment",
            f"Experiment-{experiment_number:03d}",
            sections,
            ["experiment"],
            confidence=confidence,
            source=source,
        )

    # ── 1.7 Analytics Memory ─────────────────────────────────────────────

    def save_analytics(
        self,
        observation: str,
        candidate_insight: str,
        sample_size: int,
        confidence: str = "低",
        metrics: Mapping[str, str] | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """记录分析结果：只产出候选 Insight，不直接改长期策略。

        流程固定为 Analytics -> 分析 -> 候选 Insight -> Memory Review -> 长期记忆。
        写入时 status=pending，等 Memory Review 复核通过才转 active。
        """
        if confidence not in CONFIDENCE:
            raise ValueError(f"置信度只能是 {'/'.join(CONFIDENCE)}。")
        sections = {
            "观察": observation,
            "候选 Insight": candidate_insight,
            "样本量": str(sample_size),
            "关键指标": _bullets(metrics),
            "置信度": confidence,
            "处理状态": "待 Memory Review（未经复核不得写入长期策略）",
            "记录时间": self._today(),
        }
        return self.remember(
            "analytics",
            f"{self._today()}-分析记录",
            sections,
            ["analytics"],
            status="pending",
            confidence=confidence,
            source=source,
        )

    # ── 1.9 Decision Memory ──────────────────────────────────────────────

    def save_decision(
        self,
        subject: str,
        decision: str,
        reason: str,
        date: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """记录重要决策：以后能回答「为什么没做」。"""
        day = date or self._today()
        sections = {"日期": day, "事项": subject, "决策": decision, "原因": reason}
        return self.remember(
            "decision",
            f"{day}-决策-{subject}",
            sections,
            ["decision"],
            confidence="中",
            source=source,
        )

    # ── 1.8 Agent Memory ─────────────────────────────────────────────────

    def save_agent_experience(
        self,
        agent: str,
        experience: str,
        evidence: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """按 Agent 分别记录经验（Research / Content / Analytics / Publisher ...）。"""
        sections = {"Agent": agent, "经验": experience, "证据": evidence or "暂无", "记录时间": self._today()}
        return self.remember(
            "agent",
            f"{self._today()}-{agent}-经验",
            sections,
            ["agent"],
            confidence="中",
            source=source,
        )

    # ── 1.7 续：Insights（候选观察的沉淀） ─────────────────────────────────

    def save_insight(
        self,
        observation: str,
        evidence: str,
        status: str = "观察",
        topic: str | None = None,
        confidence: str = "低",
        source: str | None = None,
    ) -> dict[str, Any]:
        """沉淀「什么有效」：必须带证据，只能记成观察，不能一次数据变永久规则。

        frontmatter status：已验证 -> active，观察/待验证 -> pending（等 Memory Review）。
        """
        if status not in INSIGHT_STATUS:
            raise ValueError(f"状态只能是 {'/'.join(INSIGHT_STATUS)}，一次数据不能直接写成永久规则。")
        if confidence not in CONFIDENCE:
            raise ValueError(f"置信度只能是 {'/'.join(CONFIDENCE)}。")
        label = topic or observation[:16]
        kind = "观察" if status == "观察" else "洞察"
        sections = {
            "主题": topic or "未分类",
            "观察": observation,
            "证据": evidence,
            "状态": status,
            "置信度": confidence,
            "记录时间": self._today(),
        }
        return self.remember(
            "insight",
            f"{self._today()}-{kind}-{label}",
            sections,
            ["insight"],
            status="active" if status == "已验证" else "pending",
            confidence=confidence,
            source=source,
        )

    # ── Retrieve / Update / Archive ──────────────────────────────────────

    def recall(self, query: str, top_k: int = 5) -> dict[str, Any]:
        """先查 EverOS，服务不可用或无结果时降级为本地 vault 全文匹配。"""
        everos_result = self.everos.search_memory(query, top_k=top_k, owner_id=self.owner_id)
        if everos_result.get("ok") and everos_result.get("data"):
            return {"ok": True, "source": "everos", "query": query, "data": everos_result["data"]}

        matches = self.search_local(query, top_k)
        return {
            "ok": True,
            "source": "obsidian",
            "query": query,
            "matches": matches,
            "message": everos_result.get("message", "EverOS 无结果，已降级为本地检索。"),
        }

    def search_local(self, query: str, top_k: int = 5, folder: str | None = None) -> list[dict[str, Any]]:
        """vault 全文匹配；指定 folder 时只搜该类别目录。"""
        keyword = query.lower()
        root = self.vault_path / folder if folder else self.vault_path
        scored: list[dict[str, Any]] = []
        if not root.exists():
            return []
        for path in sorted(root.rglob("*.md")):
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            hits = text.count(keyword)
            if hits:
                scored.append({"path": str(path.relative_to(self.vault_path)), "score": hits})
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]

    def list_notes(self, category: str) -> list[str]:
        """列出某类别的在用记忆（不含已归档）。"""
        spec = self._spec(category)
        folder = self.vault_path / spec.folder
        if not folder.exists():
            return []
        return [str(path.relative_to(self.vault_path)) for path in sorted(folder.glob("*.md"))]

    def archive(self, category: str, title: str) -> dict[str, Any]:
        """把一条记忆移入 99-Archive，并把 frontmatter status 改为 archived。"""
        spec = self._spec(category)
        # 走 note_path：标题里的 `:` 等字符写入时会被 _safe_filename 换掉，
        # 手工拼路径会导致「写得进去、找不到文件」，驳回复核直接 FileNotFoundError。
        source = self.exporter.note_path(spec.folder, title)
        if not source.exists():
            raise FileNotFoundError(f"找不到记忆：{source}")
        target_dir = self.vault_path / ARCHIVE_FOLDER / spec.folder
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        if target.exists():
            raise FileExistsError(f"归档目标已存在，拒绝覆盖：{target}")

        text = source.read_text(encoding="utf-8")
        # 兼容迁移前仍写 draft 的笔记
        target.write_text(
            re.sub(r"^status: .*$", "status: archived", text, count=1, flags=re.MULTILINE),
            encoding="utf-8",
        )
        source.unlink()
        return {
            "ok": True,
            "category": category,
            "title": title,
            "archived_to": str(target.relative_to(self.vault_path)),
        }

    def flush(self) -> list[dict[str, Any]]:
        """把已写入的 session 切分成 EverOS 长期记忆。"""
        return [
            {"session_id": session_id, "result": self.everos.flush_memory(session_id)}
            for session_id in sorted(self._sessions)
        ]

    def _next_experiment_number(self) -> int:
        folder = self.vault_path / CATEGORY_BY_KEY["experiment"].folder
        numbers = [
            int(match.group(1))
            for path in folder.glob("Experiment-*.md")
            if (match := re.match(r"Experiment-(\d+)", path.stem))
        ]
        return max(numbers, default=0) + 1
