#!/usr/bin/env python3
"""从 AIHOT 精选生成 CreatorOS 的第一条 REVIEW 草稿，不自动发布。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.content import ContentAgent
from runtime.aihot_bridge import fetch_selected_snapshot, import_selected_snapshot
from runtime.content_store import ContentStore
from runtime.memory_api import MemoryAPI
from runtime.research_store import ResearchStore
from runtime.topic_engine import TopicEngine
from runtime.topics import build_candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="从 AIHOT 精选生成 CreatorOS REVIEW 草稿")
    parser.add_argument("--base", default="http://localhost:3000")
    parser.add_argument("--research-db", default=None)
    parser.add_argument("--content-db", default=None)
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()

    payload = fetch_selected_snapshot(args.base)
    with ResearchStore(args.research_db) as research:
        imported = import_selected_snapshot(payload, research, topic="aihot-selected")
        materials = research.search(topic="aihot-selected", limit=500)
        candidates = build_candidates(materials)
        ranked = TopicEngine().recommend(candidates, top_k=args.top_k)
        recommendations = ranked["recommendations"]
        if not recommendations:
            raise RuntimeError("AIHOT 精选没有产生可用选题")
        selected = dict(recommendations[0])
        selected["title_candidates"] = _titles(selected)
        selected["evidence_status"] = "PUBLIC_SOURCES"
        selected["content_source"] = "AIHOT 精选公开资料，未完成本地实测"

    with ContentStore(args.content_db) as store:
        result = ContentAgent(store=store, memory=MemoryAPI()).run(
            "从 AIHOT 精选生成今日 X REVIEW 草稿",
            {"recommendation": selected},
        )
    print(json.dumps({"imported": imported, "recommendation": selected, "draft": result}, ensure_ascii=False, indent=2))
    return 0


def _titles(recommendation: dict[str, object]) -> list[str]:
    topic = str(recommendation.get("topic") or "AIHOT 精选")
    return [
        "为什么这条 AI 动态值得开发者今天认真看？",
        f"{topic}：真正值得关注的不是标题，而是它改变了什么",
        f"我从 {topic} 里看到的一个反常识信号",
    ]


if __name__ == "__main__":
    raise SystemExit(main())
