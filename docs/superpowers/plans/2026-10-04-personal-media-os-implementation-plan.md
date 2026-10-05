# Personal Media OS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Every implementation task MUST follow test-driven-development: write a failing test, verify RED, implement the minimum code, verify GREEN, then refactor while keeping tests green. Steps use checkbox syntax.

**Goal:** 将现有 CreatorOS 本地内容系统逐步升级为一个可一键启动、可审核、可对账、可复盘的 Personal Media OS。

**Architecture:** 保留 SQLite + Obsidian + XAdapter 的本地优先模块化单体架构。AIHOT、Agent-Reach 和未来 Crypto 数据作为 Source Adapter 接入统一 ResearchStore；Orchestrator 只编排阶段，不直接绕过 Human Gate 或发布适配器。

**Tech Stack:** Python 3.12+、SQLite、Obsidian Markdown、标准库 `http.server`、pytest、Ruff、mypy、现有 XAdapter/PublishJob/MemoryAPI。

**Spec:** `docs/superpowers/specs/2026-10-04-personal-media-os-architecture-design.md`

## Global Constraints

- 一键启动默认不联网、不调用模型、不读取浏览器凭据、不自动发帖。
- Review API 只监听 `127.0.0.1`。
- `APPROVED`、`SCHEDULED`、`PUBLISHED` 内容禁止普通编辑。
- 公开资料、本人实测、混合证据必须明确区分。
- 部分发布不得标记为完整 `SUCCEEDED`，必须进入对账或人工复核。
- X 帖子边界使用结构化 `platform_posts`，不能用普通换行推断帖子边界。
- 不引入 Redis、Kafka、Celery、Temporal、FastAPI 或 Flask。
- 不修改用户已有 `.gitignore`、`MINGLI_PLAN.md`、`engines/bazi/`、`pyproject.toml`、`requirements.txt`、`knowledge/` 改动。
- 每个任务按 TDD：RED → GREEN → REFACTOR → 全量测试。

## Review Focus

- 已批准内容被后台修改时，必须拒绝并保留原版本；由 Task 1 测试固定。
- 发布部分成功后再次执行，必须阻止整条重发；由 Task 2 测试固定。
- 一条帖子内部含多段换行时，审核和发布必须保持一条帖子边界；由 Task 3 测试固定。
- 一键启动时端口、PID、重复启动和未知进程必须安全处理；由 Task 4 测试固定。
- Review API 的非法状态、空驳回理由、CORS 和 SQLite 线程访问必须返回可解释结果；由 Task 5 测试固定。

---

### Task 1: 固化内容版本与审核不变量

**Files:**
- Modify: `runtime/content_object.py`
- Modify: `runtime/content_store.py`
- Modify: `runtime/human_review.py`
- Test: `tests/test_content_object.py`
- Test: `tests/test_content_store.py`
- Test: `tests/test_human_review.py`

**Interfaces:**
- Consumes: 现有 `ContentObject.fill()`, `ContentStore.fill()`, `human_review.approve()`。
- Produces: `ContentStore.fill()` 在 `APPROVED/SCHEDULED/PUBLISHED` 状态抛出明确 `ValueError`；证据状态只能通过 `mark_evidence_verified(status, reviewer, note)` 改变。

- [x] **Step 1: 写失败测试**
  - 已批准对象调用 `store.fill(id, {"core_content": ...})` 必须失败；
  - REVIEW 对象仍允许编辑；
  - 普通 `fill({"evidence_status": "SELF_TESTED"})` 必须失败；
  - `mark_evidence_verified()` 必须要求 reviewer，并追加 `EVIDENCE_VERIFIED`。
- [x] **Step 2: 运行指定测试确认 RED**
  - Run: `.venv/bin/python -m pytest -q tests/test_content_object.py tests/test_content_store.py tests/test_human_review.py`
  - Expected: 新增保护测试失败，失败原因是当前没有状态保护。
- [x] **Step 3: 最小实现**
  - 在 `ContentStore.fill()` 按状态拒绝；
  - 从 `ContentObject.fill()` 可更新字段移除 `evidence_status`；
  - 保留专用证据确认方法。
- [x] **Step 4: 验证 GREEN 与全量回归**
  - Run: 指定测试；
  - Run: `.venv/bin/python -m pytest -q`；
  - Expected: 全部通过。
- [x] **Step 5: 重构并提交**
  - 仅整理错误信息和重复校验；
  - Commit: `fix: protect approved content and evidence state`。

### Task 2: 发布任务恢复与部分成功阻断

**Files:**
- Modify: `agents/x_workflow.py`
- Modify: `runtime/publish_queue.py`
- Modify: `runtime/analytics_collector.py`（如状态查询需要）
- Test: `tests/test_x_workflow.py`
- Test: `tests/test_publish_queue.py`
- Test: `tests/test_publish_worker.py`

**Interfaces:**
- Consumes: `PublishJobStore.list_jobs()`, `record_publish()`, `XWorkflow.publish()`。
- Produces: `XWorkflow.publish()` 在存在 `TIMEOUT_UNVERIFIED/RECONCILING/NEEDS_REVIEW` job 时返回 `blocked_by_job`，不调用 X backend；部分成功 job 保持 `NEEDS_REVIEW`。

- [x] **Step 1: 写失败测试**
  - 构造部分成功 job 后再次调用 `publish()`，断言 backend 调用次数不增加；
  - 断言返回 `blocked_by_job`；
  - 完整人工对账仍可进入 `SUCCEEDED`；
  - `published_post_id` 只能来自有效 backend ID。
- [x] **Step 2: 验证 RED**
  - Run: `.venv/bin/python -m pytest -q tests/test_x_workflow.py tests/test_publish_queue.py tests/test_publish_worker.py`
  - Expected: 当前会再次调用 backend 或状态不符合预期。
- [x] **Step 3: 最小实现**
  - 发布前查询未解决 job；
  - 部分成功使用 `NEEDS_REVIEW`；
  - 禁止自动重发整条 Thread；
  - 不改变已确认 attempt。
- [x] **Step 4: 验证 GREEN 与全量回归**
  - Run: 指定测试；
  - Run: `.venv/bin/python -m pytest -q`。
- [x] **Step 5: 重构并提交**
  - 抽取状态查询 helper；
  - Commit: `fix: block duplicate recovery publishes`。

### Task 3: Canonical Content 与平台帖子边界

**Files:**
- Modify: `runtime/content_object.py`
- Modify: `runtime/content_store.py`
- Modify: `runtime/human_review.py`
- Modify: `agents/x_workflow.py`
- Modify: `runtime/content_pack.py`
- Test: `tests/test_content_pack.py`
- Test: `tests/test_human_review.py`
- Test: `tests/test_x_workflow.py`

**Interfaces:**
- Consumes: `platform_posts: dict[str, list[str]]`。
- Produces: 审核包和发布流程均优先读取 `platform_posts["X"]`；`core_content` 仅作为旧数据兼容字段。

- [x] **Step 1: 写失败测试**
  - 一条帖子含多个真实换行时，审核包仍返回一个 posts 元素；
  - 发布调用 backend 的 posts 与原结构完全一致；
  - 旧对象没有 `platform_posts` 时保留兼容 fallback。
- [x] **Step 2: 验证 RED**
  - Run: `.venv/bin/python -m pytest -q tests/test_content_pack.py tests/test_human_review.py tests/test_x_workflow.py`
- [x] **Step 3: 最小实现**
  - 内容包写入结构化列表；
  - 审核和发布读取结构化列表；
  - SQLite schema 增量补列。
- [x] **Step 4: 验证 GREEN 与全量回归**
  - Run: 指定测试；
  - Run: `.venv/bin/python -m pytest -q`。
- [x] **Step 5: 重构并提交**
  - 清理旧字段转换重复逻辑；
  - Commit: `fix: preserve canonical platform post boundaries`。

### Task 4: 一键启动与停止工作台

**Files:**
- Create: `scripts/start.sh`
- Create: `scripts/stop.sh`
- Modify: `.gitignore`（仅在现有规则不足时，用户已有修改需保留）
- Test: `tests/test_startup_scripts.py`

**Interfaces:**
- Produces: `data/review-server.pid`, `data/review-server.log`；启动默认 `127.0.0.1:8765`，Dashboard 输出到 `data/dashboard.html`。

- [x] **Step 1: 写失败测试**
  - 脚本能定位项目根；
  - 缺少 `.venv/bin/python` 时明确退出；
  - 已有本项目 PID 时不启动第二个服务；
  - 停止脚本只停止 PID 文件对应进程；
  - 未知 PID 不执行宽范围 kill。
- [x] **Step 2: 验证 RED**
  - Run: `.venv/bin/python -m pytest -q tests/test_startup_scripts.py`
- [x] **Step 3: 最小实现**
  - 使用 shell + Python helper；
  - 不使用 `pkill`、递归删除或未知进程终止；
  - 启动前生成 Dashboard，服务绑定 loopback。
- [x] **Step 4: 验证 GREEN 与本地 smoke**
  - Run: 测试文件；
  - Run: `./scripts/start.sh`；
  - Run: `curl http://127.0.0.1:8765/api/review`；
  - Run: `./scripts/stop.sh`。
- [x] **Step 5: 重构并提交**
  - Commit: `feat: add one-click creatoros workspace startup`。

### Task 5: Review API 与 Dashboard 可操作审核

**Files:**
- Modify: `runtime/review_server.py`
- Modify: `runtime/dashboard.py`
- Modify: `runtime/human_review.py`
- Test: `tests/test_review_server.py`
- Test: `tests/test_dashboard.py`
- Test: `tests/test_human_review.py`

**Interfaces:**
- `GET /api/review -> {ok: true, items: [...]}`
- `GET /api/review/<id> -> human_review.build_packet()` 数据；
- `POST /api/review/<id>/approve -> human_review.approve()`；
- `POST /api/review/<id>/changes -> human_review.request_changes()`；
- `OPTIONS` 返回本地 Dashboard 所需 CORS 头。

- [x] **Step 1: 写失败测试**
  - REVIEW 内容能被列出；
  - 详情包含标题候选、证据状态、来源、Claims、Evidence、`platform_posts`；
  - APPROVE 将状态改为 APPROVED；
  - 空修改理由返回 400；
  - 非 REVIEW 状态不能批准；
  - OPTIONS 返回 CORS 头。
- [x] **Step 2: 验证 RED**
  - Run: `.venv/bin/python -m pytest -q tests/test_review_server.py tests/test_dashboard.py tests/test_human_review.py`
- [x] **Step 3: 最小实现**
  - Review API 只绑定 loopback；
  - Dashboard Review 抽屉调用本地 API；
  - 不在页面直接写 SQLite。
- [x] **Step 4: 验证 GREEN 与 HTTP smoke**
  - Run: 指定测试；
  - Run: `python scripts/review_server.py --port 8765`；
  - Run: `curl http://127.0.0.1:8765/api/review`；
  - 验证 POST approve/changes 使用临时数据库。
- [x] **Step 5: 重构并提交**
  - Commit: `feat: make review dashboard actionable`。

### Task 6: Source Adapter 与增量 AIHOT 导入

**Files:**
- Modify: `runtime/aihot_bridge.py`
- Create: `runtime/source_item.py`
- Modify: `scripts/import_aihot_selected.py`
- Test: `tests/test_aihot_bridge.py`
- Test: `tests/test_source_item.py`

**Interfaces:**
- `SourceItem` 统一字段：`source/title/url/published_at/content/author/source_type/raw_metadata`；
- AIHOT 导入保留 `cursor/asOf`；
- 重复 URL 幂等，增量导入不重复生成材料。

- [x] **Step 1: 写失败测试**
  - AIHOT item 转成统一 SourceItem；
  - 旧快照重复导入不增加记录；
  - 新 cursor 只导入新增记录；
  - 缺 URL 明确跳过。
- [x] **Step 2: 验证 RED**
  - Run: `.venv/bin/python -m pytest -q tests/test_aihot_bridge.py tests/test_source_item.py`
- [x] **Step 3: 最小实现**
  - 增加统一转换和本地 cursor 状态；
  - 不改 AIHOT 数据库。
- [x] **Step 4: 验证 GREEN 与全量回归**
  - Run: 指定测试；
  - Run: `.venv/bin/python -m pytest -q`。
- [x] **Step 5: 重构并提交**
  - Commit: `feat: normalize source adapters and incremental imports`。

### Task 7: Orchestrator 状态机与一键今日任务

**Files:**
- Create: `runtime/orchestrator.py`
- Create: `scripts/run_orchestrator.py`
- Modify: `runtime/dashboard.py`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- `Orchestrator.run(stage, *, allow_network=False, allow_model=False, allow_publish=False, allow_analytics=False) -> dict`；
- 运行日志：`data/orchestrator_runs.jsonl`；
- 阶段：`IMPORT_AI_HOT`, `RESEARCH`, `BUILD_TOPICS`, `BUILD_DRAFTS`, `RUN_CHECKS`, `WAIT_HUMAN_REVIEW`, `PUBLISH_APPROVED`, `COLLECT_ANALYTICS`, `WRITE_INSIGHT_CANDIDATE`。

- [x] **Step 1: 写失败测试**
  - 默认运行不联网、不调用模型、不发布；
  - 阶段失败写 `failed` 运行记录；
  - 重复运行不会重复付费或重复导入；
  - publish 没有显式开关时为 skipped；
  - 每次运行含 external_side_effects 字段。
- [x] **Step 2: 验证 RED**
  - Run: `.venv/bin/python -m pytest -q tests/test_orchestrator.py`
- [x] **Step 3: 最小实现**
  - 顺序调用现有 bridge/store/ContentAgent；
  - 不引入后台队列。
- [x] **Step 4: 验证 GREEN 与全量回归**
  - Run: 指定测试；
  - Run: `.venv/bin/python -m pytest -q`。
- [x] **Step 5: 重构并提交**
  - Commit: `feat: add explicit orchestrator stages`。

### Task 8: Creator Intelligence 与风格观察

**Files:**
- Create: `runtime/creator_intelligence.py`
- Modify: `runtime/research_store.py`
- Modify: `runtime/creator_memory.py`
- Test: `tests/test_creator_intelligence.py`

**Interfaces:**
- `CreatorProfile` 保存 author、选题、标题结构、Hook、段落长度、情绪强度、CTA、样本数；
- `extract_creator_profile(items) -> CreatorProfile`；
- 未达样本门槛的结果状态只能是 `HYPOTHESIS/OBSERVED`。

- [x] **Step 1: 写失败测试**
  - 从公开帖子抽取结构字段；
  - 不复制原文，只保存结构特征；
  - 样本不足不生成已确认策略；
  - 真实互动数据缺失时写 UNKNOWN。
- [x] **Step 2: 验证 RED**
  - Run: `.venv/bin/python -m pytest -q tests/test_creator_intelligence.py`
- [x] **Step 3: 最小实现**
  - 先做规则式结构提取；
  - 通过 MemoryAPI 保存观察，不改账号策略。
- [x] **Step 4: 验证 GREEN 与全量回归**
  - Run: 指定测试；
  - Run: `.venv/bin/python -m pytest -q`。
- [x] **Step 5: 重构并提交**
  - Commit: `feat: add creator intelligence observations`。

### Task 9: Performance Memory 与定期工具帖流程

**Files:**
- Modify: `runtime/analytics_store.py`
- Modify: `runtime/analytics_collector.py`
- Create: `runtime/performance_insights.py`
- Modify: `runtime/dashboard.py`
- Test: `tests/test_performance_insights.py`

- [x] **Step 1: 写失败测试**
  - 按 content type、标题结构和 creator reference 聚合；
  - 样本不足时只产生 pending insight；
  - 足够样本仍不自动修改 Strategy；
  - 工具帖必须包含 pain point、official URL、audience、caveats。
- [x] **Step 2: 验证 RED**
  - Run: `.venv/bin/python -m pytest -q tests/test_performance_insights.py`
- [x] **Step 3: 最小实现**
  - 输出候选 Insight 到 Memory Review；
  - Dashboard 显示样本量和证据状态。
- [x] **Step 4: 验证 GREEN 与全量回归**
  - Run: 指定测试；
  - Run: `.venv/bin/python -m pytest -q`。
- [x] **Step 5: 重构并提交**
  - Commit: `feat: close performance memory loop`。

## 最终验收

- [x] `./scripts/start.sh` 启动 Review API 和 Dashboard；
- [x] `./scripts/stop.sh` 只停止本次启动的服务；
- [x] AIHOT 精选可增量导入；
- [x] Orchestrator 默认无外部副作用；
- [x] REVIEW 可在 Dashboard 操作；
- [x] APPROVED 内容不可绕过审核修改；
- [x] 部分发布不会重复整条 Thread；
- [x] Creator Intelligence 不抄原文、不把小样本变永久策略；
- [x] 工具帖和行情帖均保留证据边界；
- [ ] 全量测试、Ruff、mypy 和一键启动 smoke 通过。

> 验收注记（2026-10-05）：一键 smoke（start→API/表现洞察→stop→PID 清理）已通过；本计划涉及文件的
> pytest / Ruff / mypy 全绿；全量 pytest 为 523 passed + 1 失败、Ruff 1 处报错，均位于用户未提交的命理
> WIP（`engines/bazi/time_engine.py` 与 `tests/test_time_engine.py`，期望 forward 实为 backward），与本
> 计划无关且按约定不改，故最后一项暂不勾选，待该 WIP 收尾后复验。
