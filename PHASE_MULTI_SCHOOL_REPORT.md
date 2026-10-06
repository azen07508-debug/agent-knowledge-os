# 多流派策略内核阶段验收报告

日期：2026-10-05
范围：Task 1–8（多流派策略内核本地 MVP）

## 结论

本阶段本地验收通过。策略上下文、显式注册、冲突保留、Evidence provenance、规则状态过滤、Analyst/Critic/Report 分层、四层评估模型和 API 显式策略选择均有实现与测试证据。这个结论只覆盖仓库内的本地 MVP，不代表外部 benchmark 成绩、生产可用性或命理预测准确率。

## 本次修改

- `MINGLI_PLAN.md`：新增阶段收口状态，明确 Task 8 已完成及后续边界。
- `PHASE_MULTI_SCHOOL_REPORT.md`：新增本验收报告。
- 未修改其他任务代码；未纳入或修改 worktree 中未跟踪的 `uv.lock`。

## 文件与接口证据

| 设计要求 | 实现位置与接口 | 验收判断 |
|---|---|---|
| 策略 provenance | `engines/bazi/strategies.py`：`StrategyContext(school, policy, version, assumptions)`、`StrategyResult`、`DayunResult` | 通过；结果携带来源、证据、置信度、冲突和 `approximate` 标记。空的 school/policy/version 会被拒绝。 |
| 显式策略选择 | `engines/bazi/strategy_registry.py`：`StrategyRegistry.register/get/list/run` | 通过；按完整 `(school, policy, version)` 寻址，不猜测版本，不静默覆盖重复 key。 |
| 近似算法透明 | `ClassicalApproxDayunPolicy` | 通过；`classical_approx_v1` 明确声明近似假设，结果 `approximate=True`，并记录未计算精确起运时刻的冲突。 |
| 跨流派冲突 | `engines/bazi/strategy_compare.py`：`compare_results`、`ConflictReport` | 通过；保留所有结果和 provenance，输出结构化差异，不投票吞掉冲突。 |
| Evidence provenance | `knowledge/evidence.py`：`Evidence.strategy_context`、`rule_statuses`、`to_dict()` | 通过；事实来源、规则 ID/来源、策略上下文、冲突和证据强度可序列化。证据强度不是事件概率。 |
| 规则状态 | `knowledge/rules.py` 与 `build_evidence(..., include_unreviewed=False)` | 通过；默认排除 `UNREVIEWED`，并保留命中规则状态；待校核规则不作为默认权威引用。 |
| Analyst/Critic/Report | `agents/mingli.py`：`AnalystAgent.analyze`、`CriticAgent.critique`；`agents/report.py`：`ReportGenerator.render` | 通过；先构建证据，再生成保守结论；Critic 检查来源、危险措辞和冲突；报告包含输入、事实、策略、规则、结论、冲突和限制章节。 |
| 分层评估 | `evaluation/core.py`：`EvaluationCase`、`EvaluationResult`、`EvaluationSummary`、`summarize` | 通过；计算、规则、Agent 行为、冲突率、证据引用率和确定性措辞违规率分开统计，并区分有来源的权威样本。 |
| API 策略选择 | `api/server.py`：`AnalyzeRequest`、`POST /api/analyze` | 通过；`school`、`policy`、`version` 为可选显式选择器，服务层负责校验和路由；空白/不完整选择不会静默猜测。 |

## 对照设计文档逐条验收

1. **确定性计算与分层依赖**：通过本地 provider → canonical chart → facts/evidence → agent 的现有测试；LLM 不参与四柱或策略计算。
2. **每个解释结果的五项元数据**：`school/policy/version` 在策略上下文中；`evidence/confidence/conflicts` 在结果与 Evidence 中；通过 focused tests。
3. **大运策略契约**：通过 `DayunStrategy`、结构化 `DayunResult` 和显式 `classical_approx_v1` 测试；精确起运仍未实现，已显式标为近似。
4. **旺衰/用神独立策略结果模型**：本阶段已有策略内核通用契约与大运实现；独立旺衰、用神策略实现不是本 Task 交付，不作已完成声明。
5. **冲突处理**：通过 `compare_results` 测试；并列保留差异，不自动选“真相”。
6. **规则版本化与状态流转**：规则包含来源、流派、条件、置信等级、冲突和状态；默认过滤未校核规则。完整文献逐条校核仍待后续。
7. **Evidence Layer**：事实可复现提取、规则匹配、未满足条件的安全拒绝、强度计算、冲突和序列化均有本地测试。
8. **Analyst/Critic/Report**：三层接口与固定报告章节有测试；报告保留策略和证据边界，并输出非概率式限制说明。
9. **评估分层**：本地模型区分计算、规则、Agent 行为和策略冲突指标；没有把外部 benchmark 或不同层指标混成一个准确率。
10. **API 可选择策略**：`POST /api/analyze` 支持显式 selector；API 测试覆盖成功路径、选择器校验和错误响应。

## 验证结果

以下命令均在 worktree `/Users/admin/Desktop/workspace/projects/agent-knowledge-os/.worktrees/multi-school-strategy-kernel` 执行，使用主项目虚拟环境：

- focused pytest：**45 passed, 1 warning**
- full pytest：**555 passed, 1 warning**
- ruff：`ruff check engines knowledge agents evaluation runtime api tests` **通过**
- 编译检查：`python -m compileall -q engines knowledge agents evaluation runtime api` **通过**
- 依赖检查：`pip check` **通过，无 broken requirements**

已知 warning：FastAPI TestClient 导入链报告 `StarletteDeprecationWarning`，提示 `starlette.testclient` 使用 `httpx` 已弃用、建议安装 `httpx2`。该 warning 来自环境依赖，不影响本次 45/555 测试结果；本 Task 不调整依赖或 `uv.lock`。

## 未实现与边界

- **MingLi-Bench / fate-bench**：尚未下载、适配或运行真实外部数据，因此不填写准确率或命中率，不宣称 benchmark 达标。
- **紫微斗数**：本阶段不实现紫微引擎；当前交付仍是八字策略内核范围。
- **Web UI**：不在本阶段交付；仅有本地 FastAPI API 入口。
- **MCP**：不在本阶段交付。
- **认证与授权**：API 没有生产级认证、租户隔离或权限系统。
- **生产部署**：没有声明 Docker/Kubernetes/Railway、监控、审计、容量和安全加固已完成。
- **文献权威性**：待 `REVIEWED/ACTIVE` 的规则不能当作生产权威引用；经典文献逐条校核未完成。
- **命理结论**：证据强度不是现实事件概率；系统不提供医疗、法律、投资或人生决策保证。

## Deferred minors

- 完善旺衰、用神和事件窗口的独立策略实现与更多 golden cases。
- 扩充真实边界 case、第二排盘实现 differential testing，以及大运/流月精确算法。
- 完成主题化 Evidence 和更细粒度强度模型。
- 完成经典文献底本、规则版本和人工审核流程。
- 处理 Starlette/httpx 依赖 warning（另立依赖升级任务，避免在本阶段扩大范围）。

## 下一阶段建议

先建立受许可、可复现的 MingLi-Bench/fate-bench 数据适配与本地 fixture，再报告外部指标；随后补齐旺衰/用神策略和文献审核，最后单独规划紫微、Web、MCP、认证及生产部署。所有后续报告仍应区分计算、规则、Agent 和外部 benchmark 指标。

## 后续进展（2026-10-06，同一分支的追加提交）

以下交付超出 Task 1–8 范围，已分别提交；上文「未实现与边界」描述的是 Task 1–8 的交付边界，不代表当前分支状态。

- **大运与流派差异**：`DayStemDayunPolicy`、`LichunDayunPolicy`，顺逆依据（年干/日干）× 起运基准（节/立春）正交两维；`classical_approx_v1` 仍显式标 `approximate=True`。
- **流月与事件窗口**：`liu_month_at`、`extract_facts(..., liu_month)`、4 条 `UNREVIEWED` 流月规则、`event_windows` 与 `POST /api/windows`；结构事实不带 school/policy。
- **旺衰与用神**：`ClassicalStrengthPolicy`（`approximate=True`，confidence 0.4）、`ClassicalYongshenPolicy`（扶抑法，中和命局候选留空不猜）。
- **外部 benchmark**：`evaluation/external.py`、`scripts/run_external_benchmarks.py`。实测 fate-bench 295 条中 289 条可复算，289/289 通过（四柱/日主/十神/纳音/藏干十神，藏干按集合比对）；其中 106 例差异仅为巳藏干书写顺序（丙戊庚 / 丙庚戊），单独计数不计失败；大运顺逆按年干规则 289/289，按日干规则 145/289。mingli-bench 160/160 可排盘。问答类指标恒为 `None` 并写明原因（本系统无 LLM 作答器）。
- **紫微斗数**：`engines/ziwei/` 与 `POST /api/ziwei`，排十二宫干支、五行局、十四主星、六吉六煞、禄存天马与生年四化；闰月归属（split/preceding/following）与晚子时起日以策略参数显式声明。整盘与参考实现 iztro v2.6.1 的 8 组对照向量一致，夹具固化在 `tests/fixtures/ziwei_reference.json`。不含大限、流年、星曜亮度与其余杂曜。
- **验证**：全量 pytest **642 passed**；`ruff check .` 通过；`git diff --check` 干净。
