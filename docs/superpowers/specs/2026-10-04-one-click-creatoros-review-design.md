# CreatorOS 一键启动与 Review 面板设计

## 目标

把当前本地静态 Dashboard、Review API、内容审核和启动流程整合成一个可重复使用的本地工作台：

```text
一键启动
  ↓
静态 Dashboard + 本地 Review API
  ↓
查看研究 / 选题 / 内容 / 发布 / 数据 / 记忆
  ↓
在 Review 页批准或要求修改
  ↓
发布仍需独立人工确认
```

系统默认不联网、不调用模型、不自动发帖、不读取浏览器凭据。

## 使用方式

启动：

```bash
./scripts/start_creatoros.sh
```

停止：

```bash
./scripts/stop_creatoros.sh
```

今日内容生成仍使用显式命令：

```bash
./scripts/create_today_review.sh
```

一键启动只负责启动本地工作台，不隐含外部请求或付费模型调用。

## 组件设计

### 启动脚本

新增 `scripts/start_creatoros.sh` 和 `scripts/stop_creatoros.sh`。

启动脚本职责：

- 通过脚本自身位置定位项目根目录；
- 检查 `.venv/bin/python` 是否存在；
- 检查 Review API 端口 `8765` 是否可用；
- 生成最新 `data/dashboard.html`；
- 启动 `scripts/review_server.py`，监听 `127.0.0.1:8765`；
- 将 PID 写入 `data/review-server.pid`；
- 将服务日志写入 `data/review-server.log`；
- 输出 Dashboard 路径和 Review API 地址；
- 如果服务已由本次 PID 文件启动，重复执行时不再启动第二个服务。

停止脚本职责：

- 读取并验证 PID 文件；
- 只停止该 PID 文件对应的进程；
- 清理 PID 文件；
- 不杀同端口的未知进程；
- 服务已退出时正常返回。

运行文件全部位于 `data/`，由现有 Git 忽略规则保护。

### Dashboard

继续使用现有单文件 HTML 生成器：

```text
runtime/dashboard.py
scripts/build_dashboard.py
data/dashboard.html
```

Dashboard 保持静态数据展示职责，页面包括：

- Dashboard
- Research
- Topics
- Content
- Calendar
- Review
- Publish
- Analytics
- Memory
- Accounts
- Settings

不把 SQLite 写逻辑放进浏览器。Review 页面通过同源或明确的本地 API 地址调用 Review API。

### Review API

继续使用 Python 标准库 `http.server`，不引入 Web 框架。

监听地址固定为 loopback：

```text
127.0.0.1:8765
```

接口：

```text
GET  /api/review
GET  /api/review/<content_id>
POST /api/review/<content_id>/approve
POST /api/review/<content_id>/changes
OPTIONS /api/review/<content_id>/*
```

接口复用：

- `ContentStore`
- `ResearchStore`
- `human_review.build_packet()`
- `human_review.approve()`
- `human_review.request_changes()`

接口约束：

- 只允许 `REVIEW` 状态批准或驳回；
- 驳回必须带非空修改说明；
- 不支持发布操作；
- 不支持证据状态升级；
- API 错误返回 JSON，不吞异常；
- 静态 Dashboard 需要的 CORS 响应头继续保留；
- SQLite 连接支持 Review API 的线程模型。

### Review 页面

待审核内容详情必须展示：

- 内容 ID 和状态；
- 标题候选；
- 主题、角度、受众；
- `evidence_status`；
- `content_source`；
- 原始研究材料；
- 来源 URL；
- Claims；
- Evidence 摘录；
- 结构化 `platform_posts`，每条帖子单独展示；
- AI 建议；
- 历史审核记录。

操作：

- `批准`：调用 `/approve`，成功后关闭详情并提示状态；
- `要求修改`：要求输入修改说明，调用 `/changes`，成功后关闭详情并提示状态；
- `关闭`：只关闭抽屉，不修改数据。

页面调用失败时显示明确错误，不伪装成审核成功。

## 今日内容命令

新增 `scripts/create_today_review.sh`，只负责调用现有 Python 入口：

```text
AIHOT 精选快照
  ↓
ResearchStore
  ↓
TopicEngine 账号契合排序
  ↓
ContentAgent
  ↓
REVIEW 草稿
```

它不自动批准、不自动发帖。外部请求和模型调用必须由显式命令或用户操作触发。

## 数据与进程安全

- 启动脚本不读取 `.env`、Cookie、Token 或浏览器存储；
- Review API 只监听 `127.0.0.1`；
- PID 文件停止前验证 PID 对应命令属于本项目 Review 服务；
- 不使用宽范围 `pkill`；
- 不能确认归属的进程不停止；
- Review API 的 SQLite 连接在服务退出时关闭；
- Dashboard 继续不加载 CDN、图片、外部脚本或远程资源。

## 测试计划

### 单元测试

- Review API 列表、详情、批准、驳回和非法状态；
- CORS 和 OPTIONS；
- 结构化帖子在审核包中不被普通换行拆散；
- 启动脚本的路径、PID 和重复启动逻辑通过 shell 级测试或可测试 helper 验证。

### 集成验证

```bash
./scripts/start_creatoros.sh
curl http://127.0.0.1:8765/api/review
python scripts/build_dashboard.py
./scripts/stop_creatoros.sh
```

### 完成检查

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m mypy .
git diff --check
```

## 不做

- 不引入 FastAPI、Flask 或前端框架；
- 不引入新的数据库；
- 不做用户登录系统；
- 不从 Dashboard 自动发布；
- 不自动读取浏览器 Cookie；
- 不把 `Mimo` 或其他模型调用绑定到一键启动；
- 不接入更多平台发布；
- 不修改 `knowledge/` 和既有 `.gitignore` 外部改动。
