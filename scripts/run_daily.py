#!/usr/bin/env python3
"""CreatorOS 每日流程入口（Phase 21）：Research→…→Memory，跑一轮并留下记录。

    python scripts/run_daily.py                          # 默认全本地：不联网、不发布、不采集
    python scripts/run_daily.py --materials m.json       # 用本地材料做调研
    python scripts/run_daily.py --research github        # 显式允许联网调研（走 agent-reach）
    python scripts/run_daily.py --publish-x --send       # 显式允许真实发布已过审的 X 内容
    python scripts/run_daily.py --collect                # 显式允许跑 X 指标采集
    python scripts/run_daily.py --topic "选题名"          # 今天指定做这个题（人工拍板绕开 verdict 闸门）

09:00 定时由 cron/launchd 调本脚本即可；每次运行都会追加 data/daily_runs.jsonl。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.daily import DailyPipeline


def _load_materials(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"材料文件必须是 JSON 数组：{path}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="CreatorOS 每日流程（默认不联网、不外发）")
    parser.add_argument("--research", metavar="CHANNEL",
                        help="允许联网调研并指定渠道（缺省只用本地 materials）")
    parser.add_argument("--materials", metavar="PATH", help="本地材料 JSON 文件（数组）")
    parser.add_argument("--publish-x", action="store_true", help="启用 X 发布位（需再加 --send 才真发）")
    parser.add_argument("--send", action="store_true", help="真实发送（必须与 --publish-x 同用）")
    parser.add_argument("--collect", action="store_true", help="跑 X 指标采集（需 X 后端）")
    parser.add_argument("--topic", help="今天指定做的选题（无 verdict=推荐 时人工拍板用）")
    parser.add_argument("--task", default=None, help="本轮任务描述")
    args = parser.parse_args()

    if args.send and not args.publish_x:
        parser.error("--send 必须搭配 --publish-x")

    context: dict = {}
    if args.materials:
        context["materials"] = _load_materials(args.materials)
    if args.research:
        context["channel"] = args.research
    if args.topic:
        context["topic"] = args.topic

    pipeline = DailyPipeline(research=bool(args.research), publish_x=args.publish_x,
                             send=args.send, collect=args.collect)
    result = pipeline.run(args.task, context)

    print(f"{result['date']} 每日流程：{'成功' if result['ok'] else '有问题（见下）'}")
    for note in result["notes"]:
        print(f"  · {note}")
    for step in result["loop"]["steps"]:
        print(f"  {step['name']:<9} {step['status']:<8} {step['summary']}")
    print("今天必须人做的事：")
    for item in result["todo"] or ["（无）"]:
        print(f"  - {item}")
    print(f"运行记录：{result['log_path']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
