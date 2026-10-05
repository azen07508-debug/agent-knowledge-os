# Task 7 报告

## 状态

已完成 Task 7：API 支持显式 `school/policy/version` 策略选择，未知策略返回 422，未选择策略时返回明确 metadata，不静默 fallback。

## 改动

- `api/server.py`
  - `AnalyzeRequest` 增加可选 `school`、`policy`、`version`。
  - 将 selector 交给服务层解析；服务层的未知策略错误转换为 422。
- `runtime/mingli_service.py`
  - 复用 `StrategyRegistry`、`compare_results`、`ReportGenerator`。
  - 要求 selector 三项同时提供；显式 selector 按完整 key 校验并执行。
  - 响应增加策略结果、冲突报告、报告文本和 metadata。
  - 无 selector 时明确说明需要显式选择且不存在默认策略。
- `tests/test_strategy_api.py`
  - 覆盖显式选择、未知策略 422、无 selector metadata。

## 验证

- TDD red：新增专项测试初次运行 `3 failed`，确认 selector 尚未实现。
- 专项及相关回归：`30 passed`。
- API 回归：`7 passed`。
- 全量：`550 passed`。
- Ruff：`ruff check .` 通过。
- 已知警告：FastAPI TestClient 依赖链发出 Starlette/httpx deprecation warning，不影响测试结果。

## Concerns

- 当前 `MingLiService` 内部使用默认 `StrategyRegistry`；若后续需要注入自定义策略，应在后续任务中增加显式构造参数，当前不扩大 Task 7 范围。
- 工作区原有未跟踪 `uv.lock` 未纳入本次提交。

## Reviewer 修复（P1/P2）

- 区分 all `None`（合法无 selector metadata）、partial `None`（422）、三项空字符串/空白（422）和三项非空（查 registry）。
- service 直接调用与 API 使用同一边界校验。
- 新增空字符串、空白、partial selector 及 service 直调测试。
