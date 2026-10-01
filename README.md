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
| `facts` | Phase 5 的事实线索，直接进 Phase 9 Content Agent 的 `claims`（否则事实核查永远空转） |
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
| 默认后端探测 | `default_x_adapter()`：优先 OpenCLI（浏览器登录态，`opencli` 在 PATH 即可用），其次 `~/.agent-reach/config.yaml` 的 twitter-cli 凭据；都没有则返回未配置 adapter。`ReachResearch` 与 `XWorkflow` 默认走它 |
| 默认演练 | 写操作默认 `dry_run=True`，真实发送必须显式 `dry_run=False`（对外操作由上层把关） |
| X 规则 | 单条 ≤280、Thread ≤20 条、空内容拒绝，校验在后端之前 |
| 字段归一化 | 后端返回的 `id_str/screen_name/full_text/created_at` 统一成 `url/author/text/time` |

`ReachResearch` 新增 `channel="x"`（Research X）：走 `XAdapter.search`，推文文本作为材料 title、每条推文只留自己那一行进 `ResearchStore`；未配置后端时 `fetch/harvest` 返回可解释失败。

**当前状态（X 真实跑通）**：`default_x_adapter()` 探测到 `opencli`（1.8.8）→ `OpenCliXBackend`，复用 Chrome 里已登录的 x.com 会话（`AZEN_BTC`）。真实验证过的读路径：`search`（`ReachResearch.fetch/harvest channel="x"`，3 条入库 `data/research.sqlite3`）、`timeline`、`mentions`（whoami → `@自己` 搜索）、`analytics`（`twitter tweets` 找到自己最近推文并给指标）。备选 `TwitterCliXBackend`（twitter-cli + cookie 凭据，`agent-reach configure twitter-cookies`）已实现并在测试覆盖，OpenCLI 不可用时自动降级。代理走 `~/.agent-reach/config.yaml` 的 `proxy`（`127.0.0.1:7890`，twitter-cli 链路用；OpenCLI 走浏览器自己的网络栈）。

## X 内容工作流（Phase 11）

`agents/x_workflow.py`：`XWorkflow` 提供三条工作流和一个受人审闸门约束的发布出口。

```python
from agents import XWorkflow

wf = XWorkflow(reach=…, store=…, memory=…, x=XAdapter(backend=…), content_agent=…)
wf.url_to_draft("https://example.com/post")     # 文章 URL → 抓取 → 摘要/核心观点 → Thread 草稿
wf.topic_to_thread(candidate, brief=None)       # Topic → Thread（复用 Content Agent 三道检查）
wf.research_to_post("obsidian agent memory 生态") # 11-Research 结论 → 原帖草稿
wf.publish(content_id)                          # 只发 APPROVED；走 XAdapter.thread
```

- 摘要/事实/观点沿用 `topics.extract` 规则，**证据摘录会覆盖事实行**（否则事实核查永远「无出处」）。
- `publish()`：状态非 `APPROVED` → 拒绝并说明「未通过人审」；X 发送失败 → 状态保持不变；成功 → `APPROVED → SCHEDULED → PUBLISHED`，并记录 `platform_versions = {"X": "Thread"}`。
- 走 `XAdapter`，不绕过（X API 不散落到工作流里）。
- **已知问题（Phase 15 修）**：OpenCLI `post` 偶发 `TIMEOUT` 但实际已发出（首条真实推文 `2104696280136221102` 即如此，靠 `tweets` 列表人工对账补状态）。工作流现在如实报失败、状态停在 APPROVED——**不要盲目重试，先查 `opencli twitter tweets --limit 3` 是否已存在同文**；自动对账（TIMEOUT → 查列表 → 命中即补 PUBLISHED）归 Phase 15 PublishJob 的 attempts/结果判定。

## Human Review（Phase 12）

`runtime/human_review.py`：发布前的强制人审。

```python
from runtime.human_review import build_packet, render, approve, request_changes

packet = build_packet(store, content_id, research_store=…)   # 原始研究/来源/AI 生成内容/Claims/Evidence/AI 建议/修改记录
print(render(packet))                                         # 审核界面（终端文本版）
approve(store, content_id, reviewer="admin", note="…")        # REVIEW → APPROVED，记录审核人
request_changes(store, content_id, reviewer="admin", note="Hook 太平")  # REVIEW → DRAFT，必须写要改什么
```

- 只有 `REVIEW` 状态可审批；驳回必须写明要改什么，否则作者只能靠猜。
- `ContentObject` 新增 `ai_suggestions`（创建时由 Topic/Strategy 的理由生成）与 `review_notes`（只增不改的审核记录）。
- 配套状态链：`DRAFT → REVIEW → APPROVED → SCHEDULED → PUBLISHED`（与 PLAN 12 一致）。

## 国内平台层（Phase 13）

`runtime/platform_adapter.py`：六个国内平台的统一适配契约（小红书 → 抖音 → B站 → 公众号 → 微博 → 视频号）。

```python
from runtime.platform_adapter import get_adapter

adapter = get_adapter("xiaohongshu")            # douyin / bilibili / wechat_mp / weibo / channels
draft = adapter.create_draft({"title": "…", "body": "…", "tags": ["AI"], "media": [], "content_id": "…"})
adapter.validate(draft)                          # {"ok": …, "errors": […]}；标题/正文/标签字数上限按平台
adapter.publish(draft)                           # 默认 dry_run：回显预览，不外发
adapter.publish(draft, dry_run=False)            # 真实发布：必须有 backend，没配就如实 ok=False
adapter.schedule(draft, "2026-10-01 09:00")      # 同样默认演练
adapter.get_status(draft.id)                     # 平台侧状态（需 backend）
adapter.get_analytics(draft.id)                  # 平台侧数据（需 backend）
```

| 设计 | 说明 |
| --- | --- |
| PLAN 接口映射 | `createDraft/create_draft`、`validate`、`publish`、`schedule`、`getStatus/get_status`、`getAnalytics/get_analytics`（Python 侧统一 snake_case，与 `XAdapter` 一致） |
| 本地校验 | 标题/正文/标签上限是平台规格常量（`SPECS`，可被 `limits=` 覆盖）；视频平台（抖音/B站/视频号）必须有媒体，公众号/小红书/B站/视频号必须有标题 |
| backend 契约 | 与 `XAdapter` 同一套：同名方法返回 `{"ok": …}`；**没配 backend 时真实 publish/schedule/getStatus/getAnalytics 返回 `ok=False` + 平台级提示**（各平台提示写明当前可用的接入方式），不假装成功 |
| 演练闸门 | `dry_run=True` 是所有写操作默认值；演练先过 `validate`，失败连 backend 都不碰 |
| 后端现状 | 六平台都还没接真实写后端：小红书可走 OpenCLI/xhs-cli（写未验证）、B站 bili-cli（投稿未接）、公众号/微博需开放平台凭据、视频号只有手工发布 |

## 内容格式化（Phase 14）

`runtime/canonical_post.py` + `runtime/platform_formatter.py`：`CanonicalPost → Platform Formatter → FormattedPayload`。同一个内容对象可以喂给任意平台，**不重新研究内容、不复制业务逻辑**。

```python
from runtime.canonical_post import CanonicalPost
from runtime.platform_formatter import get_formatter

post = CanonicalPost(title="…", body="…", tags=["AI"], media=["clip.mp4"], content_id="c1")
formatted = get_formatter("xiaohongshu").format(post)   # douyin / bilibili / wechat_mp / weibo / channels / x
formatted.payload      # 渲染后的平台字段形状（如小红书 {title, body, hashtags}，X {posts: [thread…]}）
formatted.valid        # 契约校验是否通过（与 Phase 13 SPECS 同一套规则，共享 check_contract）
formatted.errors       # 校验失败原因（超字数、缺标题、视频平台缺媒体）
formatted.warnings     # 平台格式建议（缺配图、少于 N 字等），只提示不拦截
formatted.metadata     # content_id / label / limits / dry_run / preview
formatted.fingerprint  # sha256(platform + canonical json(payload))，跨进程稳定
formatted.preview()    # 人类可读预览（审核界面）
```

| 设计 | 说明 |
| --- | --- |
| 平台契约唯一来源 | 字数上限/标题要求/媒体要求全部来自 `platform_adapter.SPECS` + 共享 `check_contract()`，Formatter 不允许自己另立规则 |
| X Thread | 按 280 权重（中文 2/英文 1）贪心拆条，复用 `XAdapter` 的 `X_POST_LIMIT/X_THREAD_LIMIT`；>20 条报错 |
| 平台特有规则 | 只在各 Formatter 的 `render()`：小红书/抖音/微博标签写进正文、B站/视频号标签走 `tags` 字段、B站/视频号/抖音必须有视频 |
| 纯函数 | `format()` 无任何 I/O，默认 `dry_run=True`；本层不存在平台写操作，写操作只在 Phase 15 的 `PublishAdapter` |
| 指纹 | 内容变/平台变 → 指纹变；同内容+同平台 → 指纹恒定，是 Phase 15 幂等键的输入 |

## 发布队列（Phase 15）

`runtime/publish_queue.py` + `runtime/retry_policy.py` + `runtime/publish_adapters.py` + `runtime/publish_worker.py`：平台无关的发布基础设施。**六个国内平台目前全部 CONTRACT_ONLY，不接真实写 API、不伪造成功。**

```python
from runtime.publish_queue import PublishJobStore
from runtime.publish_adapters import get_publish_adapter      # 六平台 → ContractOnlyAdapter
from runtime.publish_worker import PublishWorker, Reconciler

store = PublishJobStore("data/publish.sqlite3")
worker = PublishWorker(store, {"xiaohongshu": get_publish_adapter("xiaohongshu")}, builder)
job, created = store.enqueue(content_id, "xiaohongshu", fingerprint=formatted.fingerprint)  # 幂等
worker.run_once()                    # QUEUED → RUNNING → 成功/失败/超时
Reconciler(store, adapters, builder).reconcile(job.id)   # 只对 TIMEOUT_UNVERIFIED/NEEDS_REVIEW 生效
```

**两个状态机严格分离**（Workflow 是 `ContentObject` 的 `DRAFT→REVIEW→APPROVED`，发布失败绝不改它）：

```
PublishJob：QUEUED → RUNNING → SUCCEEDED
                          ↘ FAILED
                          ↘ TIMEOUT_UNVERIFIED → RECONCILING → SUCCEEDED / FAILED / NEEDS_REVIEW
            RETRYING → RUNNING（重试=新 attempt，attempt_no 递增，不覆盖旧记录）
```

**Retry 矩阵**（`runtime/retry_policy.py`，重试必须产生新 `PublishJobAttempt`）：

| 错误类 | 重试 |
| --- | --- |
| 参数类 4xx / 鉴权 / 内容违规 / 重复内容 | 否 |
| **TIMEOUT** | **否，必须先 reconcile**（状态机里没有 `TIMEOUT_UNVERIFIED → RETRYING` 这条边） |
| NOT_IMPLEMENTED（contract-only 平台）/ 配置错误 / 不明确失败 | 否 |
| 明确网络连接失败 / 5xx | 是（延迟进 `scheduled_at`） |
| rate limit | 是，按 `retry_after`；没有就按平台默认 |

**TIMEOUT 对账**（独立流程，不自动触发）：用 `request_fingerprint` / `provider_request_id` / 发布时间窗 / 内容摘要查平台记录——命中 → `RECONCILED_SUCCESS` + Job `SUCCEEDED`；确认不存在 → `RECONCILED_FAILED` + Job `FAILED`；无法确定 → `NEEDS_REVIEW`（可人工重跑对账，**禁止自动 retry**）。全程 Workflow 保持 `APPROVED`。

**幂等**：`idempotency_key = sha256(content_id|platform|fingerprint)` 加 UNIQUE 约束，worker 重启后重复入队不会产生第二个 job；已认领（RUNNING）的 job 也不会被重启后的 worker 重复执行。

**已知边界**：六平台 `PublishAdapter` 是 Contract-Only 实现——`validate` 走真实契约校验，`publish/reconcile` 返回 `NOT_IMPLEMENTED`（Job 会诚实落到 FAILED，不重试）；测试与端到端流程用 `MockPublishAdapter`（可编排超时/5xx/「超时但实际已发出」等真实世界剧本）。

**发布日志（PLAN Phase 15「所有发布行为必须记录日志」）**：`PublishWorker.run_once()` 与 `Reconciler.reconcile()` 每次执行都往 `data/publish_log.jsonl` 追加一行（`kind=publish|reconcile`、job/content/platform、attempt_no、status、ok、error_class、post_id）。日志写失败不冒充发布失败——结果照常如实返回。测试里用 `log_path=` 指到临时目录。

## 表现数据（Phase 16）

`runtime/post_analytics.py` + `runtime/analytics_store.py` + `runtime/analytics_collector.py`：发布之后收集表现指标。**只存拿到的数：backend 缺的字段不填、算不出来的率就是 `None`、采集失败不写空快照。**

```python
from runtime.analytics_collector import AnalyticsCollector
from runtime.analytics_store import AnalyticsStore
from runtime.publish_queue import PublishJobStore
from runtime.x_adapter import default_x_adapter

store = AnalyticsStore("data/analytics.sqlite3")
collector = AnalyticsCollector(store, x=default_x_adapter(),
                               publish_store=PublishJobStore("data/publish.sqlite3"))

collector.collect("2104696280136221102", content_id="c1", content_type="thread")  # 单条
collector.collect_content("c1")        # 从 Phase 15 成功 job 的 attempt 取 published_post_id
collector.collect_published(limit=20)  # 批量：最近成功发布的 job（Phase 15 → 16 衔接）
store.recent()                         # 每 post 最新一条快照，给 Phase 17 模式识别用
```

PLAN 口径的采集项：`views / likes / comments / reposts / bookmarks / followers / engagement / publish_time / content_type`。

| 设计 | 说明 |
| --- | --- |
| 字段归一 | backend 字段差异在 `normalize_metrics()` 抹平（`replies`→`comments`、`retweets`→`reposts`、`impression_count`→`views`）；解析不了的值丢弃，不猜 |
| 互动率 | `（likes+comments+reposts+bookmarks）/ views`；views 缺失或为 0 → `None`（不算也不编）；存储不四舍五入，格式化留给展示层 |
| 转发归属 | `is_retweet=True` → `attributed=False`：转发的互动数属于原作者，默认查询（`history/latest/by_content/recent`）自动排除，原始数仍留档可回溯 |
| 快照不覆盖 | 同一 post 多次采集 = 多行（按 `collected_at` 排序），能看趋势；`recent()` 每 post 去重到最新一条 |
| 发布记录对齐 | 采集来源优先取 Phase 15 `SUCCEEDED` job 的 `attempt.published_post_id`，保证「发布 ↔ 表现」对得上；没有发布记录时如实报 `ok=False` |
| 诚实降级 | 六平台 `CONTRACT_ONLY` → `error_code=NOT_IMPLEMENTED`；X 后端未配置 → 明确失败 |

**已知边界**：六平台还没有真实指标读 API，`getAnalytics()` 仍是契约占位；X 的 `analytics` 走 `OpenCliXBackend` / `TwitterCliXBackend`（会带上 `is_retweet` 与 `publish_time` 供归属判定）。本层只负责收数和落盘，**不做任何策略解释**——那是 Phase 17 Analytics Agent 的事。

## Analytics Agent（Phase 17）

`runtime/analytics_agent.py` + `agents/analytics.py`：把表现数据变成「候选洞察 + 待确认的策略候选」。**只分析、只提案，不修改任何策略。**

```python
from agents import AnalyticsAgent
from runtime.analytics_store import AnalyticsStore
from runtime.memory_api import MemoryAPI

agent = AnalyticsAgent(memory=MemoryAPI(), store=AnalyticsStore("data/analytics.sqlite3"))
result = agent.run("分析最近内容表现", {"limit": 50})   # write_memory=False 可只出报告

result["patterns"]             # 分组事实（content_type）：样本量、平均互动率、采集窗口
result["insights"]             # 候选洞察：statement / confidence / evidence / blockers / ready
result["strategy_candidates"]  # status="PROPOSED"、applied=False
result["memory_writes"]        # 只写 pending「观察」
```

流程（PLAN Phase 17）与闸门：

```
Analytics → Pattern Detection → Insight Candidate → Evidence Check → Memory → Strategy Candidate
   ↑ 只算事实      ↑ 观察式陈述（带样本量与窗口）    ↑ 不过就只报告原因：不写记忆、不产候选
```

| 边界 | 说明 |
| --- | --- |
| 不改策略 | 策略侧只产出 `StrategyCandidate(status="PROPOSED", applied=False)`；本层没有任何写 Strategy 的方法，改策略必须人工 `memory.update("strategy", ...)` + `recordDecision` 写清变更原因 |
| 说事实不说指令 | 陈述形如「最近 6 条内容里，「thread」类 3 条平均互动率 10.00%，其余可比类型 2.00%（差 +8.00%）」，**不写**「以后全做 thread」 |
| 证据闸门 | 有 views 的样本 < 3、缺少对比组、低于其余类型平均、`content_type` 未标注、无可回溯 `post_id` → `ready=False`，报告里写明拦下原因 |
| 置信度与入库 | 样本 ≥10 才给「中」，否则「低」，**永远不产生「高」**；写入记忆的是 `status=观察`（frontmatter `pending`），要走 Memory Review 才能升级为已验证 Insight |
| 只看自己内容 | 转发快照（`attributed=False`）由 `AnalyticsStore.recent()` 排除；同一 post 只取最新一条快照 |
| 分组维度 | 当前只按 `content_type`：六平台指标读 API 还没接，按平台分组必然只有一类，没有参照 |

**已知边界**：洞察质量受制于 Phase 16 的数据量——没有真实发布与采集就没有候选；分组维度将来接入 topic / 平台后需要重新评估样本门槛。

## 核心闭环（Phase 18）

`agents/feedback_loop.py`：把 Phases 5→17 串成一圈。**每个阶段要么真跑了、要么被人审闸门挡住、要么如实说缺什么，绝不把没跑的阶段写成成功。**

```python
from agents import FeedbackLoop

loop = FeedbackLoop(memory=…, analytics_store=…, content_agent=…, collector=…, worker=…)
result = loop.run("本轮闭环", {"materials": [...]})      # 也可传 {"recommendations": [...]} 跳过调研
result["steps"]          # PLAN 顺序：research → strategy → content → publish → analytics → insight → memory → strategy
result["counts"]         # {"ran": …, "gated": …, "skipped": …, "failed": …}
result["next_actions"]   # 人审 / 复核 / 策略候选 三条闸门提示
loop.review_insight(title, approved=True, reason="样本量达标")   # Memory Review 闸门
```

| 阶段结果 | 含义 |
| --- | --- |
| `ran` | 真跑了，`data` 里有结果 |
| `gated` | 有输入但被闸门挡住（内容停在 REVIEW、发布等人审） |
| `skipped` | 缺输入或缺能力，`summary` 写清缺什么（如「调研要联网，本轮不自动发起」） |
| `failed` | 阶段异常，如实报错，`result["ok"]=False` |

- **圈是真闭合**：这轮 Analytics Agent 写进记忆的观察，会在收尾的 `strategy` 阶段被 `StrategyAgent.memory_context()` 读回来（`feedback.data.insight_notes`），下一轮策略判断直接拿它当输入。
- **人审闸门原样保留**：Content 最多到 REVIEW；Publish 遇到 IDEA/RESEARCHED/DRAFT/REVIEW 直接 `gated`；洞察写的是 pending 观察；策略候选永远 `PROPOSED`；`review_insight(approved=False)` 会把观察归档。
- **本层不写 Strategy**：只读 `memory_context()`；改策略必须人工 `memory.update("strategy", …)` + `recordDecision`。

**本阶段顺手修掉的两个闭环断点**：

1. `TopicEngine` 的推荐丢掉了 `facts`，`ContentAgent` 的 `fact_check` 在真实链路里永远空转；现在 `TopicRecommendation` 携带 `facts`，断言能回到证据摘录（有回归测试）。
2. `CreatorMemoryLayer.archive()` 手工拼文件名，标题含 `:`（如 Phase 17 的 `content_type:thread`）时写得进去却找不到文件，**驳回复核直接 `FileNotFoundError`**；现在统一走 `note_path()` 的文件名清洗。

## 仪表盘（Phase 19）

`runtime/dashboard.py` + `scripts/build_dashboard.py`：把各 store 与长期记忆聚合成**一页本地 HTML**（11 个页面，只读、不联网）。

```bash
python scripts/build_dashboard.py                 # → data/dashboard.html（双击打开）
python scripts/build_dashboard.py --out /tmp/dash.html --limit 50
```

```python
from runtime.dashboard import collect, render, write

data = collect(limit=30)        # 11 个页面的 section（columns + rows + note）
html = render(data)             # 单文件 HTML，无任何外部资源
write("/tmp/dash.html", data)
```

| 页面 | 数据来源 |
| --- | --- |
| Dashboard | 首页九块：今日研究 / 热点 / 推荐选题 / 草稿 / 待审核 / 排期 / 最近发布 / 数据 / AI Insight |
| Research | `ResearchStore`（Phase 4 抓取材料） |
| Topics | 本地 `TopicEngine`（材料 → 候选 → 推荐 + 理由/阻塞） |
| Content / Review | `ContentStore`（状态链、断言与证据计数、人审入口提示） |
| Calendar / Publish | `PublishJobStore`（排期、attempts、post_id）+ `data/publish_log.jsonl` |
| Analytics | `AnalyticsStore`（采集概览 + 最近快照） |
| Memory / Accounts | `MemoryAPI`（分类计数、Memory Health、账号画像、当前策略） |
| Settings | 本地路径 + 七平台能力现状（X 真实读写，其余 CONTRACT_ONLY） |

- **只读**：`collect()` 不写数据、不写记忆、不跑发布；渲染时所有值都过 `html.escape`——研究标题里带 `<script>` 也只会显示成文本。
- **无外部资源**：没有 CDN、没有 `fetch`，页面里唯一的 `<script>` 只做侧栏切页。
- **诚实空态**：没数据的 section 显示「暂无数据」；来源没有互动数字时热点区明说「不编造热度」。

## Memory Dashboard（Phase 20）

`runtime/memory_dashboard.py`：记忆系统最终该拥有的 **7 个视图**，接在 Phase 19 仪表盘的 **Memory 页**里（同一份 HTML）。

```python
from runtime.memory_dashboard import collect, VIEWS

sections = collect(memory)        # 7 个 section，与 Phase 19 dashboard 同构（title/columns/rows/note/count）
```

| 视图 | 回答的问题 | 数据来源 |
| --- | --- | --- |
| Account Memory | 账号现在是谁 | `memory.get("account")` |
| Strategy Memory | 现在采取什么策略 | `memory.get("strategy")`（只读，改策略必须人工） |
| Learned Patterns | 已经观察到什么 | `17-Insights`：主题 / 观察 / 状态 / 置信度，`pending` 明确标注「未经复核」 |
| Experiments | 正在验证什么 | `13-Experiments`：编号 / 假设 / 预期结果 / 结论 / 状态 |
| Decisions | 过去为什么这样决定 | `15-Decisions`：日期 / 事项 / 决策 / 原因 |
| Agent Knowledge | Agent 学到了什么 | `16-Agent`：Agent / 经验 |
| Memory Health | 记忆体检 | `memory.health()` 六类问题（重复 / 冲突 / 过时 / 无来源 / 低置信度 / 元数据非法）+ 代表文件 |

- **只读**：不写记忆、不改状态、不替人复核；没有数据的视图 rows 为空，页面显示「暂无数据」，体检计数为空库如实显示 0。
- **Accounts 页改为「平台账号」**：各平台能力（X 真实读写 / 六平台 CONTRACT_ONLY）+ 发过内容数 + 发布作业数；账号画像与策略不再重复，统一在 Memory 页前两个视图。

## 自动化 Agent（Phase 21）

PLAN 的每日流程 `09:00 Research → Topic → Strategy → Content → Human Review → Publisher → Analytics → Memory → 第二天继续`，入口是 `scripts/run_daily.py`（定时交给 cron/launchd，本项目不内置常驻进程）。

```bash
python scripts/run_daily.py                     # 默认全本地：不联网、不外发、不采集
python scripts/run_daily.py --materials m.json  # 用本地材料调研（不联网）
python scripts/run_daily.py --research github   # 显式允许联网调研
python scripts/run_daily.py --topic "选题名"     # 人工指定今天做哪题（无「推荐」结论时）
python scripts/run_daily.py --publish-x --send  # 两步开关：真发已过审的 X 内容
python scripts/run_daily.py --collect           # 显式跑 X 指标采集
```

- **`agents/daily.py` 的 `DailyPipeline.run()`**：跑一轮 `FeedbackLoop`，交回 `{ok, date, loop, todo, notes, log_path, record}`；每轮追加一条 `data/daily_runs.jsonl`（时间 / 八阶段状态 / 待办数 / 耗时），第二天接着看。
- **三件对外的事各有独立开关**：联网研究 `research`、X 发布 `publish_x`（必须再加 `send` 才 `dry_run=False` 真发，否则只留一条「演练位」提示）、指标采集 `collect`；默认全关，关掉时在 `notes` 写清为什么没跑。
- **发布阶段看存量**（`FeedbackLoop._publish` 扩展）：先处理「已过审待发布」的内容——注入了 `x_workflow`/`worker` 才发，没注入就如实 `skipped` 并把待发布条数写进 todo；今天新内容仍被 Phase 12 人审拦住时是 `gated`。
- **verdict 闸门保留**：策略结论「需人工判断 / 不建议」不自动起草，skip 消息列出每题结论；`--topic` 是人工拍板指定选题，绕开 verdict 但**绕不开人审**（仍停在 REVIEW）。
- **运行结束打印「今天必须人做的事」**：人审命令、待复核观察、PROPOSED 策略候选、发布队列、失败阶段。

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
