"""外部 benchmark 适配层。

只做本机可复算的确定性比对：四柱、日主、十神、纳音、藏干十神、大运顺逆。
问答类指标必须由 LLM 作答器产生；本系统没有作答器，因此 ``qa_accuracy``
恒为 None，不做任何折算或估算。

数据集缓存在 ``data/benchmarks/external``，不随仓库提交；文件缺失时明确
报告不可用，不伪造结果。
"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Any

from engines.bazi import BaziCalculator, BirthInput, SxtwlBaziProvider
from engines.bazi.strategies import ClassicalApproxDayunPolicy, DayStemDayunPolicy
from engines.bazi.sxtwl_provider import ten_god
from evaluation.core import EvaluationResult, EvaluationSummary, summarize

EXTERNAL_DIR = Path("data/benchmarks/external")

DATASET_FILES = {
    "fate-bench": EXTERNAL_DIR / "fate_bench.jsonl",
    "mingli-bench": EXTERNAL_DIR / "mingli_bench_data.json",
}

# 数据集使用的繁体/异体写法；只做字形归一，不改写语义。
TEXT_VARIANTS = {"順行": "顺行", "沙中金": "砂中金"}

QA_REASON = "本系统没有 LLM 作答器，无法给出问答准确率；只报告可复算的确定性比对结果。"

# 巳的藏干在不同文本里写作「丙戊庚」或「丙庚戊」，本气一致，只是中气/余气顺序不同。
HIDDEN_ORDER_NOTE = (
    "数据集与本引擎对巳藏干的中气/余气采用不同书写顺序（丙戊庚 / 丙庚戊）；"
    "按集合比对判为一致，顺序差异单独计数，不计入失败。"
)

DAYUN_POLICIES = {
    "classical_approx_v1": ClassicalApproxDayunPolicy(),
    "day_stem_approx_v1": DayStemDayunPolicy(),
}


def normalize_benchmark_text(text: str) -> str:
    """把数据集里的已知字形变体归一到本项目写法。"""
    for variant, standard in TEXT_VARIANTS.items():
        text = text.replace(variant, standard)
    return text


def available_datasets(root: Path = EXTERNAL_DIR) -> tuple[tuple[str, Path], ...]:
    """返回本地已缓存的数据集；缺失的一律不报告。"""
    return tuple(
        (name, path) for name, path in DATASET_FILES.items() if (root / path.name).exists()
    )


def verify_fate_bench(path: Path, *, calculator=None) -> dict[str, Any]:
    """比对 fate-bench 的参考命盘；缺失参考记录的样本直接跳过并计数。"""
    records = _load_jsonl(path)
    calculator = calculator or BaziCalculator(SxtwlBaziProvider())
    results: list[EvaluationResult] = []
    skipped: dict[str, int] = {}
    direction = {name: [0, 0] for name in DAYUN_POLICIES}
    hidden_order_variants = 0

    for record in records:
        reference = _reference(record)
        birth = _birth(record)
        if reference is None or birth is None:
            reason = "missing_reference_chart" if reference is None else "incomplete_birth"
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        try:
            chart = calculator.calculate_chart(BirthInput(**birth))
        except (TypeError, ValueError):
            skipped["invalid_birth"] = skipped.get("invalid_birth", 0) + 1
            continue

        result, order_variant = _compare(record, reference, chart)
        results.append(result)
        hidden_order_variants += order_variant
        expected_direction = _direction(record)
        if expected_direction:
            for name, policy in DAYUN_POLICIES.items():
                try:
                    actual = policy.calculate(chart).direction
                except ValueError:
                    continue
                want = "顺行" if actual == "forward" else "逆行"
                direction[name][1] += 1
                direction[name][0] += want == expected_direction

    summary = summarize(results)
    return {
        "benchmark": "fate-bench",
        "path": str(path),
        "cases_total": len(records),
        "cases_evaluated": len(results),
        "cases_skipped": sum(skipped.values()),
        "skip_reasons": dict(sorted(skipped.items())),
        "scope": "确定性命盘比对（四柱/日主/十神/纳音/藏干十神；藏干按集合比对）",
        "qa_accuracy": None,
        "qa_accuracy_reason": QA_REASON,
        "summary": summary,
        "hidden_stem_order_variants": hidden_order_variants,
        "hidden_stem_order_note": HIDDEN_ORDER_NOTE,
        "dayun_direction": {
            name: {
                "agreed": agreed,
                "total": total,
                "rate": round(agreed / total, 4) if total else 0.0,
            }
            for name, (agreed, total) in direction.items()
        },
        "mismatch_samples": [
            {"case_id": result.case_id, "failure_reason": result.failure_reason}
            for result in summary.results
            if not result.passed
        ][:10],
    }


def verify_mingli_bench(path: Path, *, calculator=None) -> dict[str, Any]:
    """MingLi-Bench 只有问答题，没有参考命盘，因此只报告可复算覆盖率。"""
    questions = json.loads(path.read_text(encoding="utf-8")).get("questions") or []
    calculator = calculator or BaziCalculator(SxtwlBaziProvider())
    computable = sum(_chart(question, calculator) is not None for question in questions)
    return {
        "benchmark": "mingli-bench",
        "path": str(path),
        "cases_total": len(questions),
        "chart_computable": computable,
        "chart_computable_rate": round(computable / len(questions), 4) if questions else 0.0,
        "qa_accuracy": None,
        "qa_accuracy_reason": QA_REASON,
    }


def report_to_dict(report: dict[str, Any]) -> dict[str, Any]:
    """把报告转成可 JSON 序列化的结构，去掉逐条结果以控制体积。"""
    serialised = dict(report)
    summary = serialised.get("summary")
    if isinstance(summary, EvaluationSummary):
        serialised["summary"] = {
            field.name: getattr(summary, field.name)
            for field in fields(summary)
            if field.name != "results"
        }
    return serialised


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"benchmark 数据文件缺失：{path}")
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _reference(record: dict[str, Any]) -> dict[str, Any] | None:
    bazi = (record.get("charts") or {}).get("bazi") or {}
    return bazi if bazi.get("pillars") else None


def _birth(record: dict[str, Any]) -> dict[str, Any] | None:
    info = record.get("birth_info") or {}
    resolved = record.get("resolved_time") or {}
    hour = resolved.get("hour", info.get("hour_start", info.get("hour")))
    if not (info.get("year") and info.get("month") and info.get("day")) or hour is None:
        return None
    return {
        "year": int(info["year"]),
        "month": int(info["month"]),
        "day": int(info["day"]),
        "hour": int(hour),
        "minute": int(resolved.get("minute") or 0),
        "gender": info.get("gender"),
    }


def _direction(record: dict[str, Any]) -> str | None:
    bazi = (record.get("charts") or {}).get("bazi") or {}
    value = bazi.get("luck_cycles") or {}
    direction = value.get("direction")
    return normalize_benchmark_text(direction) if direction else None


def _chart(record: dict[str, Any], calculator) -> Any:
    birth = _birth(record)
    if birth is None:
        return None
    try:
        return calculator.calculate_chart(BirthInput(**birth))
    except (TypeError, ValueError):
        return None


def _expected(reference: dict[str, Any]) -> dict[str, Any]:
    return {
        "pillars": reference.get("pillars") or {},
        "day_master": reference.get("day_master"),
        "ten_gods": reference.get("ten_gods") or {},
        "nayin": reference.get("nayin") or {},
        "hidden_stem_gods": reference.get("hidden_stem_gods") or {},
    }


def _actual(chart) -> dict[str, Any]:
    names = ("year", "month", "day", "hour")
    return {
        "pillars": {
            name: f"{pillar.heavenly_stem}{pillar.earthly_branch}"
            for name, pillar in zip(names, chart.pillars)
        },
        "day_master": chart.day_master,
        "ten_gods": {name: pillar.ten_god for name, pillar in zip(names, chart.pillars)},
        "nayin": {name: pillar.na_yin for name, pillar in zip(names, chart.pillars)},
        "hidden_stem_gods": {
            name: [ten_god(chart.day_master, stem) for stem in pillar.hidden_stems]
            for name, pillar in zip(names, chart.pillars)
        },
    }


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        flattened: dict[str, Any] = {}
        for key, item in value.items():
            flattened.update(_flatten(item, f"{prefix}.{key}" if prefix else str(key)))
        return flattened
    return {prefix: value}


def _compare(record, reference, chart) -> tuple[EvaluationResult, bool]:
    expected_payload = _expected(reference)
    actual_payload = _actual(chart)
    order_variant = _hidden_order_variant(expected_payload, actual_payload)
    expected = _flatten(_sorted_hidden(expected_payload))
    actual = _flatten(_sorted_hidden(actual_payload))
    mismatches = [
        path
        for path, value in expected.items()
        if _normalise_value(value) != _normalise_value(actual.get(path))
    ]
    return (
        EvaluationResult(
            case_id=str(record.get("id", "")),
            passed=not mismatches,
            expected=dict(expected),
            actual=dict(actual),
            source="fate-bench",
            calculation_applicable=True,
            calculation_passed=not mismatches,
            failure_reason="、".join(mismatches),
        ),
        order_variant,
    )


def _sorted_hidden(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["hidden_stem_gods"] = {
        name: sorted(gods) for name, gods in payload["hidden_stem_gods"].items()
    }
    return payload


def _hidden_order_variant(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    """藏干集合一致但书写顺序不同，即巳的中气/余气顺序差异。"""
    expected_gods = expected.get("hidden_stem_gods") or {}
    actual_gods = actual.get("hidden_stem_gods") or {}
    for name, gods in expected_gods.items():
        ours = actual_gods.get(name, [])
        if sorted(gods) == sorted(ours) and list(gods) != list(ours):
            return True
    return False


def _normalise_value(value: Any) -> Any:
    if isinstance(value, list):
        return [normalize_benchmark_text(str(item)) for item in value]
    if isinstance(value, str):
        return normalize_benchmark_text(value)
    return value


__all__ = [
    "DATASET_FILES",
    "available_datasets",
    "normalize_benchmark_text",
    "report_to_dict",
    "verify_fate_bench",
    "verify_mingli_bench",
]
