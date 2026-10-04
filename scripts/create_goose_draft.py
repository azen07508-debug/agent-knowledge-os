#!/usr/bin/env python3
"""把 Goose 公开资料内容包写入 ContentStore，停在人审 REVIEW，不自动发布。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime.content_pack import content_object_from_pack, goose_public_research_pack
from runtime.content_store import ContentStore


def main() -> int:
    pack = goose_public_research_pack()
    content = content_object_from_pack(pack)
    with ContentStore() as store:
        result = store.save(content)
    print(json.dumps({"result": result, "content": content.to_dict()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
