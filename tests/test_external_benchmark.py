"""外部 benchmark 适配层测试。

fixture 由本引擎生成，只用于验证适配管道，不代表 fate-bench 原始数据内容。
"""

import json
from pathlib import Path

import pytest

from evaluation.external import (
    available_datasets,
    normalize_benchmark_text,
    report_to_dict,
    verify_fate_bench,
    verify_mingli_bench,
)

FIXTURE = Path(__file__).parent / "fixtures" / "fate_bench_sample.jsonl"


def test_normalize_benchmark_text_handles_documented_variants():
    assert normalize_benchmark_text("順行") == "顺行"
    assert normalize_benchmark_text("沙中金") == "砂中金"
    assert normalize_benchmark_text("正官") == "正官"


def test_fate_bench_verifies_reference_chart_and_reports_layers():
    report = verify_fate_bench(FIXTURE)

    assert report["benchmark"] == "fate-bench"
    assert report["cases_total"] == 4
    assert report["cases_evaluated"] == 3
    assert report["cases_skipped"] == 1
    assert report["qa_accuracy"] is None
    assert report["qa_accuracy_reason"]

    summary = report["summary"]
    assert summary.total == 3
    assert summary.passed == 2
    assert round(summary.calculation_accuracy, 4) == 0.6667
    assert summary.authoritative_count == 3
    assert summary.rule_accuracy is None


def test_fate_bench_counts_hidden_stem_order_variants_without_failing():
    report = verify_fate_bench(FIXTURE)

    assert report["hidden_stem_order_variants"] == 1
    assert report["hidden_stem_order_note"]
    passed = {result.case_id for result in report["summary"].results if result.passed}
    assert "fixture_order_variant" in passed


def test_fate_bench_failure_reason_names_mismatched_field():
    report = verify_fate_bench(FIXTURE)

    failed = [result for result in report["summary"].results if not result.passed]

    assert [result.case_id for result in failed] == ["fixture_mismatch"]
    assert "day" in failed[0].failure_reason
    assert "nayin.day" in failed[0].failure_reason


def test_fate_bench_reports_dayun_direction_per_school():
    report = verify_fate_bench(FIXTURE)

    direction = report["dayun_direction"]

    assert direction["classical_approx_v1"] == {"agreed": 2, "total": 2, "rate": 1.0}
    assert direction["day_stem_approx_v1"] == {"agreed": 0, "total": 2, "rate": 0.0}


def test_report_to_dict_is_json_serialisable():
    report = report_to_dict(verify_fate_bench(FIXTURE))

    assert "results" not in report["summary"]
    json.dumps(report)


def test_missing_dataset_is_reported_instead_of_guessed(tmp_path):
    assert available_datasets(tmp_path) == ()

    with pytest.raises(FileNotFoundError):
        verify_fate_bench(tmp_path / "missing.jsonl")


def test_mingli_bench_reports_coverage_without_qa_accuracy(tmp_path):
    path = tmp_path / "mingli.json"
    path.write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "id": "q1",
                        "birth_info": {
                            "year": 1990,
                            "month": 2,
                            "day": 1,
                            "hour": 12,
                            "gender": "男",
                            "calendar_type": "solar",
                        },
                        "question": "此命如何？",
                        "options": [{"letter": "A", "text": "x"}],
                        "answer": "A",
                        "has_answer": True,
                    },
                    {
                        "id": "q2",
                        "birth_info": {"year": 1990, "month": 2, "calendar_type": "solar"},
                        "question": "此命如何？",
                        "options": [{"letter": "A", "text": "x"}],
                        "answer": "A",
                        "has_answer": True,
                    },
                ]
            },
            ensure_ascii=False,
        )
    )

    report = verify_mingli_bench(path)

    assert report["benchmark"] == "mingli-bench"
    assert report["cases_total"] == 2
    assert report["chart_computable"] == 1
    assert report["qa_accuracy"] is None
    assert report["qa_accuracy_reason"]
