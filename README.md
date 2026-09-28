# agent-knowledge-os

agent-knowledge-os 是一个本地 AI Agent 知识库系统，用来把 EverOS、Arbiter、Obsidian 和 Codex 工作流连接成一条可运行、可复盘、可扩展的本地闭环。

## 项目介绍

这个项目的目标不是接入真实大模型后立刻自动化一切，而是先把本地架构跑通：

- Codex 负责实际开发、修改代码、生成文件、运行测试。
- EverOS 负责长期记忆接口，当前以本机 HTTP API 封装和友好降级为主。
- Arbiter 负责预算管理、运行诊断和风险扫描。
- Obsidian vault 负责保存人类可读 Markdown 笔记。
- Git 负责版本管理、回滚和备份。

## 为什么结合 EverOS + Arbiter + Obsidian + Codex

单独使用 Agent 容易出现“执行完就忘”“错误重复发生”“预算和风险不可见”的问题。这个项目把四层职责拆开：

- EverOS：保存长期记忆线索。
- Arbiter：检查预算、记录运行状态和风险。
- Obsidian：沉淀概念、技能、错误、复盘和仓库分析。
- Codex：在本机实现、测试和审查代码。

## 架构图

```text
用户任务
  ↓
Planner Agent 拆解任务
  ↓
ArbiterGuard 检查预算
  ↓
EverOSMemory 搜索或写入历史记忆
  ↓
Researcher / Coder / Reviewer Agent 执行
  ↓
ObsidianExporter 生成 Markdown 笔记
  ↓
README / 日志 / 知识库更新
```

## 安装步骤

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果本机没有 `python3.12`，可以使用任何 `>=3.12` 的 Python，例如当前项目也支持 `python3` 指向 3.14。

## 如何启动 EverOS

```bash
everos demo
everos init
everos server start
```

也可以使用脚本：

```bash
bash scripts/start_everos.sh
```

平台限制（2026-09 实测）：本机是 Intel（x86_64）Mac，`lancedb` 从 0.26 起只发布 arm64/Windows wheel，因此这里装不上 EverOS 1.1+ 所依赖的 `lancedb`，`everos server start` 会在 lifespan 阶段报错。EverOS 服务需要跑在 arm64 主机（或远程机器）上，客户端把 `EverOSMemory(server_url=...)` 指过去即可。

如果 EverOS 没启动，demo 不会崩溃，会提示：

```text
EverOS 服务未启动，本次跳过长期记忆写入。
```

## CreatorOS 长期记忆层（Phase 1）

`runtime/creator_memory.py` 提供 9 类长期记忆（职责：Store what the system has learned, not everything the system has seen）：

| 类别 | 方法 | vault 目录 |
| --- | --- | --- |
| Account 账号是谁 | `save_account` / `update_account` | `09-Account/` |
| Strategy 当前策略 | `save_strategy` | `10-Strategy/` |
| Research 研究过什么 | `save_research` | `11-Research/` |
| Content 发过什么 | `save_content` | `12-Content/` |
| Experiments 验证什么 | `save_experiment` | `13-Experiments/` |
| Analytics 数据说明什么 | `save_analytics` | `14-Analytics/` |
| Decisions 为什么这样决定 | `save_decision` | `15-Decisions/` |
| Agent 学到什么 | `save_agent_experience` | `16-Agent/` |
| Insights 什么有效 | `save_insight` | `17-Insights/` |

生命周期：`Capture → Normalize → Validate → Store → Retrieve → Update → Archive`，对应 `remember()` 的规范化与校验、`recall()` 检索、`update_account()` 受控更新、`archive()` 归档（移入 `99-Archive/` 并把 `status` 改为 `archived`）。

写入时的硬边界：

- 必填字段不能为空，单条记忆上限 4000 字符（拒绝塞原文和 API 返回）。
- Account 画像已存在时修改必须带 `reason`，并自动产生一条 Decision Record。
- Strategy 状态只能是 `已确认/已观察/假设/未知`；不能把猜测写成事实。
- Insight 状态只能是 `观察/待验证/已验证`；一次数据不能变成永久规则。
- Experiment 结论只能是 `暂时支持/暂时不支持/数据不足`，必须带预期结果、证据、置信度与下一步。
- Analytics 只产出候选 Insight，处理状态固定为 `待 Memory Review`，不直接改长期策略。
- 置信度只能是 `低/中/高`。

初始化示例数据（幂等，重复执行不会覆盖；`--force` 才重写）：

```bash
python scripts/seed_creator_memory.py
```

检索用 `CreatorMemoryLayer.recall(query)`：先查 EverOS，查不到就降级为 vault 全文匹配。当前本机按降级模式运行——长期记忆只落在 Obsidian，检索走本地全文匹配。

## Memory API（Phase 2）

后续 Agent 只通过 `runtime/memory_api.py` 读写长期记忆，**不要直接打开 `obsidian_vault/` 下的文件**：

```python
from runtime.memory_api import MemoryAPI

memory = MemoryAPI()                      # 默认指向项目内 obsidian_vault

memory.search("项目实测")                  # 全库检索，EverOS 不可用时降级本地
memory.search("项目实测", category="insight")  # 只在某类别内检索
memory.get("account")                     # 固定单篇可省 title；返回 frontmatter + sections
memory.get("decision", "2026-09-28-决策-AI 生成标题")
memory.create("decision", "标题", {...})   # Account 已存在会要求改用 update
memory.update("strategy", "当前内容策略", {"当前内容策略": "..."})  # 合并更新，保留 created
memory.archive("insight", "2026-09-28-观察-内容类型")              # 移入 99-Archive

memory.recordObservation(topic=..., observation=..., evidence=...)   # 原始观察 -> 17-Insights
memory.recordInsight(topic=..., insight=..., evidence=...)           # 复核后的洞察 -> 17-Insights
memory.recordHypothesis(hypothesis=..., expected=...)                # 假设 -> 数据不足状态的实验
memory.recordExperiment(hypothesis=..., variables=..., expected=..., actual=...,
                        evidence=..., conclusion=..., confidence=..., next_action=...)
memory.recordDecision(subject=..., decision=..., reason=...)
```

约定：

- Account 是固定单篇，`create` 第二次会要求改用 `update(..., reason=...)`，并自动产生 Decision Record。
- 同名不同内容不会互相覆盖：文件名追加正文短哈希；内容相同则原地覆盖（幂等）。
- `update` 保留 `created` 与归档状态，只刷新正文与 `updated`。
- `recordHypothesis` 直接生成 `Experiment-00x`、结论固定 `数据不足`，等数据回填后再用 `recordExperiment` 或 `update` 升级结论。

## 治理（Phase 3）

每条记忆的 frontmatter 至少包含七字段：`type` / `status` / `created`(createdAt) / `updated`(updatedAt) / `confidence` / `source` / `tags`。

- **状态**：`active` 在用 · `pending` 待复核 · `archived` 已归档 · `superseded` 已被取代
- **置信度**：`LOW` / `MEDIUM` / `HIGH`（正文仍写中文 低/中/高，落盘时自动映射；策略状态 `已确认/已观察/假设/未知` 对应 `HIGH/MEDIUM/LOW/LOW`）
- **来源**：未标注时写 `unknown`，由 Memory Health 定位无来源结论

```python
memory.review("analytics", title, approved=True, reason="样本量达标")   # pending -> active
memory.review("analytics", title, approved=False, reason="样本量不足")  # 驳回 -> 归档并留理由
memory.supersede("insight", title, reason="已由新结论取代")             # -> superseded，reason 必填
memory.health(stale_days=90)   # 只读巡检：duplicate / conflict / stale / no_source / low_confidence / invalid_metadata
```

写入时的状态映射：Analytics 分析记录与未验证的 Insight 直接落 `pending`（等 Memory Review），已验证 Insight、实验、决策、账号、策略落 `active`。

## Agent-Reach 调研（Phase 4）

`runtime/reach_research.py` 封装 agent-reach 的三条零配置通道，把外部调研结论写进 `11-Research`：

```python
from runtime.reach_research import ReachResearch

reach = ReachResearch()
reach.fetch("agent memory layer", channel="web")     # 只读：返回截断材料 + 来源 URL，不落盘
reach.research(topic="Agent-Reach", conclusions=["多后端路由"], query="agent-reach", channel="github")
```

- 通道：`web`（Exa 搜索）、`github`（`gh search repos`，自动把 `owner/repo` 还原成仓库地址）、`page`（Jina Reader 读单页）
- **失败不写**：命令缺失、退出码非 0、通道返回限流/报错文本、抓不到任何来源 URL → `fetch` 返回 `ok=False`，`research` 抛 `RuntimeError` 且 vault 无改动
- **结论由调用方给出**：本层不生成内容、不存原文；写入的只有结论、来源 URL，frontmatter `source` 取第一个来源
- 通道报错（如 Exa 免费限流）由调用方按 agent-reach 的重试链处理，本层不自动重试

### ResearchItem（原始材料数据库）

按 PLAN 1.4：原始抓取进数据库，值得长期使用的结论才进记忆。

```python
from runtime.research_store import ResearchItem, ResearchStore

store = ResearchStore()                       # data/research.sqlite3（已 gitignore）
reach = ReachResearch(store=store)
reach.harvest("Obsidian 记忆", channel="web", topic="memory")  # 只落库，不写记忆
store.search("热层", topic="memory")           # 按关键词/主题查材料
```

| 字段 | 说明 |
| --- | --- |
| `id` / `url` | `sha1(url)[:12]`，URL 唯一键，重复抓取即更新 |
| `source` | 通道名（web / github / page） |
| `author` `timestamp` `title` | Exa 分块输出里的 Author / Published / Title |
| `content` | 材料摘要，上限 800 字符（不是全文） |
| `engagement` | 互动数据（JSON），X 接入前留空 |
| `topic` `evidence` `query` `fetched_at` | 归类、证据、触发查询、抓取时间 |

`ReachResearch.research()` 同时做两件事：材料写进 `ResearchStore`，结论写进 `11-Research`。

## Research Agent（Phase 5）

`agents/researcher.py`：`搜索 → 抓取 → 去重 → 分类 → 提取事实/观点/证据 → Topic Candidate`。

```python
from agents import ResearcherAgent

agent = ResearcherAgent()                       # 不联网构造；也可注入 reach=ReachResearch(...)、extractor=...
agent.run("obsidian agent memory", {"channel": "github", "limit": 5, "topic": "memory"})
agent.run("记忆分层", {"materials": [...]})      # 用现成材料跑，不触发网络
# -> {"summary", "details", "candidates": [TopicCandidate...], "material_count", "errors", ...}
```

`runtime/topics.py` 负责数据模型与规则：

| 环节 | 规则 |
| --- | --- |
| 去重 | 按 URL 去重；同标题的不同来源合并进同一候选 |
| 分类 | 关键词表 `CATEGORIES`（记忆系统 / AI 工具 / 内容创作 / 平台运营 / 数据增长 / 未分类） |
| 事实 | 同时命中「数字 + 计量词」的行（最多 5 条） |
| 观点 | 含建议/应该/值得等信号词的行（最多 3 条） |
| 证据 | 来源 URL + 首段摘录（最多 3 条） |
| 置信度 | 规则抽取一律 `LOW`，候选 `status` 不写记忆，等复核 |

- **候选不写记忆**：没经过复核的选题不是长期记忆；材料只进 `ResearchStore`。
- 抽取规则可由构造参数 `extractor=` 覆盖（上层模型给出更强的抽取结果时）。

## Topic Engine（Phase 6）

`runtime/topic_engine.py`：把 `TopicCandidate` 变成**带理由的选题推荐**，回答四个问题——为什么值得研究、证据是什么、是否适合当前账号、有哪些可用角度。

```python
from runtime.topic_engine import TopicEngine

TopicEngine().recommend(candidates, top_k=5)
# -> {"ok", "checked", "account", "recommendations": [TopicRecommendation...], "warnings"}
```

| 字段 | 来源 |
| --- | --- |
| `topic / sources / evidence / freshness` | Phase 5 候选 |
| `angles` | 按分类查表（记忆系统/AI 工具/内容创作/平台运营/数据增长/未分类 各 3 个角度） |
| `audience` | **只取 Account Memory 的目标受众**，没有就 `UNKNOWN` |
| `competition` | 恒为 `UNKNOWN`：没有竞争数据，不编造（接 X 数据后再算） |
| `account_fit` | `HIGH/MEDIUM/LOW/UNKNOWN`：分类关键词命中账号定位 → HIGH；选题与账号文本有二元词交集 → MEDIUM |
| `content_type` | 只输出 `X Post` / `X Thread`（Phase 9 第一阶段范围） |
| `why / blockers` | 每条推荐都带「为什么值得研究」和「缺什么、卡在哪」 |
| `score` | 证据 0–40（来源数 + 事实） + 时效 0–25（7/30/90 天窗口） + 账号契合 0–35 |

- 只读 Account Memory，不写任何笔记；没有 Account 时**全部标 UNKNOWN 并给出 warning**，不猜受众。
- 评分项可解释：每个分数都能说清来自哪一项；缺事实、缺时效、关联弱都会落进 `blockers`。

## Strategy Agent（Phase 7）

`agents/strategist.py` + `runtime/strategy.py`：把 Memory 接入 Research，回答**「这个选题为什么适合这个账号」**。

```
Research ↓ Account Memory ↓ 历史内容 ↓ 历史表现 ↓ Strategy ↓ Topic Recommendation
```

```python
from agents import StrategyAgent

StrategyAgent().run("判断这批选题", {"candidates": [...]})   # 或 {"recommendations": [...]}
# -> {"strategies": [StrategyBrief...], "recommendations", "warnings", "summary", "details"}
```

`StrategyBrief = {topic, verdict, answer, strategy_basis, history, observations, caveats, recommendation}`

| 记忆来源 | 用法 |
| --- | --- |
| Account Memory | `answer` 第一条：账号定位、受众、选题分类 |
| Strategy（当前内容策略） | 关键词命中 → `strategy_basis`；状态非 `Confirmed` → 只进 `caveats`（不当既定方向） |
| Content（历史内容） | 主题/正文 ≥2 个共同词 → `history` 重合提示，verdict 降为「需人工判断」 |
| Analytics / Insights | 只作 `observations` 引用，**不参与评分、不直接改策略**（改策略走 Memory Review） |

- `verdict` ∈ `推荐 / 需人工判断 / 不建议`：契合 HIGH 且无 blocker 才「推荐」，LOW「不建议」。
- 共同词匹配：拉丁词整词（≥3 字符，避免 `ag/ge` 子串噪声）+ 中文二字滑窗。
- 全程只读记忆，跑完笔记数量与内容不变。

## Content Object（Phase 8）

`runtime/content_object.py` + `runtime/content_store.py`：内容从想法到发布的生命周期载体，**存 SQLite**（`data/content.sqlite3`），属于生产管线数据，不是长期记忆。

```python
from runtime.content_object import ContentObject, idea_from_recommendation
from runtime.content_store import ContentStore

store = ContentStore()
obj = idea_from_recommendation(recommendation, brief)   # Topic 推荐 -> IDEA
store.save(obj)
store.fill(obj.id, {"hook": "…", "core_content": "…"})
store.transition(obj.id, "RESEARCHED")                  # 只能沿状态机走
```

- 字段（PLAN 8）：`topic / angle / audience / sources / evidence / claims / hook / coreContent / media / platformVersions / status`
- 状态机：`IDEA → RESEARCHED → DRAFT → REVIEW → APPROVED → SCHEDULED → PUBLISHED → ARCHIVED`（任意状态可 → `ARCHIVED`，`ARCHIVED` 是终态）
- **缺字段不许进阶**：进 `RESEARCHED` 要有 sources+evidence；进 `DRAFT` 要有 hook+core_content；进 `SCHEDULED/PUBLISHED` 要有 platform_versions（`REVIEW` 不强制 claims，见下）
- 跳步 / 缺字段一律 `ValueError` 且**不落库**；`fill()` 只改内容字段，改状态必须走 `transition()`
- `idea_from_recommendation()` 把事实线索放进 `claims`（待核查断言），等 `REVIEW` 逐条核查

## Content Agent（Phase 9）

`agents/content.py` + `runtime/content_draft.py`：`Topic → Research → Evidence → Outline → Draft → Fact Check → Style Check → AI味检查 → Human Review`。第一阶段只做 X Post / X Thread。

```python
from agents import ContentAgent

ContentAgent(store=…, memory=…, drafter=None).run("写 Thread", {"recommendation": rec, "brief": brief})
# -> {content, posts, checks, pending_human_review, summary, errors, next_actions}
```

| 环节 | 实现（不接 LLM key） |
| --- | --- |
| Outline | `build_outline()`：问题 → 事实(≤3) → 观点(≤2) → 角度 → 结论 |
| Draft | `draft_thread()`：首条 Hook + 大纲行 + 来源行，每条 ≤280；**可注入 `drafter=` 换更强生成器** |
| Fact Check | 断言在证据摘录里能找到出处 → `supported`，找不到 → `unverifiable`（不冒充「证伪」） |
| Style Check | 单条 ≤280、Hook 非空、Thread ≤20 条、账号「禁止内容」禁用词 |
| AI 味检查 | 命中 `首先/总之/综上所述/赋能/闭环…` 套话表即不过 |
| Human Review | 三道全过才 `DRAFT → REVIEW`；**APPROVED 永远由人来点**，Agent 不自己放行 |

- 读不到 Account Memory 时禁用词检查自动跳过（不编造禁用词）。
- 状态机拒绝（如缺必填字段）会被 Agent 转成可解释的 `errors`，状态停在原地，不崩溃。
- `REVIEW` 不强制 claims：空断言清单 = 无可核查项，`fact_check.checked == 0` 会如实显示。

## X Layer（Phase 10）

`runtime/x_adapter.py`：**所有 X API 逻辑只允许出现在这个文件**（PLAN Phase 10）。

```python
from runtime.x_adapter import XAdapter

adapter = XAdapter(backend=..., dry_run=True)
adapter.search(query, limit)      # / timeline() / mentions() / analytics(post_id)
adapter.post(text)                # 默认 dry_run：只回显，不真实发送
adapter.thread(posts)             # 逐条发送，中途失败立即停并报告已发条数
adapter.schedule(text, at)
```

| 设计 | 说明 |
| --- | --- |
| 后端可注入 | `backend` 需提供同名方法并返回 `{"ok": ...}`；**未配置时所有调用返回 `ok=False` + 明确提示**，不假装成功 |
| 默认演练 | 写操作默认 `dry_run=True`，真实发送必须显式 `dry_run=False`（对外操作由上层把关） |
| X 规则 | 单条 ≤280、Thread ≤20 条、空内容拒绝，校验在后端之前 |
| 字段归一化 | 后端返回的 `id_str/screen_name/full_text/created_at` 统一成 `url/author/text/time` |

`ReachResearch` 新增 `channel="x"`（Research X）：走 `XAdapter.search`，推文文本作为材料 title、每条推文只留自己那一行进 `ResearchStore`；未配置后端时 `fetch/harvest` 返回可解释失败。

**当前状态**：本机 X 渠道未解锁、x-mcp 未配置 → `backend` 尚未接入（安装需要 X 登录，等确认后注入 `McporterXBackend`）。

## 如何运行 demo

```bash
python -m runtime.main
```

demo 会执行 Planner、Researcher、Coder、Reviewer 四个 Agent，并生成多篇 Obsidian Markdown 笔记。

## 如何打开 Obsidian vault

用 Obsidian 打开项目内的这个目录：

```text
obsidian_vault/
```

核心目录包括：

- `01-Projects/`：项目计划和执行记录。
- `02-Skills/`：技能卡。
- `03-Concepts/`：概念卡。
- `04-Errors/`：错误记录。
- `05-Agents/`：Agent 日志和 Arbiter 报告。
- `06-Resources/GitHub-Repos/`：仓库分析。
- `08-Daily/`：每日复盘。
- `09-Account/`：账号画像（受控修改）。
- `10-Strategy/`：当前内容策略与变更原因。
- `11-Research/`：研究结论与来源。
- `12-Content/`：已产出内容的摘要与经验。
- `13-Experiments/`：实验记录。
- `14-Analytics/`：数据分析与候选 Insight。
- `15-Decisions/`：决策历史（为什么做、为什么没做）。
- `16-Agent/`：各 Agent 的经验。
- `17-Insights/`：观察、证据与置信度。
- `99-Archive/`：已归档记忆。

## 如何运行 arbiter-doctor

```bash
bash scripts/run_doctor.sh
```

如果没有安装 `arbiter-doctor`，脚本会给出安装提示，并把说明写入：

```text
obsidian_vault/05-Agents/arbiter-doctor-report.md
```

## 如何备份 vault

```bash
bash scripts/backup_vault.sh
```

备份文件会生成到：

```text
backup/obsidian_vault_日期.tar.gz
```

## 目录说明

```text
agents/              四个 Agent 的实现
runtime/             EverOS、Arbiter、Obsidian 和 demo 入口
workflows/           可复用任务流
knowledge_templates/ Obsidian 知识模板
obsidian_vault/      本地 Markdown 知识库
scripts/             doctor、备份、EverOS 启动和同步脚本
tests/               基础测试
```

## Agent 职责说明

- Planner Agent：拆解任务，输出阶段计划、文件计划、风险点和下一步命令。
- Researcher Agent：分析技术概念、仓库和 README，输出概念卡和资源卡内容。
- Coder Agent：给出代码实现建议、文件变更说明、运行命令和测试命令。
- Reviewer Agent：检查潜在 bug、安全风险、架构问题和可运行性。

## 知识库结构说明

- `00-Inbox/`：临时收集。
- `01-Projects/`：项目计划、执行记录和复盘。
- `02-Skills/`：可复用技能。
- `03-Concepts/`：技术概念。
- `04-Errors/`：错误和解决方案。
- `05-Agents/`：Agent 运行日志、预算日志和 doctor 报告。
- `06-Resources/GitHub-Repos/`：仓库调研。
- `07-Prompts/`：Prompt 卡。
- `08-Daily/`：每日复盘。
- `99-Archive/`：归档内容。

## 安全注意事项

- 不要把 API Key 写进 Markdown。
- 不要把钱包私钥、助记词写进 EverOS 或 Obsidian。
- `.env` 必须加入 `.gitignore`。
- 默认只在本机 `127.0.0.1` 使用 EverOS。
- 不要把本地 EverOS 服务直接暴露到公网。
- Codex 修改代码后必须先 review 再运行重要命令。

## 后续扩展方向

- 把 `mock_llm_call()` 替换为经过授权的真实 LLM 调用。
- 接入真实 EverOS 检索和写入接口。
- 扩展 Arbiter 预算策略和风险扫描。
- 增加更严格的敏感信息脱敏检查。
- 把高频成功流程沉淀成可复用 Agent case 或 Skill。
