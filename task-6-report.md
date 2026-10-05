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
