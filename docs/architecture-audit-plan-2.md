# CreatorOS 二次修复与 Review 面板计划

> 目标：把当前“能生成、能发布、能复盘”的本地系统，推进到审核不变量可靠、发布恢复可靠、Review 可操作。
> 原则：改动小、状态可追踪、人工审核不绕过、外部副作用可对账。

## 阶段 A：内容与发布不变量

### A1. 保护 APPROVED 内容

当前风险：普通 `ContentStore.fill()` 可以修改已批准正文、平台帖子或证据字段，破坏人工审核版本。

修复：

- `APPROVED`、`SCHEDULED`、`PUBLISHED` 禁止普通 `fill()`；
- 已批准内容修改必须先回到 `DRAFT` 或创建新内容版本；
- 证据状态只能通过显式验证方法升级；
- 增加状态回归测试。

验收：尝试修改已批准内容必须失败；REVIEW 内容仍可正常编辑和审批。

### A2. 阻止部分发布重复发送

当前风险：Thread 部分成功后 job 进入 `NEEDS_REVIEW`，但内容仍是 `APPROVED`；再次调用发布可能从第一条重新发送。

修复：

- 发布前检查同一 `content_id/platform` 是否有 `NEEDS_REVIEW`、`RECONCILING` 或 `TIMEOUT_UNVERIFIED` job；
- 有未解决 job 时拒绝整条发布；
- 只允许人工对账或后续明确的后缀补发；
- 保留已确认 post ID。

验收：部分成功后再次调用 `publish()` 不调用后端；返回明确的待对账信息。

### A3. 结构化帖子边界

保留 `platform_posts` 作为 X 帖子的唯一边界来源；审核、发布和数据展示都不得把普通换行当作帖子分隔符。

## 阶段 B：可操作 Review 面板

### B1. 本地 Review API

使用 Python 标准库启动本地服务，不联网、不读取凭据：

- `GET /api/review`：列出 REVIEW 内容；
- `GET /api/review/<id>`：返回研究、标题候选、证据、平台帖子、审核记录；
- `POST /api/review/<id>/approve`：调用 `human_review.approve()`；
- `POST /api/review/<id>/changes`：调用 `human_review.request_changes()`；
- 非 REVIEW 状态拒绝操作；
- 监听地址默认 `127.0.0.1`。

### B2. Review 页面

页面必须显示：

- 账号定位相关性；
- 标题候选；
- 证据状态；
- 原始来源和摘录；
- Claims；
- X 帖子边界；
- 公开资料/实测标记；
- 审核记录；
- 批准和要求修改按钮。

不做：

- 页面直接发帖；
- 页面调用模型；
- 自动批准；
- 把公开资料标记为实测。

### B3. 验收与提交

每阶段执行：

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m mypy .
```

Review 服务额外执行本地 HTTP smoke；通过后分阶段 commit。

## 暂不做

- 不引入 Web 框架；
- 不引入数据库迁移工具；
- 不接入更多发布平台；
- 不自动批准或自动真实发布；
- 不在限流状态下反复调用 Mimo。
