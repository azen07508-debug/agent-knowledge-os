# Final Fix Wave

## Scope

- 无 `school/policy/version` 时保留命盘事实，但不输出无 provenance 的规则分析。
- `UNREVIEWED` 规则不得作为生产权威引用；Critic 拒绝，报告明确标记为仅内部测试、非权威引用。
- 补齐策略运行的 `approximate=True` 断言。
- 冲突 provenance 测试使用确实产生 `has_conflict=True` 的两个策略结果。

## Changes

- `runtime/mingli_service.py`：无 selector 时清空规则匹配、冲突和规则状态，保留 facts/chart 并返回 required metadata 与空策略分析结论。
- `agents/mingli.py`：Critic 对匹配到的 `UNREVIEWED` 规则增加拒绝问题。
- `agents/report.py`：规则和结论明确输出 `UNREVIEWED`、仅内部测试、非权威引用，同时保留危险措辞清洗。
- `tests/`：新增无 selector、UNREVIEWED、approximate 和真实冲突回归断言。

## Verification

- `uv run --no-project --with pytest --with sxtwl --with requests --with fastapi --with pydantic --with httpx2 pytest -q tests/test_mingli_reporting.py tests/test_strategy_registry.py tests/test_strategy_compare.py tests/test_evidence_provenance.py`
  - `25 passed`
- `uv run --no-project --with pytest --with sxtwl --with requests --with fastapi --with pydantic --with httpx2 --with python-dotenv --with rich pytest -q`
  - `557 passed`
- `uvx ruff check .`
  - `All checks passed`
- `python3 -m compileall -q`（目标源码与测试）
  - 通过
- `git diff --check`
  - 通过

## Environment Note

直接运行 `pytest` 不可用；项目完整 `uv` 环境因 Intel macOS 无 `lancedb==0.34.0` 可用 wheel 不能解析。使用 `uv --no-project` 安装测试所需最小依赖完成了专项和全量验证，未读取或传输凭据、私有文件或外部项目内容。

## Residual Important Fix

- 无 selector 时在 selector 校验后、Analyst 调用前直接返回，仅返回 chart 与 facts metadata；`analysis`、`critique`、`strategy`、`conflicts`、`report` 均为 `None`，因此不会调用 `ReportGenerator`。
- `AnalysisResponse.analysis` 与 `critique` 改为允许 `None`；`/api/chart` 仍直接返回 `response.chart`。
- 测试覆盖 API 与 service 直调，并更新旧的无 selector API 断言。
