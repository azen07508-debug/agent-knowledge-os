# Multi-School MingLi Strategy Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前命盘、规则和 Agent MVP 扩展为带 `school / policy / version` provenance 的多流派策略内核，并持续输出可比较、可审计、可评估的命理结果。

**Architecture:** 保留 sxtwl 作为确定性 Chart Provider；新增独立的策略上下文、策略结果、注册表和比较器。大运、旺衰、用神、事件窗口分别实现为可替换策略，Evidence Layer 只消费结构事实和规则命中，不直接生成预测。Analyst/Critic/Report 层统一检查来源、冲突和确定性措辞。

**Tech Stack:** Python 3.12+、dataclasses、sxtwl 2.0.7、pytest、ruff、FastAPI；不引入 LLM SDK，不读取或发送密钥。

**Spec:** `docs/2026-10-04-multi-school-mingli-design.md`

## Global Constraints

- 计算与推理分离：LLM 不负责计算，只负责理解问题和解释证据。
- 每个解释性结果必须携带 `school`、`policy`、`version`、`evidence`、`confidence`、`conflicts`。
- 近似算法必须明确标记 `approximate=True`，不得成为默认唯一真相。
- 规则来源未经核校时必须标记待校核，不得冒充权威引文。
- 证据强度不是现实事件发生概率。
- 冲突不得静默吞掉；比较器必须输出并列结果和差异来源。
- 新功能先写失败测试，再写最小生产代码；每个任务独立验证并提交。
- 不覆盖或删除现有未提交的 CreatorOS/Review Server 改动。
- 不读取、记录或发送 `.env`、token、Cookie、私钥、OAuth 或其他凭据。

## Review Focus

- **缺少 gender 的大运输入**：必须拒绝，而不是猜顺逆；由 Task 2 测试。
- **同一命盘的不同策略结果**：必须并列输出冲突和策略 provenance；由 Task 3 测试。
- **规则来源不完整或未校核**：不得进入权威报告；由 Task 4 测试。
- **证据强度被写成概率或确定事件**：Critic 必须拦截；由 Task 5 测试。
- **Provider 版本或 Chart 来源不一致**：必须拒绝结果；由 Task 1 测试。

---

### Task 1: Strategy Context and Result Contracts

**Files:**
- Create: `engines/bazi/strategies.py`
- Modify: `engines/bazi/time_engine.py`（将现有近似大运输出迁移到新结果契约）
- Test: `tests/test_strategy_contracts.py`

**Interfaces:**
- Consumes: `Chart`、现有 `ClassicalApproxDayunPolicy` 的输入约束。
- Produces: `StrategyContext`、`StrategyResult`、`DayunResult`、`DayunStrategy` Protocol；后续注册表、比较器和报告层只依赖这些类型。

- [ ] **Step 1: Write the failing tests**
  - `test_strategy_context_requires_school_policy_version()`：空字段抛出 `ValueError`。
  - `test_strategy_result_keeps_provenance_and_approximation()`：结果保留 context、assumptions、evidence、confidence、`approximate`。
  - `test_dayun_strategy_protocol_result_is_structured()`：策略结果不再返回无来源裸 dict。
  - `test_dayun_without_gender_is_rejected()`：没有 gender 时抛出可解释错误。
- [ ] **Step 2: Run the tests to verify they fail**
  - Run: `.venv/bin/pytest -q tests/test_strategy_contracts.py`
  - Expected: FAIL because the strategy result types do not exist。
- [ ] **Step 3: Implement the minimal contracts**
  - 在 `engines/bazi/strategies.py` 定义不可变 dataclass 和 Protocol。
  - `StrategyContext` 字段固定为 `school: str`、`policy: str`、`version: str`、`assumptions: tuple[str, ...]`。
  - `StrategyResult` 固定包含 `context`、`evidence`、`confidence`、`conflicts`、`approximate`。
  - 将 `ClassicalApproxDayunPolicy` 适配为 `DayunStrategy`，名称固定为 `classical_approx_v1`。
- [ ] **Step 4: Run the tests to verify they pass**
  - Run: `.venv/bin/pytest -q tests/test_strategy_contracts.py tests/test_time_engine.py`
  - Expected: PASS。
- [ ] **Step 5: Run lint and commit**
  - Run: `.venv/bin/ruff check engines/bazi tests/test_strategy_contracts.py tests/test_time_engine.py`
  - Commit: `feat(strategy): add provenance-aware strategy contracts`

### Task 2: Dayun Strategy Registry

**Files:**
- Create: `engines/bazi/strategy_registry.py`
- Modify: `engines/bazi/time_engine.py`
- Test: `tests/test_strategy_registry.py`

**Interfaces:**
- Consumes: Task 1 的 `StrategyContext`、`DayunStrategy`、`StrategyResult`。
- Produces: `StrategyRegistry.register()`、`StrategyRegistry.get()`、`StrategyRegistry.list()`、`StrategyRegistry.run()`。

- [ ] **Step 1: Write failing tests**
  - 注册相同 `school/policy/version` 必须拒绝。
  - 查询不存在策略必须给出明确错误。
  - 注册表运行策略时必须返回带 provenance 的结果。
  - 允许同一 school 下不同 policy 并存。
- [ ] **Step 2: Run red test**
  - Run: `.venv/bin/pytest -q tests/test_strategy_registry.py`
  - Expected: FAIL because registry is absent。
- [ ] **Step 3: Implement minimal registry**
  - 使用 `(school, policy, version)` 作为唯一键。
  - 不在 registry 中自动选择策略；缺少显式 key 时抛错。
  - 将 `classical_approx_v1` 注册为显式内置策略。
- [ ] **Step 4: Run green tests**
  - Run: `.venv/bin/pytest -q tests/test_strategy_registry.py tests/test_strategy_contracts.py`
  - Expected: PASS。
- [ ] **Step 5: Commit**
  - Commit: `feat(strategy): add explicit strategy registry`

### Task 3: Strategy Comparator and Conflict Report

**Files:**
- Create: `engines/bazi/strategy_compare.py`
- Test: `tests/test_strategy_compare.py`

**Interfaces:**
- Consumes: `StrategyResult` 列表。
- Produces: `ConflictReport`，至少包含 `results`、`conflicts`、`has_conflict`、`summary`。

- [ ] **Step 1: Write failing tests**
  - 两个相同结论的策略返回 `has_conflict=False`。
  - 两个不同结论的策略并列保留，不投票、不丢弃。
  - 缺少 context 的结果拒绝比较。
  - 比较报告可序列化并保留 assumptions 和 evidence。
- [ ] **Step 2: Verify red**
  - Run: `.venv/bin/pytest -q tests/test_strategy_compare.py`
  - Expected: FAIL because comparator is absent。
- [ ] **Step 3: Implement comparator**
  - 使用结构化结论指纹比较，不用自然语言模糊相似度。
  - 冲突记录双方的 `(school, policy, version)` 和差异字段。
  - 不生成“多数派即正确”的结论。
- [ ] **Step 4: Verify green**
  - Run: `.venv/bin/pytest -q tests/test_strategy_compare.py`
  - Expected: PASS。
- [ ] **Step 5: Commit**
  - Commit: `feat(strategy): add conflict-aware comparator`

### Task 4: Evidence Provenance and Rule Review State

**Files:**
- Modify: `knowledge/rules.py`
- Modify: `knowledge/evidence.py`
- Modify: `knowledge/default_rules.py`
- Test: `tests/test_evidence_provenance.py`

**Interfaces:**
- Consumes: 当前 `RuleRegistry`、`Chart`、Task 1 的 `StrategyContext`。
- Produces: Evidence 中的 `school`、`policy`、`version`、`rule_status`；规则支持 `UNREVIEWED/REVIEWED/ACTIVE/DEPRECATED`。

- [ ] **Step 1: Write failing tests**
  - 未校核规则能匹配内部结构，但报告标记 `UNREVIEWED`。
  - `DEPRECATED` 规则默认不参与生产匹配。
  - Evidence 序列化结果包含策略 provenance 和来源状态。
  - 不同策略产生的 evidence 不得互相覆盖。
- [ ] **Step 2: Verify red**
  - Run: `.venv/bin/pytest -q tests/test_evidence_provenance.py`
  - Expected: FAIL because fields and state filters are absent。
- [ ] **Step 3: Implement minimal changes**
  - 为 Rule 增加 `status`，默认 `UNREVIEWED`。
  - `RuleRegistry.match()` 增加显式 `include_unreviewed=False` 参数。
  - Evidence 增加 `strategy_context` 和 `rule_statuses`，不改变既有调用的默认安全行为。
- [ ] **Step 4: Verify green**
  - Run: `.venv/bin/pytest -q tests/test_rules.py tests/test_evidence.py tests/test_evidence_provenance.py`
  - Expected: PASS。
- [ ] **Step 5: Commit**
  - Commit: `feat(evidence): preserve strategy and rule provenance`

### Task 5: Analyst/Critic/Report Safety Checks

**Files:**
- Modify: `agents/mingli.py`
- Create: `agents/report.py`
- Test: `tests/test_mingli_reporting.py`

**Interfaces:**
- Consumes: `Evidence`、`ConflictReport`、`Analysis`。
- Produces: `ReportGenerator.render()` 和新增 Critic 检查项。

- [ ] **Step 1: Write failing tests**
  - 报告必须显示采用流派、策略版本和 assumptions。
  - 有冲突时必须显示各策略，不得只显示一个结论。
  - 出现“必然/一定/保证/概率”时 Critic 必须失败并指出原因。
  - 低证据强度只能输出限制说明，不能输出确定性预测。
- [ ] **Step 2: Verify red**
  - Run: `.venv/bin/pytest -q tests/test_mingli_reporting.py`
  - Expected: FAIL because report generator and checks are incomplete。
- [ ] **Step 3: Implement minimal report layer**
  - 报告固定章节：输入口径、事实、策略、规则、结论、冲突、限制。
  - Critic 检查规则引用是否存在、冲突是否披露、证据强度是否被误写成概率。
- [ ] **Step 4: Verify green**
  - Run: `.venv/bin/pytest -q tests/test_mingli_agents.py tests/test_mingli_reporting.py`
  - Expected: PASS。
- [ ] **Step 5: Commit**
  - Commit: `feat(agent): add conflict-aware report safety checks`

### Task 6: Local Golden Cases and Evaluation Expansion

**Files:**
- Create: `data/benchmarks/mingli_cases.json`
- Modify: `evaluation/custom.py`
- Modify: `evaluation/core.py`
- Test: `tests/test_strategy_evaluation.py`

**Interfaces:**
- Consumes: Strategy Registry、Comparator、Report/Critic。
- Produces: 计算正确性、规则正确性、Agent 行为分开的评估指标；不填写外部 benchmark 分数。

- [ ] **Step 1: Write failing tests**
  - golden case 能验证 provider、四柱、十神、纳音和关系字段。
  - 策略冲突率、证据引用率、确定性措辞违规率分别统计。
  - 缺失 source 的 case 不能被计为权威样本。
- [ ] **Step 2: Verify red**
  - Run: `.venv/bin/pytest -q tests/test_strategy_evaluation.py`
  - Expected: FAIL because metrics and fixture schema are absent。
- [ ] **Step 3: Implement**
  - 保持 benchmark 数据为本地 JSON，不抓取个人敏感资料。
  - `EvaluationSummary` 扩展分类指标，但保留旧字段兼容。
  - 为每个结果保存 case source 和失败原因。
- [ ] **Step 4: Verify green**
  - Run: `.venv/bin/pytest -q tests/test_evaluation.py tests/test_strategy_evaluation.py`
  - Expected: PASS。
- [ ] **Step 5: Commit**
  - Commit: `feat(evaluation): add multi-school golden metrics`

### Task 7: Service/API Integration

**Files:**
- Modify: `runtime/mingli_service.py`
- Modify: `api/server.py`
- Test: `tests/test_strategy_api.py`

**Interfaces:**
- Consumes: registry、comparator、report generator。
- Produces: API 请求可指定 `school/policy/version`，响应返回策略结果、冲突和报告限制。

- [ ] **Step 1: Write failing tests**
  - `/api/analyze` 接受显式 strategy selector。
  - 不存在策略返回 422，不自动 fallback。
  - 未提供策略时接口返回“需要显式选择/当前默认配置”的可解释 metadata。
- [ ] **Step 2: Verify red**
  - Run: `.venv/bin/pytest -q tests/test_strategy_api.py`
  - Expected: FAIL because selector is absent。
- [ ] **Step 3: Implement**
  - Pydantic 请求模型增加可选 strategy selector。
  - Service 负责解析和校验，路由不直接操作规则或 Chart。
- [ ] **Step 4: Verify green**
  - Run: `.venv/bin/pytest -q tests/test_api.py tests/test_strategy_api.py`
  - Expected: PASS。
- [ ] **Step 5: Commit**
  - Commit: `feat(api): expose explicit strategy selection`

### Task 8: Full Verification and Phase Handoff

**Files:**
- Modify: `MINGLI_PLAN.md`
- Create: `PHASE_MULTI_SCHOOL_REPORT.md`

- [ ] **Step 1: Run focused checks**
  - `.venv/bin/pytest -q tests/test_strategy_contracts.py tests/test_strategy_registry.py tests/test_strategy_compare.py tests/test_evidence_provenance.py tests/test_mingli_reporting.py tests/test_strategy_evaluation.py tests/test_strategy_api.py`
- [ ] **Step 2: Run full checks**
  - `.venv/bin/pytest -q`
  - `.venv/bin/ruff check engines knowledge agents evaluation runtime api tests`
  - `.venv/bin/python -m compileall -q engines knowledge agents evaluation runtime api`
  - `.venv/bin/pip check`
- [ ] **Step 3: Review requirements line by line**
  - 对照设计文档确认 provenance、冲突、近似算法、规则状态和评估分层均有证据。
  - 明确未完成项：真实 MingLi-Bench/fate-bench 下载适配、紫微、Web UI、认证、生产部署。
- [ ] **Step 4: Write acceptance report**
  - 记录修改文件、接口、测试结果、已知限制、未实现项和下一阶段建议。
- [ ] **Step 5: Commit**
  - Commit: `docs: record multi-school strategy kernel acceptance`

## Spec Coverage Self-Review

- 多流派策略内核：Tasks 1–3。
- 规则版本化和 Evidence provenance：Task 4。
- Analyst/Critic/Report：Task 5。
- 计算、规则、Agent 分层评估：Task 6。
- API 可选择策略：Task 7。
- 全量验收和未完成项诚实记录：Task 8。
- 紫微、MCP、Web、用户记忆和商业化不属于本计划，按设计文档的后续阶段单独规划。
