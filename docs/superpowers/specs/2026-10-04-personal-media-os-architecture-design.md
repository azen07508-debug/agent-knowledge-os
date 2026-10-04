# Personal Media OS 总体架构设计

## 目标

把 `agent-knowledge-os` 从一组可运行脚本升级为一个本地优先的 Personal Media OS：

```text
采集 → 热点判断 → 研究大V → 提炼风格 → 内容生产 → 质量检查
→ 人工审核 → 多平台发布 → 数据分析 → 记忆与策略更新
```

第一阶段继续以 X 为真实发布主平台，国内平台先保留统一契约和演练能力，不把未验证的写入能力伪装成已接入。

## 产品边界

### 一键启动的含义

`./scripts/start.sh` 启动的是本地工作台，不是无条件启动所有外部副作用：

- API / Review 服务；
- Dashboard；
- 本地 SQLite 存储；
- Orchestrator 进程；
- 本地任务队列或轻量调度；
- 可选的 AIHOT / Research 连接。

联网采集、模型调用、真实发布、指标采集必须保留独立开关，并在 Dashboard 显示当前开关状态。

### 不引入的东西

当前不引入 Redis、Kafka、Celery、Temporal 或新的数据库系统。项目是单用户、本机优先系统，先使用 SQLite、JSONL 和可恢复任务状态。只有多 worker、跨机器或实际吞吐成为瓶颈时才重新评估。

## 目标架构

```text
                         一键启动
                             │
                     ┌───────▼────────┐
                     │  Orchestrator  │
                     │   总调度器      │
                     └───────┬────────┘
                             │
       ┌─────────────────────┼─────────────────────┐
       ▼                     ▼                     ▼
 Source Layer         Intelligence Layer     Creator Intelligence
 采集/归一化            热点/选题/证据            大V/风格/结构
       │                     │                     │
       └─────────────────────┼─────────────────────┘
                             ▼
                       Memory Layer
              Source / Topic / Creator / Style
                    Content / Performance
                             │
                             ▼
                      Content Factory
             Research → Outline → Writer
                    → Fact Check → Style
                    → Platform Adapter
                             │
                             ▼
                       Human Gate
                             │
                             ▼
                 Publishing + Reconciliation
                             │
                             ▼
                         Analytics
                             │
                             └──────→ Memory
```

## 分层设计

### 1. Source Layer

统一输入模型 `SourceItem`，至少包含：

```text
source
title
url
published_at
content
author
source_type
raw_metadata
```

输入适配器：

- AIHOT 公开精选/API；
- Agent-Reach web / GitHub / page；
- RSS；
- 官方博客；
- X 公开读取；
- 未来的 Crypto 行情与链上数据。

所有输入先归一化进入 `ResearchStore`，后续 Agent 不直接关心来源协议。

约束：

- 原始材料和长期记忆分离；
- 失败不写假材料；
- 来源 URL 必须保留；
- 公开资料、本人实测、混合证据必须区分。

### 2. Intelligence Layer

分为三个职责：

#### HotScore

第一阶段只做可解释评分，不编造社交热度：

```text
HotScore =
  source_authority
  + cross_source_confirmation
  + freshness
  + novelty
  + account_fit
  + observed_engagement
```

缺数据时写 `UNKNOWN`，不补猜测数字。

#### Topic Engine

输出：

- 选题；
- 分类；
- 来源；
- 事实线索；
- 证据摘录；
- 账号契合度；
- 推荐角度；
- 标题候选；
- 阻塞项。

#### Evidence Gate

内容进入 `REVIEW` 前必须能回答：

- 这是公开资料、本人实测还是混合证据？
- 每个事实来自哪里？
- 哪些结论仍是观点或假设？
- 是否存在未验证的收益/行情承诺？

### 3. Creator Intelligence

研究大V不是复制文章，而是提炼可解释结构。

`CreatorProfile` 记录：

- author；
- 常用选题；
- 标题结构；
- 开头 Hook；
- 段落长度；
- 信息密度；
- 情绪强度；
- 论证方式；
- CTA 方式；
- 内容形式；
- 公开表现数据及样本量。

输出的是结构规则和观察，不直接写入“必须模仿”的永久策略。未经样本验证的风格结论状态为 `HYPOTHESIS` 或 `OBSERVED`。

### 4. Memory Layer

长期记忆分层：

```text
Source Memory
    ↓
Topic Memory
    ↓
Creator Memory
    ↓
Style Memory
    ↓
Content Memory
    ↓
Performance Memory
```

实现上继续保留：

- SQLite 运行数据；
- Obsidian 人类可读记忆；
- EverOS 可选增强检索。

重要规则：

- Analytics 只能产生待审核 Insight；
- 一次爆款不能直接变成长期策略；
- 所有策略变化必须记录原因；
- 证据状态不能由普通字段填充绕过。

### 5. Content Factory

内容工厂不是一个万能 Agent，而是多个可测试阶段：

```text
Research Agent
      ↓
Outline Agent
      ↓
Writer Agent
      ↓
Fact Check Agent
      ↓
Style Agent
      ↓
Platform Adapter
```

统一内容对象必须保留：

- `title_candidates`；
- `evidence_status`；
- `content_source`；
- `platform_posts`；
- `review_notes`；
- `status`。

X 规则：

- 能放入一条帖子就不拆；
- 超出长度才使用同一根帖的评论链；
- 根帖和评论不得重复；
- 真实换行，不允许字面量 `\\n`；
- 部分成功必须进入人工对账状态。

### 6. Human Gate

统一状态：

```text
REVIEW → APPROVED
REVIEW → DRAFT
```

Review 面板显示：

- 标题候选；
- 研究材料；
- 来源；
- Claims；
- Evidence；
- 帖子边界；
- 证据状态；
- Creator 结构参考；
- 修改记录。

人工审核不允许：

- 页面直接发帖；
- 页面自动批准；
- 公开资料直接改成实测；
- 把审核后的内容静默覆盖。

### 7. Publishing Layer

发布统一通过 `PublishJob`：

- 幂等键；
- attempt；
- provider request ID；
- timeout；
- reconciliation；
- `NEEDS_REVIEW`；
- post ID；
- 发布 JSONL 日志。

部分成功的 Thread 不得标记为完整 `SUCCEEDED`。已有未解决发布 Job 时禁止整条重新发送。

### 8. Analytics Layer

发布之后收集：

- Views；
- Likes；
- Replies；
- Reposts；
- Bookmarks；
- Followers；
- Engagement Rate；
- 发布时间；
- Content Type；
- 标题结构；
- Creator 参考结构。

数据进入 Performance Memory 前必须标明：

- 样本量；
- 采集时间；
- 数据来源；
- 是否包含转发；
- 是否足以支持结论。

## Orchestrator

第一阶段实现轻量 `Orchestrator`，不引入分布式队列。

任务类型：

```text
IMPORT_AI_HOT
RESEARCH
BUILD_TOPICS
RESEARCH_CREATORS
BUILD_DRAFTS
RUN_CHECKS
WAIT_HUMAN_REVIEW
PUBLISH_APPROVED
COLLECT_ANALYTICS
WRITE_INSIGHT_CANDIDATE
```

每次运行写 `data/orchestrator_runs.jsonl`：

- run_id；
- stage；
- status；
- started_at；
- finished_at；
- inputs；
- outputs；
- errors；
- external_side_effects。

默认流程只执行本地导入、分析和草稿生成；联网、模型、发布和指标采集必须由开关显式开启。

## 一键启动

第一版启动内容：

```text
Review API
Dashboard HTML
本地 SQLite Store
Orchestrator 状态页
```

不默认启动：

- 真实模型调用；
- AIHOT 外部采集；
- X 发布；
- 浏览器控制；
- 账号 Cookie 读取。

命令：

```bash
./scripts/start.sh
./scripts/stop.sh
```

`start.sh` 负责路径、虚拟环境、端口、PID、日志、Dashboard 生成和 Review API；不杀未知进程，不覆盖用户已有服务。

## 分阶段路线

### Phase 1：不变量与审核基础

- 完成 `APPROVED` 内容保护；
- 完成部分发布阻断和对账；
- 完成结构化帖子边界；
- 完成 Review API 和 Dashboard 操作；
- 一键启动 Review 工作台。

### Phase 2：Source Layer 统一

- 将 AIHOT、Agent-Reach、RSS 统一为 `SourceItem`；
- 增量导入和游标；
- 来源健康与失败记录；
- 保留原文 URL 和证据。

### Phase 3：Orchestrator

- 建立轻量阶段状态机；
- `orchestrator_runs.jsonl`；
- Dashboard 显示运行状态；
- 失败可恢复，不重复付费。

### Phase 4：Creator Intelligence

- 大V公开内容采集；
- 标题、Hook、段落、信息密度、CTA 结构提取；
- CreatorProfile；
- 样本不足时标记假设，不写成规则。

### Phase 5：Content Factory

- 研究、提纲、写作、事实、风格、平台适配拆开；
- X / 小红书 / 公众号 / 视频脚本使用同一 Canonical Content；
- 各平台保持独立审核和发布回执。

### Phase 6：Analytics → Memory

- 统一采集发布后表现；
- 按内容类型、标题结构、Creator 参考结构分组；
- 样本达标后生成待审核 Insight；
- 人工确认后更新 Strategy Memory。

## 验收标准

系统达到下一阶段前必须满足：

- 所有外部副作用有独立开关；
- 所有发布有 Job、Attempt 和对账记录；
- 所有审核动作有 reviewer 和 note；
- 所有公开资料和实测结论可区分；
- 所有内容可以追溯到来源；
- 全量测试、Ruff、mypy 或已知遗留错误清单明确；
- 一键启动和停止不会误杀其他进程。
