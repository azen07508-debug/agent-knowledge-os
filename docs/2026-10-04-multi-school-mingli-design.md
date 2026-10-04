# MingLi Agent 多流派策略内核设计

## 1. 设计目标

MingLi Agent 采用“确定性计算 + 多流派策略 + 证据链 + 可评估 Agent”的架构。
系统不把任何单一命理流派、单一大运起运算法或单一用神判断标记为唯一正确答案。

每个解释性结果必须携带：

- `school`：理论流派
- `policy`：具体算法或策略名称
- `version`：策略版本
- `evidence`：支持事实与规则
- `confidence`：证据强度，不表示事件发生概率
- `conflicts`：冲突策略或规则

## 2. 非目标

本阶段不做：

- 以 LLM 直接计算四柱、大运或流年
- 把“证据强度”表述成现实事件概率
- 把未经文献核校的网络断语写成经典原文
- 默认选择某个流派并隐藏其他流派差异
- 在没有 golden case 的情况下宣称“行业最高准确率”

## 3. 分层架构

```text
BirthInput
  ↓
Chart Provider（sxtwl / 其他实现）
  ↓
Canonical Chart
  ↓
Fact Extractor
  ↓
School Strategy Registry
  ├── Dayun Strategy
  ├── Strength Strategy
  ├── YongShen Strategy
  └── Event Window Strategy
  ↓
Evidence Layer
  ↓
Analyst
  ↓
Critic
  ↓
Conflict-aware Report
```

各层只能依赖前一层的稳定契约。LLM 只能解释已生成的事实和证据，不得绕过
Chart Provider 或 Rule Registry 自行生成计算结果。

## 4. 核心接口

### 4.1 策略上下文

```python
@dataclass(frozen=True)
class StrategyContext:
    school: str
    policy: str
    version: str
    assumptions: tuple[str, ...]
```

### 4.2 大运策略

```python
class DayunStrategy(Protocol):
    context: StrategyContext

    def calculate(self, chart: Chart) -> DayunResult:
        ...
```

`DayunResult` 至少包含：

- 顺逆方向
- 起运年龄或起运时间
- 大运干支序列
- 起运计算依据
- 近似/精确标志
- 输入假设

当前 `classical_approx_v1` 只能作为显式近似策略，不能成为默认唯一策略。

### 4.3 旺衰与用神策略

```python
class StrengthStrategy(Protocol):
    context: StrategyContext

    def evaluate(self, chart: Chart) -> StrengthResult:
        ...

class YongShenStrategy(Protocol):
    context: StrategyContext

    def evaluate(self, chart: Chart, strength: StrengthResult) -> YongShenResult:
        ...
```

结果必须区分：

- 计算事实
- 策略假设
- 规则命中
- 解释结论

### 4.4 冲突合并

```python
class StrategyComparator:
    def compare(self, results: list[StrategyResult]) -> ConflictReport:
        ...
```

如果不同策略结论不同，系统输出并列结果和差异来源，不自动投票选出“真相”。

## 5. 规则版本化

规则 ID 不能只代表结论，还必须记录：

- 文献来源
- 版本或底本
- 流派
- 条件表达式
- 支持的事实字段
- 置信等级
- 冲突规则
- 人工校核状态

规则状态：

```text
UNREVIEWED → REVIEWED → ACTIVE
                         ↘ DEPRECATED
```

当前项目中的“待版本核校”规则只能用于结构演示和内部测试，不得作为生产报告的
权威引用。

## 6. Evidence Layer 规范

Evidence Layer 负责：

1. 从 Chart 提取可复现事实；
2. 根据 topic 和 school 筛选规则；
3. 记录规则命中和未满足条件；
4. 计算证据强度；
5. 记录跨流派冲突；
6. 输出可序列化证据链。

证据强度只表示“当前输入、当前规则和当前策略下的支持程度”，不得写成：

```text
68% 会发生
```

应写成：

```text
当前证据强度：0.68；这不是现实事件发生概率。
```

## 7. Agent 协议

### Analyst

- 识别用户主题
- 请求指定流派或使用明确默认配置
- 调用 Chart、Strategy、Rule、Evidence 工具
- 只根据证据组织解释
- 明确假设、冲突和未知项

### Critic

- 检查命盘事实是否来自 provider
- 检查规则 ID 和来源是否存在
- 检查结论是否超过证据范围
- 检查确定性措辞
- 检查是否披露流派冲突
- 检查是否把证据强度说成概率

### Report Generator

输出固定章节：

1. 输入和计算口径
2. 命盘事实
3. 采用的流派与策略
4. 命中规则和来源
5. 分析结论
6. 其他流派或策略差异
7. 未知项与限制
8. 非医疗、法律、投资或人生决策保证声明

## 8. 评估计划

评估分为四层，不混用指标：

### A. 计算正确性

- 四柱、十神、纳音、藏干
- 立春和节气边界
- 真太阳时输入和转换
- 大运策略 golden cases

### B. 规则正确性

- 规则条件匹配
- 规则来源存在性
- 冲突识别
- 未知条件拒绝误匹配

### C. Agent 行为

- 证据引用率
- 幻觉规则率
- 确定性措辞违规率
- 冲突披露率
- 前后一致性

### D. 外部 Benchmark

- MingLi-Bench：知识/推理题
- fate-bench：历史事件资料验证

外部 benchmark 适配完成前，不在项目中填写准确率成绩。

## 9. 实施顺序

1. 将当前 `classical_approx_v1` 改造成带元数据的策略对象；
2. 增加策略注册表和比较器；
3. 为大运、旺衰和用神建立独立结果模型；
4. 扩展 Evidence Layer 的 school/policy/version 字段；
5. 接入报告生成器和 Critic 检查；
6. 建立 20 个本地 golden cases；
7. 适配 MingLi-Bench；
8. 适配 fate-bench；
9. 再实现用户记忆、MCP、Web UI 和生产安全能力。

## 10. 验收门槛

进入下一阶段前必须满足：

- 所有新策略都有独立测试；
- 所有输出都有 provider/strategy provenance；
- 冲突不会被静默吞掉；
- 未验证规则不会冒充权威来源；
- 全量回归测试通过；
- 评估报告区分计算、规则、Agent 和外部 benchmark 指标。
