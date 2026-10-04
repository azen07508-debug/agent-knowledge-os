#!/usr/bin/env python3
"""导入 AIHOT 精选快照到 CreatorOS ResearchStore；只读 AIHOT，不发布。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime.aihot_bridge import fetch_selected_snapshot, import_selected_snapshot
from runtime.research_store import ResearchStore


def main() -> int:
    parser = argparse.ArgumentParser(description="导入 AIHOT 精选到 CreatorOS ResearchStore")
    parser.add_argument("--base", default="http://localhost:3000")
    parser.add_argument("--query", default="AIHOT selected")
    parser.add_argument("--topic", default="aihot-selected")
    parser.add_argument("--db", default=None, help="ResearchStore 路径；不传则使用正式 data/research.sqlite3")
    args = parser.parse_args()
    payload = fetch_selected_snapshot(args.base)
    with ResearchStore(args.db) as store:
        result = import_selected_snapshot(payload, store, query=args.query, topic=args.topic)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
