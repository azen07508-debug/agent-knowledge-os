# 离线西方星盘与跨体系解释

使用 Astronomy Engine **2.1.19**（MIT），作为独立的可替换 provider。
八字、紫微计算保持各自的模型和历法策略；西方日月位置不应用八字真太阳时修正。
当前提供日月、八颗额外行星、上升、整宫制/等宫制及五类主要相位。
跨体系接口另提供有事实依据的固定象征解读，不含合盘或运势评分。

## 输入和运行

在现有 checkout `/workspace/agent-knowledge-os` 的 `mingli-split` 分支开发，不需要新 worktree。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt httpx
python -m uvicorn api.server:app --host 127.0.0.1 --port 8000
```

`POST /api/western/chart` 的分钟精度示例：

```json
{
  "year": 1990,
  "month": 2,
  "day": 1,
  "hour": 12,
  "minute": 0,
  "timezone": "Asia/Shanghai",
  "longitude": 121.5,
  "latitude": 31.2
}
```

该时刻为 `1990-02-01T04:00:00+00:00`：太阳水瓶座、月亮白羊座。
经纬度可选；地心位置不受地点影响，但上升与宫位必须提供准确出生时刻和经纬度。
可选 `house_system`：`whole_sign`（默认整宫制）或 `equal`（等宫制），不支持 Placidus。
时区默认 `Asia/Shanghai`，其他出生地应显式传入对应的 IANA 时区。

仅知道出生日期时省略 `hour`（也可以传 `null`），不填写 `minute` 或 `fold`：

```json
{"year": 2024, "month": 3, "day": 20, "timezone": "UTC"}
```

返回 `chart.time_precision="day"`、`instant_utc=null` 和当地民用日对应的 UTC 半开区间。
太阳跨越双鱼/白羊交界，`sun.sign=null`，`sun.possible_signs` 保留两个候选。
未知时间不返回虚构的黄经或星座内度数；即便某个星座整日稳定，也不会补造出生时刻。
按半小时及区间结束前一瞬取样；日月不会在相邻样本之间跨过一个完整 30° 星座。

只知道日期时，Web 的八字、紫微和事件窗口按钮会提示需要出生时间。
Web 在“命盘 → 完整星盘”展示日月卡、上升、行星、宫位与相位。
城市选项填入近似市中心坐标及对应时区；可手动改成准确经纬度。原始数据默认折叠。

## 时区与边界

- 公历日期和时间必须使用整数；不接受布尔值、浮点整数或数字字符串。
- 民用时间先按 IANA 时区换算为 UTC，再计算天文位置。经纬度必须是有限数值。
- DST 或历史时区变更产生的不存在时刻返回 422。
- 重复时刻必须显式选择 `fold=0`（前一次）或 `fold=1`（后一次）。
  例如 `America/New_York` 的 `2024-11-03 01:30` 对应 UTC `05:30` 或 `06:30`。
- 日期精度覆盖真实民用日，包括 DST 的 23/25 小时日、午夜跳时和整日跳过。
- 首期西方星座接受 **1900–2100** 年；事件窗口查询为 **1–9997** 年，以保留计算跨年节气的空间。
- HTTP 与 MCP 共用 `runtime/input_models.py`，均拒绝未知字段和非法输入；直接调用领域对象也会校验。

## 计算来源与精度

回归黄道以日期真春分点为起点，每 30° 一个星座；这与天空中的 IAU 星座边界不同。
太阳通过 `SunPosition` 取得地心位置，月亮通过 `EclipticGeoMoon` 取得地心几何位置；
两者均使用日期真黄道/真春分点坐标系。

结果包含 `provider`、`algorithm_version`、`zodiac`、`coordinate_frame`、`time_model`、
`accuracy_arcminutes` 和计算假设。采用库声明的 1 角分位置精度作为交界保守范围；
交界距离在此范围内时返回相邻星座候选，不给出唯一落座。

时间模型将 UTC 近似为 UT1，再用 Espenak-Meeus ΔT 模型得到 TT。
未来 ΔT 的预测差异不包含在标称 1 角分位置误差内。
独立 Swiss Ephemeris 比对使用相同的 TT 时刻；直接混用两套库的未来 ΔT 默认值会产生额外偏差。

## API 与 MCP

- HTTP：`POST /api/western/chart`，响应为 `{"chart": ...}`。
- MCP：`western_chart`，参数与 HTTP 相同；省略 `hour` 即日期精度。
- 已配置 `MINGLI_API_KEY` 时，新 HTTP 接口同样要求 `X-API-Key`。
- MCP 保留原有工具，并新增 `synthesis`；参数 schema 由共用请求模型生成。
- 日期精度暂不接入现有要求出生小时的记忆档案 API；分钟精度字段与现有出生档案共用。

## 验证

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest -q -ra
```

`tests/fixtures/western_reference.json` 包含 17 个固定参考时刻：2024 年各月及
1900/1950/2000/2050/2100 年边界样本。参考位置由 **PySwissEph 2.10.3.2** 独立生成，
使用 Moshier 后端和固定 JD(TT)，差异阈值为 1 角分。
太阳为 `calc(JD_TT, SUN, FLG_MOSEPH)`，月亮为
`calc(JD_TT, MOON, FLG_MOSEPH | FLG_TRUEPOS)`，与本期月亮几何位置约定一致。
PySwissEph 仅在 checkout 外的独立环境中用于生成参考数据，不是应用或测试运行依赖。

回归测试覆盖十二个 30° 区间、0°/360°、春分当日交界、跨年时区、DST 歧义/缺口、
未知出生时间的月亮换座、输入校验、HTTP/MCP 一致性和禁止网络的计算路径。

## 候选项目

- [Astronomy Engine](https://github.com/cosinekitty/astronomy)：当前唯一新增生产依赖，MIT。
- [Kerykeion](https://github.com/g-battaglia/kerykeion)：完整星盘/SVG 候选；当前 v6 默认
  `libephemeris`，采用 AGPL/商业授权，未集成。
- [Flatlib](https://github.com/flatangle/flatlib)：传统占星参考；自身 MIT，依赖的
  `pyswisseph` 采用 AGPL，未集成。
- [PySwissEph](https://github.com/astrorigin/pyswisseph)：独立参考数据来源，未纳入生产依赖。

## 上升、宫位与相位 v2

上升求日期真黄道面与地平面的交点，使用当地真恒星时和纬度，并以高度对恒星时的正导数选择正在升起的交点。经度东正西负。地平定义为几何地平，不加大气折射。
纬度绝对值达到 89° 或交点退化时，保留行星结果，并在 `unavailable` 提示上升/宫位无法计算。

整宫制从上升所在星座的 0° 开始；等宫制从上升点精确黄经开始，两者均为十二个 30° 区间，宫头属于新宫。行星列表为水星、金星、火星、木星、土星、天王星、海王星、冥王星；使用 `GeoVector(..., aberration=True)` 加 `Ecliptic`。日月保持原算法，兼容先前结果。

相位只计算十个天体之间的合相 0°、六合 60°、刑相 90°、拱相 120°、冲相 180°。涉及日月的容许度为 8°，其余 6°，边界包含。返回实际角距、与精确相位的差值及容许度阈值，按差值排序。不计算入相/出相，不把上升加入行星相位。

仅日期输入不生成行星精确位置、上升、宫位或相位。准确时刻但无地点，仍能生成日月、行星和相位。出生地点和时间的不确定性不能用行星的 1 角分数值误差替代。

独立参考 `tests/fixtures/western_extended_reference.json` 含 8 个 UTC 时刻、南北半球和不同经纬度，对照 Swiss 的 W/A 宫制及 Moshier 十个天体；上升/宫头阈值 0.02°，天体阈值 1 角分。参考生成依赖在仓库外安装，生产和 pytest 均不需要 Swiss 库。未来 UTC/UT1 与 ΔT 差异仍适用前述限制。

## 跨体系解读

`POST /api/synthesis` / MCP `synthesis` 接受西方出生字段、`house_system`、`question`、`leap_month`，返回：

- `charts.bazi`、`charts.ziwei`、`charts.western`：各自独立计算，保留来源及策略。
- `interpretation`：问题、主题、象征解释、事实证据与引用 ID、规则版本、缺失信息和边界。

规则版本 `synthesis-symbolic-v1`；不接入 LLM。按问题关键词区分事业/学习、关系/沟通、压力/情绪或通用自我探索，调整反思问题。说明分别引用八字日主五行、紫微命宫星曜、西方日月/上升/主要相位；不把五行、紫微星曜和西方元素互相换算。

这是一套可检查的探索框架，而非科学性格结论或针对问题的预测。不凭日主判旺衰、喜用，不凭单宫或单相位断命。未知时刻时八字/紫微为 null，仅展示西方日月候选并提示补充；候选星座不强行解释为一个唯一结果。

复现离线 HTTP 回归：`.venv/bin/python scripts/offline_api_check.py`。该脚本启动临时 loopback 服务与临时记忆文件，审计钩子禁止外部连接和 DNS，完成后自动关闭。
