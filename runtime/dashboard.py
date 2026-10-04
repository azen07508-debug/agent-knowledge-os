"""Phase 19：静态 Dashboard——把各 store 与长期记忆聚合成一页本地 HTML。

边界：
- 纯只读：不改数据、不跑 Agent、不联网、不加载任何外部资源（无 CDN、无 fetch）。
- 诚实：没有的数据就写「暂无 + 该跑哪个阶段」，不补占位数字、不猜热度。
- 单文件输出，双击即开；默认写 `data/dashboard.html`（data/ 已 gitignore）。
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from runtime.memory_api import MemoryAPI

PAGES = (
    "Dashboard", "Research", "Topics", "Content", "Calendar",
    "Review", "Publish", "Analytics", "Memory", "Accounts", "Settings",
)
"""PLAN Phase 19 的 11 个页面。"""

TS = "%Y-%m-%d %H:%M:%S"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_OUT = DATA_DIR / "dashboard.html"
PUBLISH_LOG = DATA_DIR / "publish_log.jsonl"

# 平台能力现状（PLAN Phase 13/15/16 的诚实状态，Settings 页展示）
PLATFORM_NOTES = {
    "x": "真实读写：XAdapter（opencli / twitter-cli）",
    "xiaohongshu": "CONTRACT_ONLY：可校验与演练，未接真实写/读 API",
    "douyin": "CONTRACT_ONLY：可校验与演练，未接真实写/读 API",
    "bilibili": "CONTRACT_ONLY：可校验与演练，未接真实写/读 API",
    "wechat_mp": "CONTRACT_ONLY：可校验与演练，未接真实写/读 API",
    "weibo": "CONTRACT_ONLY：可校验与演练，未接真实写/读 API",
    "channels": "CONTRACT_ONLY：可校验与演练，未接真实写/读 API",
}


# ── 数据聚合（只读） ──────────────────────────────────────────────────────


def collect(
    *,
    memory: MemoryAPI | None = None,
    research_store: Any | None = None,
    content_store: Any | None = None,
    publish_store: Any | None = None,
    analytics_store: Any | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    """按 11 个页面聚合数据；每个页面是若干 section（columns + rows + note）。"""
    memory = memory or MemoryAPI()
    research = research_store if research_store is not None else _store("research")
    content = content_store if content_store is not None else _store("content")
    publish = publish_store if publish_store is not None else _store("publish")
    analytics = analytics_store if analytics_store is not None else _store("analytics")

    research_items: list[dict] = _safe(lambda: research.search(limit=limit), [])
    contents: list[dict] = _safe(lambda: content.list(), [])
    jobs: list[Any] = _safe(lambda: publish.list_jobs(), [])
    snapshots: list[Any] = _safe(lambda: analytics.recent(limit=limit), [])
    insights = _insight_notes(memory)

    pages: dict[str, list[dict[str, Any]]] = {
        "Dashboard": _dashboard_sections(research_items, contents, jobs, snapshots,
                                         insights, memory),
        "Research": [_research_section(research_items)],
        "Topics": _topic_sections(research_items, memory),
        "Content": [_content_section(contents)],
        "Calendar": [_calendar_section(jobs)],
        "Review": _review_sections(contents),
        "Publish": _publish_sections(publish, jobs),
        "Analytics": _analytics_sections(analytics, snapshots),
        "Memory": _memory_sections(memory),
        "Accounts": _account_sections(jobs, contents),
        "Settings": [_settings_section(memory)],
    }

    return {
        "generated_at": datetime.now().strftime(TS),
        "pages": pages,
        "totals": {
            "research": _safe(lambda: research.count(), len(research_items)),
            "content": len(contents),
            "jobs": len(jobs),
            "snapshots": len(snapshots),
            "insights": len(insights),
        },
    }


def _store(kind: str) -> Any:
    """按需实例化项目自有 store（SQLite 本地文件，不联网）。"""
    if kind == "research":
        from runtime.research_store import ResearchStore

        return ResearchStore(DATA_DIR / "research.sqlite3")
    if kind == "content":
        from runtime.content_store import ContentStore

        return ContentStore(DATA_DIR / "content.sqlite3")
    if kind == "publish":
        from runtime.publish_queue import PublishJobStore

        return PublishJobStore(DATA_DIR / "publish.sqlite3")
    from runtime.analytics_store import AnalyticsStore

    return AnalyticsStore(DATA_DIR / "analytics.sqlite3")


def _safe(fn, default):
    """单个 store/记忆接口挂了不拖垮整页：降级成默认值（通常即「暂无数据」）。"""
    try:
        return fn()
    except Exception:
        return default


def _section(title: str, columns: list[str], rows: list[list[Any]],
             note: str = "") -> dict[str, Any]:
    return {"title": title, "columns": columns,
            "rows": [[_cell(value) for value in row] for row in rows],
            "note": note, "count": len(rows)}


def _cell(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


# ── 各页面 section ────────────────────────────────────────────────────────


def _research_section(items: list[dict]) -> dict[str, Any]:
    rows = [[item.get("title") or item.get("url"), item.get("source"),
             item.get("topic"), item.get("fetched_at")] for item in items]
    return _section("抓取材料", ["标题", "来源", "主题", "抓取时间"], rows,
                    f"最新 {len(rows)} 条；候选选题在 Topics 页")


def _hot_section(items: list[dict]) -> dict[str, Any]:
    """按来源互动数据排序；一个数字都没有就老实说排不了，不编热度。"""
    ranked: list[tuple[float, dict]] = []
    for item in items:
        engagement = item.get("engagement") or {}
        numbers = [value for value in engagement.values()
                   if isinstance(value, (int, float)) and not isinstance(value, bool)]
        if numbers:
            ranked.append((float(sum(numbers)), item))
    if not ranked:
        return _section("热点", ["标题", "来源", "抓取时间"],
                        [[item.get("title") or item.get("url"), item.get("source"),
                          item.get("fetched_at")] for item in items[:5]],
                        "来源没有互动数据，按抓取时间倒序展示——不编造热度。")
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return _section("热点", ["标题", "来源", "互动合计", "抓取时间"],
                    [[item.get("title") or item.get("url"), item.get("source"),
                      score, item.get("fetched_at")] for score, item in ranked[:5]],
                    "按来源给出的互动数字合计排序。")


def _recommendations(items: list[dict], memory: MemoryAPI) -> list[dict]:
    """研究材料 → 候选 → Topic Engine 推荐（纯本地规则，不联网）。"""
    if not items:
        return []
    try:
        from runtime.topic_engine import TopicEngine
        from runtime.topics import build_candidates

        candidates = build_candidates(items)
        if not candidates:
            return []
        return TopicEngine(memory=memory).recommend(candidates, top_k=10)["recommendations"]
    except Exception:
        return []


def _topic_sections(items: list[dict], memory: MemoryAPI) -> list[dict[str, Any]]:
    recommendations = _recommendations(items, memory)
    rows = [[rec.get("topic"), rec.get("category"), rec.get("score"),
             rec.get("account_fit"), "；".join(rec.get("blockers") or []) or "无"]
            for rec in recommendations]
    section = _section("推荐选题", ["选题", "分类", "分数", "账号契合", "阻塞"], rows,
                       "分数=证据+时效+账号契合；没有 Account Memory 时契合度全为 UNKNOWN")
    detail = _section("选题理由", ["选题", "为什么值得研究"],
                      [[rec.get("topic"), "；".join(rec.get("why") or [])]
                       for rec in recommendations])
    return [section, detail]


def _content_section(contents: list[dict]) -> dict[str, Any]:
    rows = [[item.get("topic"), item.get("status"), item.get("angle"),
             item.get("updated_at") or item.get("created_at")] for item in contents]
    return _section("内容对象", ["主题", "状态", "角度", "更新时间"], rows,
                    "状态链：IDEA → RESEARCHED → DRAFT → REVIEW → APPROVED → SCHEDULED → PUBLISHED")


def _calendar_section(jobs: list[Any]) -> dict[str, Any]:
    ordered = sorted(jobs, key=lambda job: (job.scheduled_at or "", job.created_at or ""))
    rows = [[job.scheduled_at, job.content_id, job.platform, job.status] for job in ordered]
    return _section("排期（发布队列）", ["到期时间", "内容", "平台", "状态"], rows,
                    "排期即 PublishJob.scheduled_at；队列为空时这里没有行")


def _review_sections(contents: list[dict]) -> list[dict[str, Any]]:
    pending = [item for item in contents if item.get("status") == "REVIEW"]
    rows = [[item.get("id"), item.get("topic"), len(item.get("claims") or []),
             len(item.get("evidence") or []), len(item.get("review_notes") or [])]
            for item in pending]
    section = _section("待人工审核", ["内容 ID", "主题", "断言", "证据", "审核记录"], rows,
                       "启动 scripts/review_server.py 后，点击内容 ID 进行审核")
    section["review_ids"] = [item.get("id") for item in pending]
    return [
        section,
        _section("已通过人审", ["内容 ID", "主题", "状态"],
                 [[item.get("id"), item.get("topic"), item.get("status")]
                  for item in contents
                  if item.get("status") in ("APPROVED", "SCHEDULED", "PUBLISHED")],
                 "只有 APPROVED 才会进发布队列"),
    ]


def _publish_sections(publish_store: Any, jobs: list[Any]) -> list[dict[str, Any]]:
    rows = []
    for job in jobs:
        attempts = _safe(lambda: publish_store.attempts(job.id), [])
        last = attempts[-1] if attempts else None
        rows.append([job.id[:8], job.content_id, job.platform, job.status, len(attempts),
                     getattr(last, "published_post_id", "") or "—"])
    queue = _section("发布作业", ["Job", "内容", "平台", "状态", "尝试", "post_id"], rows,
                     "重试=新 attempt，不覆盖旧记录；TIMEOUT 先对账再谈重试")
    log_rows = _publish_log_rows()
    log = _section(f"发布日志（最后 {len(log_rows)} 条）",
                   ["时间", "类型", "Job", "状态", "结果"], log_rows,
                   "PLAN Phase 15：所有发布行为必须记录日志")
    return [queue, log]


def _publish_log_rows(limit: int = 10) -> list[list[Any]]:
    if not PUBLISH_LOG.exists():
        return []
    try:
        lines = PUBLISH_LOG.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    rows: list[list[Any]] = []
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append([record.get("at"), record.get("kind"), record.get("job_id"),
                     record.get("status"), "成功" if record.get("ok") else "失败"])
    return rows


def _analytics_sections(analytics: Any, snapshots: list[Any]) -> list[dict[str, Any]]:
    counts = _safe(lambda: analytics.counts(), {})
    summary = _section("采集概览", ["指标", "数量"],
                       [[key, value] for key, value in counts.items()])
    rows = [[snap.post_id, snap.content_type or "—", snap.platform,
             snap.engagement, snap.engagement_rate, snap.collected_at]
            for snap in snapshots]
    detail = _section("最近采集快照", ["post", "类型", "平台", "互动", "互动率", "采集时间"], rows,
                      "互动率缺 views 时为 —（不算也不编）")
    return [summary, detail]


def _insight_notes(memory: MemoryAPI) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for path in _safe(lambda: memory.list_notes("insight"), []):
        title = Path(path).stem
        found = _safe(lambda: memory.get("insight", title), {"ok": False})
        if not found.get("ok"):
            continue
        notes.append({
            "title": title,
            "topic": found["sections"].get("主题", ""),
            "status": found["frontmatter"].get("status", ""),
            "confidence": found["frontmatter"].get("confidence", ""),
        })
    return notes


def _memory_sections(memory: MemoryAPI) -> list[dict[str, Any]]:
    """Phase 20：记忆系统的 7 个视图（Account/Strategy/Patterns/Experiments/
    Decisions/Agent Knowledge/Memory Health）。"""
    from runtime import memory_dashboard

    return memory_dashboard.collect(memory)


def _account_sections(jobs: list[Any], contents: list[dict]) -> list[dict[str, Any]]:
    """平台账号：谁在发、发过多少（账号画像与策略在 Memory 页前两个视图）。"""
    job_counts: dict[str, int] = {}
    for job in jobs:
        job_counts[job.platform] = job_counts.get(job.platform, 0) + 1
    post_counts: dict[str, int] = {}
    for item in contents:
        for platform in item.get("platform_versions") or {}:
            post_counts[platform] = post_counts.get(platform, 0) + 1

    rows = [[platform,
             "真实读写" if note.startswith("真实") else "CONTRACT_ONLY",
             post_counts.get(platform, 0), job_counts.get(platform, 0)]
            for platform, note in PLATFORM_NOTES.items()]
    return [_section("平台账号", ["平台", "能力", "发过内容", "发布作业"], rows,
                     "不探测登录态：X 后端状态见 Settings 与 X Layer；"
                     "账号画像 / 当前策略在 Memory 页的前两个视图。")]


def _settings_section(memory: MemoryAPI) -> dict[str, Any]:
    rows = [
        ["生成时间", datetime.now().strftime(TS)],
        ["项目根", str(DATA_DIR.parent)],
        ["输出文件", str(DEFAULT_OUT)],
        ["研究库", str(DATA_DIR / "research.sqlite3")],
        ["内容库", str(DATA_DIR / "content.sqlite3")],
        ["发布队列", str(DATA_DIR / "publish.sqlite3")],
        ["表现数据", str(DATA_DIR / "analytics.sqlite3")],
        ["发布日志", str(PUBLISH_LOG)],
        ["记忆库", str(_safe(lambda: memory.layer.vault_path, "—"))],
    ]
    rows += [[platform, note] for platform, note in PLATFORM_NOTES.items()]
    return _section("本地运行现状", ["项目", "值"], rows,
                    "全部数据在本机；本页面不联网、不读凭据、不加载外部资源")


def _dashboard_sections(
    items: list[dict],
    contents: list[dict],
    jobs: list[Any],
    snapshots: list[Any],
    insights: list[dict],
    memory: MemoryAPI,
) -> list[dict[str, Any]]:
    recommendations = _recommendations(items, memory)
    drafts = [item for item in contents if item.get("status") in ("IDEA", "RESEARCHED", "DRAFT")]
    reviews = [item for item in contents if item.get("status") == "REVIEW"]
    scheduled = [job for job in jobs if job.status in ("QUEUED", "RUNNING", "RETRYING")]
    published = [item for item in contents if item.get("status") == "PUBLISHED"]

    return [
        _section("今日研究", ["标题", "来源", "抓取时间"],
                 [[item.get("title") or item.get("url"), item.get("source"),
                   item.get("fetched_at")] for item in items[:5]],
                 f"最新抓取的 {min(5, len(items))} 条"),
        _hot_section(items),
        _section("推荐选题", ["选题", "分数", "账号契合"],
                 [[rec.get("topic"), rec.get("score"), rec.get("account_fit")]
                  for rec in recommendations[:5]], "详见 Topics 页"),
        _section("草稿", ["主题", "状态", "更新时间"],
                 [[item.get("topic"), item.get("status"), item.get("updated_at")]
                  for item in drafts[:5]]),
        _section("待审核", ["主题", "状态"],
                 [[item.get("topic"), item.get("status")] for item in reviews[:5]],
                 "人审闸门：approve() 之前不会发布"),
        _section("排期", ["到期时间", "内容", "平台"],
                 [[job.scheduled_at, job.content_id, job.platform] for job in scheduled[:5]]),
        _section("最近发布", ["主题", "状态"],
                 [[item.get("topic"), item.get("status")] for item in published[:5]]),
        _section("数据", ["指标", "数量"],
                 [["研究材料", len(items)], ["内容对象", len(contents)],
                  ["发布作业", len(jobs)], ["采集快照", len(snapshots)]]),
        _section("AI Insight", ["主题", "状态", "置信度"],
                 [[note["topic"], note["status"], note["confidence"]] for note in insights[:5]],
                 "pending=待 Memory Review，active=已验证"),
    ]


# ── 渲染（单文件 HTML，无外部资源） ───────────────────────────────────────


def render(data: dict[str, Any]) -> str:
    pages = data["pages"]
    nav_parts = []
    for index, page in enumerate(PAGES):
        active = " data-active" if index == 0 else ""
        nav_parts.append(f'<button class="nav" data-page="{_esc(page)}"{active}>{_esc(page)}</button>')
    body = "".join(_render_page(page, pages.get(page, [])) for page in PAGES)
    totals = (
        f"研究 {data['totals']['research']} · 内容 {data['totals']['content']} · "
        f"发布 {data['totals']['jobs']} · 快照 {data['totals']['snapshots']} · "
        f"洞察 {data['totals']['insights']}"
    )
    return _TEMPLATE.format(
        generated=_esc(data["generated_at"]),
        nav="".join(nav_parts),
        body=body,
        totals=_esc(totals),
    )


def _render_page(page: str, sections: list[dict[str, Any]]) -> str:
    cards = "".join(_render_section(section) for section in sections) or '<p class="empty">暂无数据。</p>'
    return f'<section class="page" id="page-{_esc(page)}"><h1>{_esc(page)}</h1>{cards}</section>'


def _render_section(section: dict[str, Any]) -> str:
    columns = "".join(f"<th>{_esc(column)}</th>" for column in section["columns"])
    if section["rows"]:
        body = "".join(
            "<tr>" + "".join(f"<td>{_esc(value)}</td>" for value in row) + "</tr>"
            for row in section["rows"]
        )
        if section.get("review_ids"):
            body = "".join(
                "<tr>" + "".join(f"<td>{_esc(value)}</td>" for value in row)
                + f'<td><button class="review-open" data-content-id="{_esc(row[0])}">打开审核</button></td></tr>'
                for row in section["rows"]
            )
            columns += "<th>操作</th>"
        table = f"<table><thead><tr>{columns}</tr></thead><tbody>{body}</tbody></table>"
    else:
        table = '<p class="empty">暂无数据。</p>'
    note = f'<p class="note">{_esc(section["note"])}</p>' if section.get("note") else ""
    return (
        f'<article class="card"><h2>{_esc(section["title"])}'
        f'<span class="count">{section["count"]}</span></h2>{table}{note}</article>'
    )


def _esc(value: Any) -> str:
    """所有进入 HTML 的值都转义：研究标题里可能带 <script>。"""
    return html.escape(str(value if value is not None else ""), quote=True)


def write(out_path: str | Path | None = None, data: dict[str, Any] | None = None) -> Path:
    """生成并写盘，返回文件路径。"""
    path = Path(out_path) if out_path else DEFAULT_OUT
    payload = data if data is not None else collect()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(payload), encoding="utf-8")
    return path


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CreatorOS 仪表盘</title>
<style>
:root {{ --bg:#0f1115; --panel:#171a21; --line:#252a34; --text:#e6e9ef; --muted:#8b93a3; --accent:#5aa9e6; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:14px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;
       background:var(--bg); color:var(--text); }}
.layout {{ display:flex; min-height:100vh; }}
nav {{ width:180px; flex:none; background:var(--panel); border-right:1px solid var(--line); padding:16px 8px; }}
nav .brand {{ font-weight:600; padding:0 8px 12px; color:var(--accent); }}
button.nav {{ display:block; width:100%; text-align:left; background:none; border:0; color:var(--muted);
              padding:8px; border-radius:6px; cursor:pointer; font:inherit; }}
button.nav:hover {{ background:#1e222b; color:var(--text); }}
button.nav[data-active] {{ background:#20293a; color:var(--text); }}
main {{ flex:1; padding:20px 24px 40px; }}
.meta {{ color:var(--muted); font-size:12px; margin-bottom:16px; }}
h1 {{ font-size:20px; margin:0 0 4px; }}
h2 {{ font-size:15px; margin:0 0 10px; display:flex; align-items:center; gap:8px; }}
.count {{ font-size:11px; color:var(--muted); background:#1e222b; border-radius:10px; padding:1px 8px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:14px;
         margin-bottom:14px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); vertical-align:top;
         word-break:break-word; }}
th {{ color:var(--muted); font-weight:500; }}
.note,.empty {{ color:var(--muted); font-size:12px; margin:8px 0 0; }}
footer {{ color:var(--muted); font-size:12px; padding:16px 24px; border-top:1px solid var(--line); }}
.page {{ display:none; }}
 .page[data-active] {{ display:block; }}
 .review-open,.review-action {{ border:1px solid var(--line); background:#20293a; color:var(--text); border-radius:6px; padding:5px 9px; cursor:pointer; }}
 .review-action {{ margin:6px 6px 0 0; }}
 #review-drawer {{ display:none; position:fixed; inset:6vh 6vw; overflow:auto; z-index:10; background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:20px; box-shadow:0 20px 80px #0009; }}
 #review-drawer[data-open] {{ display:block; }}
 #review-drawer pre {{ white-space:pre-wrap; background:#101217; padding:12px; border-radius:8px; }}
</style>
</head>
<body>
<div class="layout">
  <nav><div class="brand">CreatorOS</div>{nav}</nav>
   <main>
    <div class="meta">本地生成于 {generated} · {totals}</div>
    {body}
  </main>
</div>
<div id="review-drawer"><button id="review-close" class="review-action">关闭</button><div id="review-detail">加载中…</div></div>
<footer>本地数据视图：不联网、不加载外部资源。审核按钮仅调用本机 Review API；发布仍需单独人工确认。</footer>
<script>
document.querySelectorAll("button.nav").forEach(function (button) {{
  button.addEventListener("click", function () {{
    document.querySelectorAll("button.nav").forEach(function (item) {{ item.removeAttribute("data-active"); }});
    document.querySelectorAll("section.page").forEach(function (item) {{ item.removeAttribute("data-active"); }});
    button.setAttribute("data-active", "");
    document.getElementById("page-" + button.dataset.page).setAttribute("data-active", "");
  }});
}});
document.querySelector("section.page").setAttribute("data-active", "");
const drawer = document.getElementById("review-drawer");
const detail = document.getElementById("review-detail");
document.getElementById("review-close").onclick = () => drawer.removeAttribute("data-open");
document.querySelectorAll(".review-open").forEach(function(button) {{
  button.onclick = async function() {{
    drawer.setAttribute("data-open", "");
    const id = button.dataset.contentId;
    const response = await window["fetch"]("http://127.0.0.1:8765/api/review/" + encodeURIComponent(id));
    const packet = await response.json();
    if (!packet.ok) {{ detail.textContent = packet.message || "加载失败"; return; }}
    const posts = (packet.generated.posts || []).map((p, i) => `<p><b>${{i + 1}}.</b> ${{escapeHtml(p)}}</p>`).join("");
    const evidence = (packet.evidence || []).map(e => `<li>${{escapeHtml(e.url)}} — ${{escapeHtml(e.quote)}}</li>`).join("");
    detail.innerHTML = `<h2>${{escapeHtml(packet.content_id)}} · ${{escapeHtml(packet.status)}}</h2><p>证据状态：${{escapeHtml(packet.evidence_status || "见内容包")}}</p><h3>正文</h3>${{posts}}<h3>证据</h3><ul>${{evidence}}</ul><button class="review-action" data-action="approve">批准</button><button class="review-action" data-action="changes">要求修改</button>`;
    detail.querySelectorAll(".review-action[data-action]").forEach(action => action.onclick = async () => {{
      const note = action.dataset.action === "changes" ? prompt("请输入修改要求") : "";
      if (action.dataset.action === "changes" && !note) return;
      const endpoint = "http://127.0.0.1:8765/api/review/" + encodeURIComponent(id) + "/" + action.dataset.action;
      const result = await window["fetch"](endpoint, {{ method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify({{reviewer:"local-user",note}}) }}).then(r=>r.json());
      alert(result.ok ? "已完成：" + result.status : (result.message || "操作失败"));
      if (result.ok) drawer.removeAttribute("data-open");
    }});
  }};
}});
function escapeHtml(value) {{ const div=document.createElement("div"); div.textContent=String(value ?? ""); return div.innerHTML; }}
</script>
</body>
</html>
"""
