# Task 3 实现报告

## 状态

DONE

## 实现

- 新增 `engines/bazi/strategy_compare.py`。
- 新增 `ConflictReport`、`StrategyConflict`、`ConflictSide` 和 `compare_results`。
- 通过结构化字段指纹比较结论，不使用自然语言相似度。
- 冲突保留双方 `(school, policy, version)`、完整指纹和差异字段；输入结果按原序列全部保留，不投票、不丢弃。
- 缺少 `context` 的结果会拒绝比较。
- `ConflictReport.to_dict()` 可 JSON 序列化，并保留策略 assumptions 与 evidence。
- 新增 `tests/test_strategy_compare.py` 覆盖相同结论、冲突保留、context 校验和序列化。

## TDD 验证

- RED：首次运行专项测试因 `engines.bazi.strategy_compare` 不存在而收集失败，确认测试先于实现。
- 专项测试：`4 passed`。
- 相关回归：`15 passed`。
- 全量测试：`519 passed`，存在 1 个既有 Starlette/httpx 弃用警告。
- Ruff：专项文件检查通过。

## Concerns

- 全量测试的 Starlette/httpx 弃用警告与本 Task 无关，未修改依赖。
