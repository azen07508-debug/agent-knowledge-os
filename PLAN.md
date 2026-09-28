# CreatorOS 完整执行计划（Phase 0–22）

> 保存日期：2026-09-28。来源：用户给出的 22 阶段执行路线，作为本仓库后续开发的唯一阶段基准。
> 验收原则见文末：每个阶段必须过测试并输出十项验收报告才能进入下一阶段。

## 一、最终目标

构建一个面向 X + 国内自媒体的平台型 AI Creator OS。

核心闭环：

```
Research → Strategy → Content → Human Review → Publish → Analytics → Memory → Strategy
```

最终目标不是「AI 自动写文章」，而是：

让 Agent 能持续研究互联网、理解账号定位、生产内容、辅助发布、分析结果，并把经过验证的经验沉淀为长期记忆。

---

## Phase 0：项目总原则

在整个开发过程中遵守以下原则：

1. 不直接把多个 GitHub 项目粗暴拼接。
2. CreatorOS 自己拥有核心数据模型和业务逻辑。
3. Agent-Reach 作为信息获取层。
4. x-mcp 作为 X 操作层。
5. 国内平台使用独立 Platform Adapter。
6. Agent-Knowledge-OS / EverOS / Obsidian / Git 作为长期记忆层。
7. PostgreSQL/SQLite 负责结构化运行数据。
8. AI Provider 必须可替换。
9. 所有自动发布默认经过人工审核。
10. 不把一次偶然的数据表现直接写成长期策略。
11. 不保存没有价值的垃圾记忆。
12. 所有重要结论尽量保留来源和证据。
13. 每个阶段完成测试后再进入下一阶段。
14. 不允许 Agent 一次性重写整个项目。

---

## Phase 1：完成 Memory Layer

目标：建立 CreatorOS 的长期记忆基础设施。

### 1.1 Memory 分类

建立以下一级分类：

```
/Account /Strategy /Research /Content /Experiments
/Analytics /Decisions /Agent /Insights
```

### 1.2 Account Memory

保存：账号定位、目标受众、内容领域、内容支柱、表达风格、长期目标、禁止内容、平台差异、账号阶段。

不要让 Agent 随意修改。重要修改必须产生 Decision Record。

### 1.3 Strategy Memory

保存：当前内容策略、内容支柱、目标方向、已验证策略、待验证策略、暂停策略、策略变更原因。

必须区分：Confirmed / Observed / Hypothesis / Unknown。不能把猜测写成事实。

### 1.4 Research Memory

保存：已研究项目、重要来源、关键事实、已验证信息、未验证信息、研究结论、研究时间、来源 URL。

不要保存所有原始抓取数据。原始数据应该进入数据库或缓存。Memory 只保存值得长期使用的研究结果。

### 1.5 Content Memory

保存：已发布内容、内容主题、内容形式、Hook、核心观点、平台、内容表现摘要、后续经验。

不要把完整历史帖子全部塞进长期记忆。

### 1.6 Experiment Memory

建立实验机制。每个实验至少包含：

Experiment ID / Hypothesis / Variables / Expected Result / Actual Result / Evidence / Conclusion / Confidence / Next Action

例如「项目实测类 Thread 是否比普通新闻类 Thread 更适合账号？」结果不能直接写「项目实测一定更好」，而应该写「当前 5 次实验中表现更高，但样本不足，继续验证」。

### 1.7 Analytics Memory

Analytics 不直接改变长期策略。正确流程：

```
Analytics → 分析 → 提出候选 Insight → Memory Review → 写入长期记忆
```

例如 Analytics：「5 个项目拆解内容平均互动率更高。」Memory：「目前观察到项目拆解内容表现较好，样本量 5，置信度低，继续验证。」

### 1.8 Agent Memory

分别记录 Research Agent / Content Agent / Analytics Agent / Publisher Agent 的经验。例如：哪些信息源噪音较大、哪些任务经常失败、哪些内容容易产生 AI 味、哪些检查经常发现问题。

### 1.9 Decision Memory

记录重要决策：为什么选择 X？为什么选择 Agent-Reach？为什么暂时不做某个平台？为什么修改账号定位？为什么停止某种内容？这样以后 Agent 不会反复重新讨论已经解决的问题。

### 1.10 Memory 生命周期

必须实现：`Capture → Normalize → Validate → Store → Retrieve → Update → Archive`，而不是 `Agent → Markdown → 完事`。

---

## Phase 2：Memory API

记忆层稳定后，不要让其他 Agent 直接操作 Obsidian 文件。建立统一 Memory API。

至少提供：`memory.search()` `memory.get()` `memory.create()` `memory.update()` `memory.archive()`

以及：`memory.recordObservation()` `memory.recordHypothesis()` `memory.recordDecision()` `memory.recordExperiment()` `memory.recordInsight()`

---

## Phase 3：Memory Governance

建立记忆质量规则。每条长期记忆至少需要：

type / content / source / createdAt / updatedAt / confidence / status

状态：`ACTIVE` `PENDING` `ARCHIVED` `SUPERSEDED`

置信度：`LOW` `MEDIUM` `HIGH`

这样以后 Agent 才不会越来越「失忆」或者「胡乱记忆」。

---

## Phase 4：Research Layer

Memory Layer 完成后开始接 Research。第一优先级：Agent-Reach。

负责：X / 网页 / GitHub / YouTube / RSS / 其他公开信息源。

建立 ResearchItem，字段至少包括：

source / URL / author / timestamp / title / content / engagement / topic / evidence

---

## Phase 5：Research Agent

工作流程：

```
信息源 → 搜索 → 抓取 → 去重 → 分类 → 提取事实 → 提取观点 → 提取证据 → 形成候选选题
```

输出：Topic Candidate。

---

## Phase 6：Topic Engine

建立选题系统。每个候选选题包含：

Topic / Angle / Audience / Source / Evidence / Freshness / Competition / Account Fit / Content Type

不要直接做「AI 热点排行榜」。应该让 Agent 给出：为什么值得研究？证据是什么？是否适合当前账号？有哪些可用角度？

---

## Phase 7：Strategy Agent

把 Memory 接入 Research。流程：

```
Research ↓ Account Memory ↓ 历史内容 ↓ 历史表现 ↓ Strategy ↓ Topic Recommendation
```

最终让 Agent 能回答：「这个选题为什么适合这个账号？」

---

## Phase 8：Content Object

CreatorOS 最重要的数据结构之一。

字段：topic / angle / audience / sources / evidence / claims / hook / coreContent / media / platformVersions / status

状态：`IDEA` `RESEARCHED` `DRAFT` `REVIEW` `APPROVED` `SCHEDULED` `PUBLISHED` `ARCHIVED`

---

## Phase 9：Content Agent

流程：

```
Topic → Research → Evidence → Outline → Draft → Fact Check → Style Check → AI味检查 → Human Review
```

第一阶段只做：X Post / X Thread。

---

## Phase 10：X Layer

使用 Agent-Reach + x-mcp，形成 `Research X → Content X → Review → Publish X → Analytics X`。

支持：Post / Thread / Search / Timeline / Mentions / Media / Schedule / Analytics

所有 X API 逻辑必须放进 XAdapter，禁止散落到业务代码。

---

## Phase 11：X 内容工作流

参考 x-post-scheduler 的工作方式，支持：

`文章 URL → Research → 摘要 → 核心观点 → X Post → Thread → 人工修改 → 发布`

以及 `Topic → Thread`、`Research → Original Post`。

---

## Phase 12：Human Review

正式发布前的强制环节。

状态：`DRAFT → REVIEW → APPROVED → SCHEDULED → PUBLISHED`

审核界面显示：原始研究 / 来源 / AI 生成内容 / Claims / Evidence / AI 建议 / 修改记录。避免 Agent 无依据地产生内容。

---

## Phase 13：国内平台 Layer

X 跑通以后再做。顺序：小红书 → 抖音 → B站 → 公众号 → 微博 → 视频号。

统一 PlatformAdapter，接口：`createDraft()` `validate()` `publish()` `schedule()` `getStatus()` `getAnalytics()`

---

## Phase 14：Platform Formatter

不要重新研究内容。统一 `ContentObject → X Formatter / Xiaohongshu Formatter / Douyin Formatter / Bilibili Formatter`。

例如同一个研究「Agent-Reach 深度分析」：X → Thread；小红书 → 项目拆解；抖音 → 60 秒口播；B站 → 长视频脚本。

---

## Phase 15：Publisher Layer

建立统一发布队列。

PublishJob：contentId / platform / accountId / scheduledAt / status / attempts / error / result

状态：`QUEUED` `PROCESSING` `SUCCESS` `FAILED` `RETRYING` `CANCELLED`

所有发布行为必须记录日志。

---

## Phase 16：Analytics Layer

发布之后收集：Views / Likes / Comments / Reposts / Bookmarks / Followers / Engagement / Publish Time / Content Type

建立 PostAnalytics。

---

## Phase 17：Analytics Agent

Analytics Agent 不直接修改策略。

流程：`Analytics → Pattern Detection → Insight Candidate → Evidence Check → Memory → Strategy Candidate`

例如「最近 10 条内容中，项目实测类内容互动率较高」，而不是「以后全部做项目实测」。

---

## Phase 18：Memory Feedback Loop

正式形成核心闭环：

```
Research ↓ Strategy ↓ Content ↓ Publish ↓ Analytics ↓ Insight ↓ Memory ↓ Strategy
```

---

## Phase 19：Dashboard

首页：今日研究 / 热点 / 推荐选题 / 草稿 / 待审核 / 排期 / 最近发布 / 数据 / AI Insight

页面：Dashboard / Research / Topics / Content / Calendar / Review / Publish / Analytics / Memory / Accounts / Settings

---

## Phase 20：Memory Dashboard

记忆系统最终应该拥有的界面，显示：

- Account Memory：账号现在是谁
- Strategy Memory：现在采取什么策略
- Learned Patterns：已经观察到什么
- Experiments：正在验证什么
- Decisions：过去为什么这样决定
- Agent Knowledge：Agent 学到了什么
- Memory Health：重复记忆 / 过时记忆 / 相互冲突 / 无来源结论 / 低置信度结论

---

## Phase 21：自动化 Agent

前面的系统稳定后才进入真正 Agent 化。每日流程：

```
09:00 Research Agent → 发现信息 → Topic Agent → 筛选选题 → Strategy Agent → 选择候选方向
→ Content Agent → 生成内容 → Human Review → Publisher → Analytics → Memory → 第二天继续
```

---

## Phase 22：最终能力

- 早上：告诉你「今天值得关注的 10 个话题」，再告诉你「其中 3 个最符合当前账号定位」。
- 生成 X Post / X Thread / 小红书 / 抖音 / B站 内容，你审核、修改一次。
- 系统发布到对应平台。
- 晚上：Analytics Agent 分析今天内容表现；Memory Agent 只把真正有价值的经验写入长期记忆。

---

## 最终系统结构

```
                CreatorOS
                    │
    ┌───────────────┼───────────────┐
    ↓               ↓               ↓
Research        Strategy        Memory
    │               │               │
Agent-Reach     Account Memory   Obsidian
    │               │            EverOS
    └───────────────┤              Git
                    ↓
              Content Agent
                    │
             Content Object
                    │
    ┌───────────────┼───────────────┐
    ↓               ↓               ↓
    X              小红书            抖音
    │               │               │
  x-mcp          Adapter          Adapter
    │               │               │
    └───────────────┼───────────────┘
                    ↓
                 Publish
                    ↓
               Analytics
                    ↓
             Analytics Agent
                    ↓
                 Memory
                    ↓
               Strategy
                    ↓
                下一轮
```

---

## 当前执行顺序

```
Phase 1：Memory Layer
↓ Phase 2：Memory API
↓ Phase 3：Memory Governance
↓ Phase 4：Agent-Reach（Research Layer）
↓ Phase 5：Research Agent
↓ Phase 6：Topic Engine
↓ Phase 7：Strategy Agent
↓ Phase 8：Content Object
↓ Phase 9：Content Agent
↓ Phase 10：X Layer + x-mcp
↓ Phase 11：X 内容工作流
↓ Phase 12：Human Review
↓ Phase 13–15：小红书 / 抖音 / B站 + Publisher
↓ Phase 16–18：Analytics + Memory Feedback
↓ Phase 19–20：Dashboard + Memory Dashboard
↓ Phase 21：自动化 Agent
↓ Phase 22：完整 CreatorOS
```

---

## 每个阶段的验收原则

任何阶段完成后都必须让 Agent 输出：

1. 修改了什么
2. 为什么修改
3. 文件清单
4. 数据结构
5. API
6. 测试结果
7. 构建结果
8. 已知问题
9. 未实现功能
10. 下一阶段建议

没有通过测试，就不要进入下一阶段。

尤其是 Memory Layer：先把「记什么、为什么记、怎么检索、什么时候更新、什么时候废弃」解决，再接任何内容 Agent。这样后面接 Agent-Reach、X、国内平台时，它们都会成为记忆系统的使用者和数据来源，而不是各自再造一套记忆机制。
