#!/usr/bin/env python3
"""Phase 22 最终能力入口：早报 / 多平台生成 / 发布 / 晚报。

    python scripts/briefing.py morning --materials m.json  # 10 个话题 + 3 个最符合定位（本地）
    python scripts/briefing.py morning --channel github --research   # 联网调研（默认关闭）
    python scripts/briefing.py generate <content_id>        # 生成 X/小红书/抖音/B站 版本（不外发）
    python scripts/briefing.py publish <content_id>         # 发布回执（默认：X 缺能力、六平台 CONTRACT_ONLY）
    python scripts/briefing.py publish <content_id> --send  # 显式真实发送 X（需已 APPROVED）
    python scripts/briefing.py evening                      # 当日表现 + 记忆待办
    python scripts/briefing.py evening --collect            # 顺带跑 X 指标采集
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.briefing import DEFAULT_PLATFORMS, Briefing
from agents.researcher import ResearcherAgent, default_research_query


def _load_json(path: str):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"文件必须是 JSON 数组：{path}")
    return data


def _candidates(args) -> list[dict]:
    """早报的候选选题：默认本地 materials；channel 必须显式 --research 才允许联网。"""
    context: dict = {}
    if args.materials:
        context["materials"] = _load_json(args.materials)
    if args.channel:
        if not args.research:
            raise SystemExit("--channel 需要同时给 --research 才允许联网调研（默认不联网）。")
        context["channel"] = args.channel
        query = args.query or default_research_query()
        if query:
            context["query"] = query
            print(f"调研检索词：{query}")
    if not context:
        return []
    outcome = ResearcherAgent().run("早报候选", context)
    for error in outcome.get("errors") or []:
        print(f"调研错误：{error}")
    return list(outcome.get("candidates") or [])


def cmd_morning(args) -> int:
    briefing = Briefing()
    result = briefing.morning(_candidates(args), limit=args.limit, top=args.top)
    print(result["summary"])
    if not result["ok"]:
        return 1
    for note in result["warnings"]:
        print(f"  ! {note}")
    print("今天值得关注的话题：")
    for index, item in enumerate(result["topics"], 1):
        print(f"  {index:>2}. [{item['account_fit']}] {item['topic']}（分 {item['score']}）")
    print("最符合当前账号定位：")
    if not result["top_fit"]:
        print("  （没有 HIGH 契合的选题，不凑数）")
    for item in result["top_fit"]:
        print(f"  - {item['topic']}：{'；'.join(item.get('why') or []) or '见上'}")
    return 0


def cmd_generate(args) -> int:
    result = Briefing().generate(args.content_id, platforms=tuple(args.platforms))
    print(result["summary"])
    for item in result["versions"]:
        if not item.get("ok"):
            print(f"  ✗ {item['platform']}：{item.get('message')}")
            continue
        mark = "✓" if item["valid"] else "✗ 契约不过"
        print(f"  {mark} {item['label']}（{item['platform']}）")
        for error in item["errors"]:
            print(f"      错误：{error}")
        for warning in item["warnings"]:
            print(f"      建议：{warning}")
        if item["preview"]:
            print("      预览：" + item["preview"].replace("\n", "\n             "))
    return 0 if result["ok"] else 1


def cmd_publish(args) -> int:
    from agents.x_workflow import XWorkflow

    x_workflow = XWorkflow() if args.send else None
    if args.send:
        print("已开启 X 真实发送（--send）：只发 APPROVED 内容。")
    result = Briefing().publish(args.content_id, platforms=tuple(args.platforms),
                                x_workflow=x_workflow)
    print(result["summary"])
    for item in result["results"]:
        mark = "✓" if item["ok"] else "✗"
        print(f"  {mark} {item['platform']}：{item['message']}")
    return 0 if result["ok"] else 1


def cmd_evening(args) -> int:
    collector = None
    if args.collect:
        from runtime.analytics_collector import AnalyticsCollector
        from runtime.publish_queue import PublishJobStore
        from runtime.x_adapter import default_x_adapter

        collector = AnalyticsCollector(store=_analytics_store(), x=default_x_adapter(),
                                       publish_store=PublishJobStore())
        print("已开启指标采集（--collect）：走 X 后端，失败会如实记录。")
    else:
        print("未开启采集（--collect）：本次只分析已有表现数据。")

    result = Briefing().evening(collector=collector, limit=args.limit,
                                write_memory=not args.no_write_memory)
    print(f"晚报：{result['summary'] or '（没有可分析的表现数据）'}")
    for note in result["warnings"]:
        print(f"  ! {note}")
    print(f"写入观察 {result['memory_writes']} 条（pending，需 Memory Review 才算已验证）。")
    if result["pending_review"]:
        print("等你复核的观察：")
        for item in result["pending_review"]:
            print(f"  - {item['title']}（{item['confidence']}）")
    for action in result["next_actions"]:
        print(f"  · {action}")
    return 0


def _analytics_store():
    from runtime.analytics_store import AnalyticsStore

    return AnalyticsStore()


def main() -> int:
    parser = argparse.ArgumentParser(description="CreatorOS Phase 22 最终能力（早报/生成/发布/晚报）")
    sub = parser.add_subparsers(dest="command", required=True)

    morning = sub.add_parser("morning", help="今天值得关注的话题 + 最符合账号定位的选题")
    morning.add_argument("--materials", metavar="PATH", help="本地材料 JSON（数组，不联网）")
    morning.add_argument("--channel", help="联网调研渠道（必须同时给 --research）")
    morning.add_argument("--research", action="store_true", help="显式允许联网调研")
    morning.add_argument("--query", help="调研检索词（默认取 Account Memory 的内容领域）")
    morning.add_argument("--limit", type=int, default=10, help="给几个话题（默认 10）")
    morning.add_argument("--top", type=int, default=3, help="挑几个最符合定位（默认 3）")
    morning.set_defaults(func=cmd_morning)

    generate = sub.add_parser("generate", help="生成各平台版本（只生成、不外发）")
    generate.add_argument("content_id")
    generate.add_argument("--platforms", nargs="+", default=list(DEFAULT_PLATFORMS),
                          help="平台（默认 x xiaohongshu douyin bilibili）")
    generate.set_defaults(func=cmd_generate)

    publish = sub.add_parser("publish", help="按平台发布（默认不开真实发送）")
    publish.add_argument("content_id")
    publish.add_argument("--platforms", nargs="+", default=list(DEFAULT_PLATFORMS))
    publish.add_argument("--send", action="store_true", help="X 真实发送（内容必须 APPROVED）")
    publish.set_defaults(func=cmd_publish)

    evening = sub.add_parser("evening", help="当日表现分析 + 记忆待办")
    evening.add_argument("--collect", action="store_true", help="先跑 X 指标采集")
    evening.add_argument("--limit", type=int, default=50, help="分析最近多少条快照")
    evening.add_argument("--no-write-memory", action="store_true", help="只出报告，不写观察")
    evening.set_defaults(func=cmd_evening)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
