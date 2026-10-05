# Task 6 Report

## Scope

- Added local-only `data/benchmarks/mingli_cases.json`; no external benchmark scores or personal sensitive data.
- Extended evaluation results and summaries with calculation, rule, and Agent behavior metrics while preserving existing fields.
- Preserved case `source` and failure reasons; cases without a source are not authoritative.
- Added golden-case loading and validation for provider, pillars, ten gods, na yin, and relations.
- Added tests for the separated conflict, evidence-citation, and certainty-violation rates.

## Verification

- `.venv/bin/pytest -q tests/test_strategy_evaluation.py`: 2 passed.
- `.venv/bin/pytest -q tests/test_evaluation.py tests/test_strategy_evaluation.py`: 4 passed.
- `.venv/bin/pytest -q`: 541 passed, 1 existing dependency deprecation warning.
- `.venv/bin/ruff check evaluation tests/test_strategy_evaluation.py`: passed.

## Concerns

- `uv.lock` was already untracked before this task and was not modified or included.

## Reviewer follow-up

- Certainty violations now use `CriticAgent` output and are measured on a real dangerous-word case.
- Authority-scoped metrics exclude empty-source cases and expose `authoritative_count`; rule accuracy is `None` when no rule assertion applies.
- Invalid input/expected/source shapes and unknown expected fields are recorded as `mismatch` failures without aborting the batch.

Follow-up verification:

- `tests/test_strategy_evaluation.py`: 6 passed.
- `tests/test_evaluation.py tests/test_strategy_evaluation.py`: 8 passed.
- Full suite: 545 passed, 1 existing dependency deprecation warning.
- Ruff: passed.

## Scoped re-review follow-up

- Added explicit validation before `agent.analyze`: `expected.question` must be a non-empty string and every expected key must be a string.
- Malformed expected cases are retained as `mismatch` failures and do not prevent subsequent valid cases from running.

Verification:专项 8 passed；相关回归 10 passed；全量 547 passed；Ruff passed；全量仍有 1 条既有依赖弃用警告。
