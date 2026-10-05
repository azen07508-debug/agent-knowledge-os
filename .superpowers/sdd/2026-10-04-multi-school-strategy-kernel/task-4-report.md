# Task 4 Report

## Status

DONE

## Changes

- `knowledge/rules.py`
  - Added `UNREVIEWED`、`REVIEWED`、`ACTIVE`、`DEPRECATED` rule states.
  - `Rule.status` defaults to `UNREVIEWED` and validates values.
  - Deprecated rules are excluded from matching.
  - Added the `include_unreviewed` matching option while retaining legacy direct matching behavior.
- `knowledge/evidence.py`
  - Added optional `StrategyContext` provenance and matched `rule_statuses`.
  - Added both fields to `Evidence.to_dict()`.
  - Production evidence excludes unreviewed rules by default; internal evidence can opt in with `include_unreviewed=True`.
  - Existing positional/default construction and `build_evidence(chart, registry, topic)` calls remain valid.
- `knowledge/default_rules.py`
  - Marked built-in, not-yet-verified rules explicitly as `UNREVIEWED`.
- `tests/test_evidence_provenance.py`
  - Added coverage for internal unreviewed evidence, deprecated filtering, serialized strategy provenance, and strategy isolation.

## Verification

- Red phase: `.venv/bin/pytest` was unavailable inside the worktree; the specified shared environment was used instead. The new test file failed 4 tests because `Rule.status` was absent.
-专项/相关回归：`11 passed` (`tests/test_evidence_provenance.py`, `tests/test_rules.py`, `tests/test_evidence.py`).
- Ruff: passed for all Task 4 files and related tests.
- Full suite: `523 passed, 1 warning`.
- `git diff --check`: passed.

## Concerns

- Full suite emits an existing Starlette/httpx deprecation warning from the virtual environment; it is unrelated to Task 4.
- `uv.lock` was pre-existing untracked workspace state and was not included in the commit.
