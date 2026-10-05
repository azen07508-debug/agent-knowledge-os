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

## Reviewer follow-up

- 修正 `RuleRegistry.match()`：`include_unreviewed: bool = False`，默认排除 `UNREVIEWED`；显式 `True` 才允许内部匹配；`DEPRECATED` 始终排除。
- 修正 `RuleRegistry.add_many()`：先检查批内/已有 ID 冲突，再统一校验所有冲突引用，最后一次性提交；支持前向和双向 `conflicts_with`，未知引用失败时保持注册表原状。
- 新增测试覆盖默认匹配、显式包含、永久排除 deprecated、双向冲突和失败原子性。

### Follow-up verification

- Red：新增 reviewer 测试按预期失败 3 项。
- 专项及相关回归：`15 passed`。
- 全量：`527 passed, 1 warning`。
- Ruff：通过。
- `git diff --check`：通过。
