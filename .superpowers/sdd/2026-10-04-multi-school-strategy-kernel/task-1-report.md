# Task 1 完成报告

## 修改文件

- `engines/bazi/strategies.py`
  - 新增不可变 `StrategyContext`、`StrategyResult`、`DayunResult`。
  - 新增 `DayunStrategy` Protocol。
  - 将 `ClassicalApproxDayunPolicy` 适配为结构化、带来源和近似标记的结果；策略名称固定为 `classical_approx_v1`。
  - 缺少 `gender` 时显式抛出可解释的 `ValueError`。
- `engines/bazi/time_engine.py`
  - 保留原有流年能力和 `DayunPolicy` 的“不猜测”边界。
  - 重导出新大运策略契约及经典近似策略。
- `tests/test_strategy_contracts.py`
  - 覆盖上下文必填字段、结果来源/假设/近似信息、结构化大运结果、策略名称和缺少性别拒绝。

## 设计决定

- 所有策略结果使用 `frozen=True` dataclass，避免计算完成后篡改来源和置信信息。
- `StrategyContext` 固定包含 `school`、`policy`、`version`、`assumptions`，前三者拒绝空白值。
- `ClassicalApproxDayunPolicy` 明确声明 `classical_approx_v1`，结果将证据、冲突和 `approximate=True` 一并返回。
- 未引入新的依赖；`uv.lock` 是工具副产物，未纳入提交。

## TDD 与验证

1. 初始已有策略契约测试：`4 passed`。
2. 新增策略名称断言后先运行：`1 failed, 3 passed`，失败原因为缺少 `name` 属性。
3. 实现最小修复后运行：
   - `/Users/admin/Desktop/workspace/projects/agent-knowledge-os/.venv/bin/pytest -q tests/test_strategy_contracts.py tests/test_time_engine.py`
   - 结果：`8 passed`
4. Lint：
   - `/Users/admin/Desktop/workspace/projects/agent-knowledge-os/.venv/bin/ruff check engines/bazi tests/test_strategy_contracts.py tests/test_time_engine.py`
   - 结果：`All checks passed!`
5. 全量测试：
   - `/Users/admin/Desktop/workspace/projects/agent-knowledge-os/.venv/bin/pytest -q`
   - 结果：`508 passed, 1 warning`

## 基线失败处理

本次检查中既有 `tests/test_time_engine.py` 基线未失败，运行结果为 `4 passed`；因此没有修改既有基线断言或通过忽略测试掩盖问题。全量测试也全部通过。唯一警告来自环境中的 Starlette/httpx 弃用提示，与 Task 1 无关。

## 限制

- 经典策略仍是显式近似：起运年龄固定为现有近似值 `3.0`，不计算精确起运日期/时刻。
- `periods` 继续使用兼容现有调用方的只读 tuple 包裹 dict；本 Task 未扩展更细粒度的大运领域类型。
- `uv.lock` 保留在工作树中但未提交。

## Reviewer 修复（2026-10-04）

- 新增 frozen `DayunPeriod` dataclass，并将 `DayunResult.periods` 从可变字典改为 `tuple[DayunPeriod, ...]`。
- 更新契约测试，验证所有 period 使用 `DayunPeriod`，并验证 period 字段原地赋值抛出 `FrozenInstanceError`。
- 这是最小兼容范围内的契约收紧：保留 `periods` 的 tuple 序列和字段名，不扩展到 Task 2；调用方若依赖 `period["field"]` 字典索引需迁移到属性访问。
- TDD：新增测试在实现前因 `DayunPeriod` 不存在而收集失败；实现后通过。
