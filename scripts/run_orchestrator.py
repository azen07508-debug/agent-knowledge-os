#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from runtime.orchestrator import STAGES, Orchestrator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--allow-model", action="store_true")
    parser.add_argument("--allow-publish", action="store_true")
    parser.add_argument("--allow-analytics", action="store_true")
    args = parser.parse_args()
    result = Orchestrator().run(args.stage, allow_network=args.allow_network, allow_model=args.allow_model, allow_publish=args.allow_publish, allow_analytics=args.allow_analytics)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
