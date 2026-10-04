# 命理智能体项目结构说明

本文档说明项目从 CreatorOS 转向 MingLi Agent 后的目录结构和职责调整。

---

## 项目转型

**原项目**：agent-knowledge-os（CreatorOS 内容创作系统）
**新方向**：MingLi Agent（可验证的命理推理系统）

转型原因：
1. 命理推理是更适合 Agent 验证的领域（有明确的规则和评估基准）
2. 可以利用现有的 Memory Layer 和 Agent 基础设施
3. 有完整的开源生态和评估体系（MingLi-Bench + fate-bench）

---

## 目录结构

```text
agent-knowledge-os/
├── agents/                    # Agent 实现
│   ├── __init__.py
│   ├── reasoning.py          # 推理 Agent（新）
│   ├── critic.py             # 审查 Agent（新）
│   └── conversation.py       # 对话 Agent（新）
│
├── engines/                   # 核心引擎（新目录）
│   ├── __init__.py
│   ├── bazi/                 # 八字排盘引擎
│   │   ├── calculator.py     # 四柱计算
│   │   ├── relations.py      # 刑冲合害
│   │   └── dayun.py          # 大运流年
│   ├── ziwei/                # 紫微斗数引擎（Phase 11）
│   └── integrations/         # 第三方引擎集成
│       └── heige.py          # HeiGe-SuanMing 适配器
│
├── knowledge/                 # 知识库（新目录）
│   ├── __init__.py
│   ├── rules/                # 规则库
│   │   ├── yuanhai.py        # 《渊海子平》
│   │   ├── ditian.py         # 《滴天髓》
│   │   ├── ziping.py         # 《子平真诠》
│   │   └── sanming.py        # 《三命通会》
│   ├── schools/              # 流派系统
│   │   ├── classical.py      # 子平正统
│   │   ├── ditian_school.py  # 滴天髓派
│   │   └── blind.py          # 盲派
│   └── evidence/             # 证据层
│       ├── facts.py          # 事实提取
│       ├── matcher.py        # 规则匹配
│       └── chain.py          # 证据链构建
│
├── runtime/                   # 运行时（保留并扩展）
│   ├── __init__.py
│   ├── memory_api.py         # 记忆 API（保留，用于用户档案）
│   ├── chart_store.py        # 命盘存储（新）
│   ├── analysis_store.py     # 分析结果存储（新）
│   └── time_engine.py        # 时间轴引擎（新）
│
├── evaluation/                # 评估系统（新目录）
│   ├── __init__.py
│   ├── mingli_bench.py       # MingLi-Bench 集成
│   ├── fate_bench.py         # fate-bench 集成
│   ├── custom_tests.py       # 自建测试集
│   └── metrics.py            # 评估指标
│
├── api/                       # API 服务（新目录，Phase 10）
│   ├── __init__.py
│   ├── server.py             # FastAPI 服务
│   ├── routes/               # 路由
│   │   ├── chart.py          # 排盘接口
│   │   ├── analyze.py        # 分析接口
│   │   └── history.py        # 历史记录
│   └── models.py             # Pydantic 模型
│
├── web/                       # Web UI（新目录，Phase 9）
│   ├── src/
│   │   ├── components/       # React 组件
│   │   ├── pages/            # 页面
│   │   └── utils/            # 工具函数
│   ├── public/
│   └── package.json
│
├── tests/                     # 测试（扩展）
│   ├── test_bazi_engine.py   # 排盘引擎测试
│   ├── test_rules.py         # 规则匹配测试
│   ├── test_evidence.py      # 证据层测试
│   ├── test_reasoning.py     # 推理测试
│   └── test_critic.py        # 审查测试
│
├── scripts/                   # 脚本（保留并扩展）
│   ├── import_heige.py       # 导入 HeiGe-SuanMing 数据
│   ├── import_rules.py       # 导入规则库
│   ├── run_benchmark.py      # 运行评估
│   └── seed_test_cases.py    # 生成测试数据
│
├── data/                      # 数据（保留并扩展）
│   ├── charts.sqlite3        # 命盘数据库
│   ├── analyses.sqlite3      # 分析结果数据库
│   ├── rules.sqlite3         # 规则库
│   └── benchmarks/           # 评估数据
│       ├── mingli-bench/
│       └── fate-bench/
│
├── obsidian_vault/           # Obsidian 笔记（调整）
│   ├── 00-Inbox/
│   ├── 01-UserProfiles/      # 用户命盘档案（新）
│   ├── 02-Questions/         # 历史问题（新）
│   ├── 03-Analyses/          # 分析记录（新）
│   ├── 04-Rules/             # 规则笔记（新）
│   ├── 05-Experiments/       # 验证实验（新）
│   ├── 06-Feedback/          # 用户反馈（新）
│   └── 99-Archive/
│
├── docs/                      # 文档（新目录）
│   ├── architecture.md       # 架构设计
│   ├── evidence_layer.md     # 证据层设计
│   ├── rule_format.md        # 规则格式说明
│   ├── school_system.md      # 流派系统
│   └── api_reference.md      # API 文档
│
├── .env.example
├── .gitignore
├── MINGLI_PLAN.md            # 完整执行计划
├── PLAN.md                   # 原 CreatorOS 计划（保留参考）
├── README.md                 # 项目说明
├── pyproject.toml
└── requirements.txt
```

---

## 职责调整

### 保留的模块

| 模块 | 原职责 | 新职责 |
|------|-------|-------|
| `runtime/memory_api.py` | 内容创作记忆 | 用户命盘档案、历史问题 |
| `obsidian_vault/` | 内容策略、研究笔记 | 用户档案、规则笔记、分析记录 |
| `agents/` | Research/Content/Strategy | Reasoning/Critic/Conversation |
| `tests/` | 内容工作流测试 | 排盘、推理、评估测试 |
| `scripts/` | 内容管道脚本 | 数据导入、评估脚本 |

### 新增的模块

| 模块 | 职责 |
|------|------|
| `engines/` | 排盘引擎（八字、紫微） |
| `knowledge/` | 规则库、流派系统、证据层 |
| `evaluation/` | Benchmark 集成、持续评估 |
| `api/` | RESTful API 服务 |
| `web/` | Web UI |
| `docs/` | 架构和 API 文档 |

### 废弃的模块

| 模块 | 原职责 | 废弃原因 |
|------|-------|---------|
| `runtime/reach_research.py` | Agent-Reach 调研 | 命理推理不需要互联网调研 |
| `runtime/x_adapter.py` | X 平台发布 | 不需要社交媒体发布 |
| `runtime/platform_adapter.py` | 国内平台适配 | 不需要平台发布 |
| `runtime/content_*.py` | 内容对象、草稿 | 不需要内容创作 |
| `runtime/publish_*.py` | 发布队列 | 不需要发布系统 |
| `runtime/analytics_*.py` | 表现数据采集 | 不需要数据分析 |
| `agents/researcher.py` | 调研 Agent | 不需要互联网调研 |
| `agents/strategist.py` | 策略 Agent | 不需要内容策略 |
| `agents/content.py` | 内容生成 | 不需要内容生成 |
| `agents/x_workflow.py` | X 工作流 | 不需要社交媒体工作流 |

---

## 数据流转

### Phase 1-3：基础能力

```text
用户输入生辰
    ↓
Bazi Engine 排盘
    ↓
Chart Store 存储
    ↓
返回四柱、十神等
```

### Phase 4-6：推理能力

```text
用户提问（事业如何？）
    ↓
Conversation Agent 理解问题
    ↓
Evidence Layer 提取事实 + 匹配规则
    ↓
Reasoning Agent 基于证据推理
    ↓
Critic Agent 审查推理质量
    ↓
Report Generator 生成报告
    ↓
Analysis Store 存储分析结果
```

### Phase 7：评估体系

```text
Agent 分析
    ↓
Evaluation Engine
    ↓
MingLi-Bench / fate-bench / Custom Tests
    ↓
生成评估报告（准确率、幻觉率等）
```

### Phase 8-10：产品化

```text
用户（Web / API）
    ↓
FastAPI Server
    ↓
Agent 推理
    ↓
返回结果（事实 + 规则 + 证据 + 结论）
    ↓
Memory API 记录历史
```

---

## 迁移策略

### 第一步：清理（当前）

- [ ] 标记废弃模块（添加 `# DEPRECATED` 注释）
- [ ] 更新 README.md 和 MINGLI_PLAN.md
- [ ] 创建新目录结构

### 第二步：保留复用（Phase 1）

- [ ] 保留 `runtime/memory_api.py`，调整为用户档案存储
- [ ] 保留 `obsidian_vault/`，调整目录分类
- [ ] 保留 `tests/` 框架，添加新测试

### 第三步：增量开发（Phase 1-10）

- [ ] 实现 `engines/bazi/`
- [ ] 实现 `knowledge/rules/`
- [ ] 实现 `knowledge/evidence/`
- [ ] 实现 `agents/reasoning.py`
- [ ] 实现 `agents/critic.py`
- [ ] 实现 `evaluation/`
- [ ] 实现 `api/`
- [ ] 实现 `web/`

### 第四步：完全迁移（Phase 11+）

- [ ] 删除废弃模块
- [ ] 重命名仓库（可选）
- [ ] 完善文档

---

## 开发规范

### 代码风格

- Python: 遵循 PEP 8，使用 black + ruff
- TypeScript: 遵循 Airbnb 规范
- 测试覆盖率 > 80%
- 每个模块必须有 docstring

### 提交规范

```text
feat(engines): add bazi calculator
fix(evidence): correct rule matching logic
test(evaluation): add MingLi-Bench integration
docs(architecture): update evidence layer design
```

### 分支策略

- `main`：稳定版本
- `develop`：开发版本
- `feature/*`：功能分支
- `phase/*`：阶段分支（如 `phase/1-chart-engine`）

### 验收标准

每个 Phase 完成后必须：

1. 通过所有测试
2. 更新文档
3. 更新 MINGLI_PLAN.md 进度
4. 提交验收报告（10 项清单）

---

## 常见问题

### Q1：为什么不直接创建新仓库？

A：保留现有的 Memory Layer 和 Agent 基础设施，可以加速开发。Obsidian vault、Memory API、测试框架都可以复用。

### Q2：原 CreatorOS 的代码还有用吗？

A：部分有用（Memory API、Obsidian 集成），部分无用（内容创作、平台发布）。无用的会标记为 DEPRECATED，Phase 11 后清理。

### Q3：如何处理 Git 历史？

A：保留完整 Git 历史。转型是演进而非重写，历史提交有参考价值。

### Q4：如何避免与原 CreatorOS 混淆？

A：
1. README.md 开头明确说明当前是 MingLi Agent
2. PLAN.md 重命名为 CREATOR_PLAN.md（归档）
3. MINGLI_PLAN.md 是当前执行计划
4. 可选：Phase 11 后重命名仓库为 `mingli-agent`

---

## 下一步

1. **Phase 1 准备**：
   - [ ] 调研 HeiGe-SuanMing 代码结构
   - [ ] 设计 `engines/bazi/` 接口
   - [ ] 准备 100 个排盘测试用例
   - [ ] 创建 `knowledge/rules/` 数据结构

2. **Phase 0 收尾**：
   - [x] 完成项目规划（MINGLI_PLAN.md）
   - [x] 更新 README.md
   - [x] 创建结构说明（本文件）
   - [ ] 标记废弃模块
   - [ ] 提交 Phase 0 验收报告

---

**当前状态**：Phase 0 规划完成，准备进入 Phase 1。

**责任人**：待确定

**预计时间**：Phase 1（2周），Phase 2-3（6周），总计 2 个月完成核心能力验证。
