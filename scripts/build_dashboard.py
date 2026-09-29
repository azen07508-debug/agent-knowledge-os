#!/usr/bin/env python3
"""生成 CreatorOS 本地仪表盘：各 store + 长期记忆 → 单文件 HTML（只读、不联网）。

    python scripts/build_dashboard.py                # 写 data/dashboard.html
    python scripts/build_dashboard.py --out /tmp/x.html --limit 50
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime.dashboard import DEFAULT_OUT, PAGES, collect, write


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 CreatorOS 本地仪表盘（单文件 HTML）")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出 HTML 路径")
    parser.add_argument("--limit", type=int, default=30, help="各列表最多取多少行")
    args = parser.parse_args()

    data = collect(limit=args.limit)
    path = write(args.out, data)
    totals = data["totals"]
    print(f"已生成：{path}")
    print(
        f"页面 {len(PAGES)} 个 · 研究 {totals['research']} · 内容 {totals['content']} · "
        f"发布 {totals['jobs']} · 快照 {totals['snapshots']} · 洞察 {totals['insights']}"
    )
    print("本地只读视图：不联网、不加载外部资源、不修改任何数据。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
