"""运行外部 benchmark 的确定性比对并打印 JSON 报告。

数据集缓存在 ``data/benchmarks/external``，不随仓库提交；缺失时只报告
不可用，不伪造分数。问答类指标恒为 None。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.external import (
    DATASET_FILES,
    available_datasets,
    report_to_dict,
    verify_fate_bench,
    verify_mingli_bench,
)


def main() -> int:
    found = dict(available_datasets())
    reports = []
    if "fate-bench" in found:
        reports.append(report_to_dict(verify_fate_bench(found["fate-bench"])))
    if "mingli-bench" in found:
        reports.append(verify_mingli_bench(found["mingli-bench"]))

    print(
        json.dumps(
            {
                "available": sorted(found),
                "missing": sorted(set(DATASET_FILES) - set(found)),
                "reports": reports,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if reports else 1


if __name__ == "__main__":
    sys.exit(main())
