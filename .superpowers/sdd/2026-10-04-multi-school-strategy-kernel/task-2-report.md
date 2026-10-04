# Task 2 实现报告：Dayun Strategy Registry

## 修改文件

- `engines/bazi/strategy_registry.py`：新增显式 `(school, policy, version)` 注册表，支持 `register()`、`get()`、`list()`、`run()`；内置显式注册 `classical_approx_v1`。
- `engines/bazi/time_engine.py`：导出 `StrategyRegistry`，不改变既有 `DayunPolicy` 行为。
- `tests/test_strategy_registry.py`：覆盖重复注册、缺失策略、provenance、同 school 多 policy，以及运行时必须提供完整 key。

## 设计决定

- 注册表以策略 `context` 的 `(school, policy, version)` 作为唯一键，重复 key 拒绝覆盖。
- `get()` 对缺失完整 key 抛出包含 key 的明确 `KeyError`。
- `run()` 强制显式提供完整 key，不做默认策略或模糊 fallback；结果直接保留策略自身 `StrategyContext` provenance。
- `list()` 返回 tuple 快照，避免暴露可变注册表容器。
- 保留 Task 1 的 frozen/只读结果契约，未修改策略结果模型。

## 命令结果

- 红灯：`/Users/admin/Desktop/workspace/projects/agent-knowledge-os/.venv/bin/pytest -q tests/test_strategy_registry.py`：收集阶段失败，因注册表尚不存在（预期）。
- 绿灯：`.../pytest -q tests/test_strategy_registry.py tests/test_strategy_contracts.py tests/test_time_engine.py`：15 passed。
- Ruff：`.../ruff check engines/bazi/strategy_registry.py engines/bazi/time_engine.py tests/test_strategy_registry.py`：All checks passed。
- 全量：`.../pytest -q`：515 passed，1 个既有 `StarletteDeprecationWarning`。
- `git diff --check`：通过。

## 限制 / concerns

- 注册表默认实例会显式预注册 `classical_approx_v1`；若调用方需要完全空表，可通过后续接口设计补充，但本任务要求该内置策略显式可用。
- 工作树中已有未跟踪 `uv.lock`，未修改、未纳入本次提交。
