# 太阳/月亮星座 MVP 验收

分支：`mingli-split`；实现基线：`6c0b229`。执行已批准计划的第 1–3 步。

## 实现

- `engines/birth_time.py`：共享整数日期、有限经纬度、IANA 时区和 DST 校验。
  重复时刻使用显式 `fold`；日期精度覆盖真实民用日的 23/25 小时和跳日情况。
- `engines/western/`：独立 provider 契约，采用 MIT 的 Astronomy Engine 2.1.19，
  输出回归黄道地心日月黄经、落座、候选、版本、坐标系和时间模型。
- `runtime/input_models.py`：HTTP/MCP 共用严格输入契约，拒绝非法整数、未知字段和非有限数值。
- 新增 `POST /api/western/chart` 与 MCP `western_chart`；保留现有八字、紫微和事件窗口操作。
- Web 补充分钟、时区、地点、时间精度、DST fold 与太阳/月亮卡片。
  仅日期输入不生成虚构时间；其他需要出生小时的操作会给出明确提示。
- 查询年份增加上界；事件窗口菜单改为后端实际支持的六冲、六合、六害、相破。
- NaN/Infinity 输入原先会使校验错误的 JSON 序列化失败并返回 500，现返回可序列化的 422。
- 新增依赖已精确固定版本；文档见 `docs/western-zodiac.md`。

## 实际验证

执行目录：`/workspace/agent-knowledge-os`。

| 检查 | 结果 |
| --- | --- |
| `.venv/bin/ruff check .` | All checks passed |
| `.venv/bin/python -m pip check` | No broken requirements found |
| `.venv/bin/python -m pytest -q -ra` | 429 passed, 1 warning；5.75 秒 |
| `git diff --check` | 通过 |
| 实际 Uvicorn HTTP 离线检查 | 65 次检查通过；禁止非 loopback 连接与外部 DNS，实际外部请求为 0 |
| Chromium/Playwright | 正常日月落座、仅日期候选、缺出生时间提示、DST 拒绝与 fold、空数字字段、390px 手机布局通过；页面异常和外部请求均为 0 |
| MCP stdio 子进程 | 握手、工具列表、原有排盘与新增 western_chart 通过，包含在 pytest 中 |

独立参考使用 PySwissEph 2.10.3.2 的 Moshier 算法生成 17 个固定样本。
在相同 TT 时刻下，太阳最大差异 **0.01984 角分**，月亮最大差异 **0.03588 角分**，
均低于 1 角分阈值；此结果仅描述选定样本，不是整个年代范围的误差保证。
参考生成库位于 checkout 外，不是生产依赖，回归测试直接读取固定 JSON。

比对初期发现两套库的 2100 年默认 ΔT 估计相差约 109 秒，导致月亮相差约 1.04 角分。
位置比较随后固定相同 TT 时刻，未放宽 1 角分阈值；输出和文档明确声明时间模型以及未来 ΔT 限制。

唯一测试警告为既有 Starlette TestClient 使用 httpx 的弃用提示；未跳过或禁用测试。

## 本期边界与后续

- 西方星座首期接受 1900–2100 年，使用回归黄道；不是 IAU 天文学星座边界。
- 仅日期输入不接入当前要求出生小时的记忆 API；分钟精度共用出生档案字段。
- 上升、宫位、相位、行运、合盘和跨体系解释报告属于后续阶段，尚未实现。
- Kerykeion/Flatlib 仅作调研候选，未纳入生产代码或依赖。
