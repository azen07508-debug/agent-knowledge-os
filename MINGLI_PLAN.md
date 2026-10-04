# 命理智能体完整执行计划（MingLi Agent Plan）

> 创建日期：2026-10-04
> 项目定位：不是"会算命的聊天机器人"，而是一个能够排盘、引用规则、形成证据链、处理流派冲突，并且可以用 Benchmark 持续验证的命理推理 Agent。

---

## 一、项目愿景

### 1.1 核心目标

构建一个**可验证的命理推理 Agent**，而不是简单的"LLM + 八字项目"。

**核心能力**：
- 确定性排盘计算（不让 LLM 算命盘）
- 规则引擎（传统命理典籍规则化）
- 证据链追踪（每个结论都有依据）
- 流派系统（处理不同理论体系的冲突）
- 持续评估（MingLi-Bench + fate-bench + 自建测试集）

**不做什么**：
- ❌ 不直接让 LLM 计算四柱、十神、大运
- ❌ 不把一次推断当成永久规则
- ❌ 不编造命理规则
- ❌ 不混淆"推测"和"事实"
- ❌ 不保证预测准确率（只提供证据强度）

---

## 二、架构设计

### 2.1 核心分层架构

```text
                         ┌──────────────┐
                         │     用户     │
                         └──────┬───────┘
                                ↓
                       ┌─────────────────┐
                       │ Conversation    │
                       │     Agent       │
                       └────────┬────────┘
                                ↓
                 ┌──────────────┼──────────────┐
                 ↓              ↓              ↓
          Chart Tools      Knowledge       User Memory
                 ↓              ↓              ↓
          ┌──────────┐   ┌──────────┐   ┌──────────┐
          │Bazi      │   │Classics  │   │Previous  │
          │Engine    │   │Rules     │   │Questions │
          └────┬─────┘   └────┬─────┘   └──────────┘
               │              │
               └──────┬───────┘
                      ↓
                Evidence Layer  (最关键的创新层)
                      ↓
                Reasoning Agent
                      ↓
                Critic Agent
                      ↓
              Confidence / Conflict
                      ↓
                Report Generator
```

### 2.2 能力模块划分

| 模块 | 职责 | 主要参考项目 |
|------|------|------------|
| **Chart Engine** | 四柱、十神、大运、流年排盘 | HeiGe-SuanMing, bazi-engine, xuziping-bazi |
| **Knowledge Engine** | 规则库、经典文献、流派系统 | HeiGe-SuanMing 的 23 个 references |
| **Evidence Layer** | 事实提取、规则匹配、证据追踪 | **自研**（核心创新） |
| **Reasoning Agent** | 基于证据的推理 | 基于 LLM + 证据约束 |
| **Critic Agent** | 检查推理合理性、冲突检测 | 双模型架构 |
| **Evaluation Engine** | 持续验证 | MingLi-Bench, fate-bench, 自建测试 |

---

## 三、执行阶段（Phase 0-20）

### Phase 0：项目总原则

1. **计算与推理分离**：LLM 不负责计算，只负责理解问题和解释证据
2. **证据前置**：先有事实和规则，再有结论
3. **流派透明**：不同流派的判断差异必须明确告知用户
4. **可验证性**：每个阶段都有测试覆盖
5. **渐进式开发**：先八字，再紫微，再其他体系
6. **本地优先**：核心计算引擎可离线运行
7. **API 可替换**：不绑定单一 LLM 提供商

---

### Phase 1：Chart Engine（排盘引擎）

**目标**：建立确定性的命盘计算核心，保证计算结果可复现、可审计。

#### 1.1 技术选型

**主引擎选择**：
- **首选**：HeiGe-SuanMing（Python）
  - 理由：434 个回归测试，完整知识底座，可审计推理链
  - 覆盖：八字 + 紫微 + 梅花 + 六爻 + 奇门遁甲
- **备选**：xuziping-bazi（Python，专注八字，方法论清晰）

**TypeScript 集成层**（如需 Web 前端）：
- shunshi-bazi-core 或 openfate-ai/bazi-engine
- 用于前端展示，后端仍走 Python 引擎

#### 1.2 核心能力

```python
class BaziEngine:
    def calculate_chart(self, birth_input: BirthInput) -> Chart:
        """
        输入：阳历生日 + 时辰 + 经度（真太阳时）
        输出：四柱、藏干、纳音、十神、五行强弱
        """
        pass
    
    def calculate_dayun(self, chart: Chart) -> List[DaYun]:
        """大运计算"""
        pass
    
    def calculate_liunian(self, chart: Chart, year: int) -> LiuNian:
        """流年计算"""
        pass
    
    def analyze_relations(self, chart: Chart) -> List[Relation]:
        """刑冲合害穿破"""
        pass
```

#### 1.3 测试覆盖

- [ ] 立春分界测试（2月3/4/5日边界）
- [ ] 节气换月测试（月柱在节气前后的变化）
- [ ] 真太阳时测试（东八区vs东九区）
- [ ] 早子时/晚子时测试
- [ ] 闰月测试
- [ ] 历史名人命盘对照（10个golden cases）

#### 1.4 验收标准

1. 所有边界测试通过
2. 与 HeiGe-SuanMing 的 158 个八字测试结果一致
3. 计算耗时 < 100ms（单次排盘）
4. API 文档完整
5. 错误处理清晰（非法输入、边界年份）

---

### Phase 2：Knowledge Engine（规则库）

**目标**：把传统命理典籍转化为结构化规则，支持多流派。

#### 2.1 经典文献规则化

**优先级顺序**：
1. 《渊海子平》（子平体系基础）
2. 《滴天髓》（用神体系）
3. 《子平真诠》（格局理论）
4. 《三命通会》（神煞体系）
5. 《穷通宝鉴》（调候用神）

#### 2.2 规则数据结构

```python
@dataclass
class Rule:
    id: str                    # RULE_001
    source: str                # 《滴天髓》
    school: str                # classical_method_A / modern_method
    category: str              # ten_god / strength / structure
    condition: Dict            # 条件匹配
    conclusion: str            # 结论描述
    confidence: str            # HIGH / MEDIUM / LOW
    conflicts_with: List[str]  # 与哪些规则冲突
    evidence_required: List[str]  # 需要哪些命盘要素

# 示例
RULE_017 = Rule(
    id="RULE_017",
    source="《滴天髓》",
    school="classical_method_A",
    category="career",
    condition={"ten_god": {"正官": "month"}, "strength": "medium"},
    conclusion="官星得令，宜从政或管理",
    confidence="MEDIUM",
    conflicts_with=["RULE_043"],
    evidence_required=["ten_god", "month_branch", "day_master_strength"]
)
```

#### 2.3 流派系统

不同流派对同一命盘可能有不同判断。必须明确区分：

| 流派 | 核心方法 | 代表典籍 |
|------|---------|---------|
| 子平正统 | 格局用神 | 《渊海子平》《子平真诠》 |
| 滴天髓派 | 通关调候 | 《滴天髓》 |
| 盲派 | 做功理论 | 现代盲派传承 |
| 新派 | 象法体系 | 现代命理家 |

**流派冲突处理**：
```python
class SchoolConflict:
    def detect(self, chart: Chart) -> List[Conflict]:
        """检测不同流派的判断差异"""
        pass
    
    def explain(self, conflict: Conflict) -> str:
        """解释为什么不同流派会有不同结论"""
        pass
```

#### 2.4 验收标准

1. 至少 50 条规则录入（优先《滴天髓》）
2. 每条规则有明确来源和条件
3. 冲突规则已标注
4. 流派系统可扩展
5. 规则查询 API 完整

---

### Phase 3：Evidence Layer（证据层）★核心创新

**目标**：这是整个项目最重要的创新层。不让模型直接输出结论，而是先提取事实、匹配规则、形成证据链。

#### 3.1 工作流程

```text
命盘
 ↓
事实提取（Fact Extraction）
 ↓
规则匹配（Rule Matching）
 ↓
证据链（Evidence Chain）
 ↓
结论（Conclusion with Evidence）
```

#### 3.2 事实提取

```python
@dataclass
class Fact:
    type: str           # ten_god / branch_relation / strength / element
    fact: str           # 具体事实描述
    chart_element: str  # 对应命盘要素
    confidence: float   # 0.0 - 1.0

# 示例
facts = [
    Fact(
        type="ten_god",
        fact="月柱正官透出",
        chart_element="month_stem:正官",
        confidence=1.0
    ),
    Fact(
        type="branch_relation",
        fact="日支与月支六合",
        chart_element="day_branch:寅 + month_branch:亥",
        confidence=1.0
    )
]
```

#### 3.3 证据数据结构

```python
@dataclass
class Evidence:
    topic: str                # career / marriage / health
    facts: List[Fact]         # 相关事实
    rules: List[str]          # 匹配的规则ID
    sources: List[str]        # 规则来源
    strength: float           # 证据强度（0.0-1.0）
    conflicts: List[str]      # 冲突的规则ID
    school: str               # 采用的流派
    
    def to_json(self) -> Dict:
        """输出结构化证据"""
        return {
            "topic": self.topic,
            "facts": [f.fact for f in self.facts],
            "rules": self.rules,
            "sources": self.sources,
            "strength": self.strength,
            "conflicts": self.conflicts,
            "school": self.school
        }
```

#### 3.4 证据强度计算

```python
def calculate_evidence_strength(evidence: Evidence) -> float:
    """
    证据强度 = 事实数量 × 规则置信度 × 流派一致性
    """
    fact_score = min(len(evidence.facts) * 0.2, 0.6)  # 最多0.6
    rule_confidence = sum([get_rule_confidence(r) for r in evidence.rules]) / len(evidence.rules)
    conflict_penalty = len(evidence.conflicts) * 0.1
    
    return min(fact_score * rule_confidence - conflict_penalty, 1.0)
```

#### 3.5 验收标准

1. 能从命盘提取 20+ 事实
2. 事实与规则匹配准确率 > 90%
3. 证据链可追溯（用户能看到推理路径）
4. 冲突规则被正确标注
5. 证据强度计算合理

---

### Phase 4：Reasoning Agent（推理智能体）

**目标**：基于证据进行命理推理，而不是凭空生成。

#### 4.1 Analyst 模型

```python
class ReasoningAgent:
    def __init__(self, chart_engine, knowledge_engine, evidence_layer):
        self.chart = chart_engine
        self.knowledge = knowledge_engine
        self.evidence = evidence_layer
    
    def analyze(self, chart: Chart, question: str) -> Analysis:
        """
        分析流程：
        1. 理解用户问题（事业/婚姻/健康等）
        2. 提取相关事实
        3. 匹配规则
        4. 形成证据链
        5. 给出推理结论
        """
        # 提取事实
        facts = self.evidence.extract_facts(chart, question)
        
        # 匹配规则
        rules = self.knowledge.match_rules(facts, question)
        
        # 形成证据
        evidence = self.evidence.build_evidence(facts, rules)
        
        # LLM 只负责理解问题和解释证据
        prompt = f"""
        用户问题：{question}
        
        命盘事实：
        {json.dumps([f.to_dict() for f in facts], ensure_ascii=False)}
        
        匹配规则：
        {json.dumps([self.knowledge.get_rule(r).to_dict() for r in rules], ensure_ascii=False)}
        
        请基于以上事实和规则，给出推理结论。
        要求：
        1. 只能根据已有事实和规则推理
        2. 明确说明推理依据
        3. 标注证据强度
        4. 不编造规则
        """
        
        conclusion = self.llm.generate(prompt)
        
        return Analysis(
            question=question,
            facts=facts,
            rules=rules,
            evidence=evidence,
            conclusion=conclusion,
            strength=evidence.strength
        )
```

#### 4.2 验收标准

1. 推理结论能追溯到具体规则
2. 不引用不存在的规则
3. 证据强度合理
4. 回答与问题相关
5. 通过 10 个测试案例

---

### Phase 5：Critic Agent（审查智能体）

**目标**：双模型架构，第二个模型负责检查第一个模型的推理质量。

#### 5.1 Critic 检查项

```python
class CriticAgent:
    def critique(self, analysis: Analysis) -> Critique:
        """
        检查清单：
        1. 有没有编造命盘数据？
        2. 有没有跳过规则直接下结论？
        3. 证据能不能支持结论？
        4. 有没有把概率说成确定事件？
        5. 有没有不同流派冲突？
        6. 有没有逻辑矛盾？
        """
        checks = []
        
        # 检查1：数据编造
        if not self._verify_facts(analysis.facts, analysis.chart):
            checks.append("发现编造的命盘数据")
        
        # 检查2：规则跳跃
        if not self._verify_rule_chain(analysis.rules, analysis.conclusion):
            checks.append("结论未能追溯到规则")
        
        # 检查3：证据支持度
        if analysis.strength < 0.3 and "确定" in analysis.conclusion:
            checks.append("低证据强度下使用了确定性表述")
        
        # 检查4：流派冲突
        conflicts = self._detect_school_conflicts(analysis.rules)
        if conflicts:
            checks.append(f"存在流派冲突：{conflicts}")
        
        return Critique(
            passed=len(checks) == 0,
            issues=checks,
            recommendation="修改" if checks else "通过"
        )
```

#### 5.2 迭代修正

```text
Analyst
   ↓
Critic
   ↓
修改（如有问题）
   ↓
Critic（再次检查）
   ↓
Final（通过后输出）
```

#### 5.3 验收标准

1. 能检测出编造的数据
2. 能检测出缺失的推理链
3. 能检测出流派冲突
4. 误报率 < 10%
5. 通过 20 个测试案例

---

### Phase 6：Time Engine（时间轴引擎）

**目标**：分析流年流月的事件窗口。

#### 6.1 时间窗口分析

```python
class TimeEngine:
    def analyze_period(
        self, 
        chart: Chart, 
        start_year: int, 
        end_year: int,
        topic: str
    ) -> List[TimeWindow]:
        """
        分析某个时间段内的事件窗口
        """
        windows = []
        
        for year in range(start_year, end_year + 1):
            liunian = self.chart_engine.calculate_liunian(chart, year)
            
            # 提取该年事实
            facts = self.evidence.extract_facts(chart, f"{year}年{topic}")
            
            # 匹配规则
            rules = self.knowledge.match_rules(facts, topic)
            
            # 计算信号强度
            signals = self._calculate_signals(facts, rules)
            
            if signals:
                windows.append(TimeWindow(
                    year=year,
                    topic=topic,
                    signals=signals,
                    strength=self._calculate_strength(signals)
                ))
        
        return windows
```

#### 6.2 信号强度

```python
@dataclass
class TimeWindow:
    year: int
    topic: str
    signals: List[str]        # 该年的命理信号
    strength: float           # 0.0 - 1.0
    evidence: List[Evidence]  # 支持证据
    
    def to_report(self) -> str:
        """
        输出形式：
        "2028年，信号：财星入命、食神生财，证据强度0.68"
        
        而不是：
        "2028年你一定会发财"
        """
        return f"{self.year}年，信号：{', '.join(self.signals)}，证据强度{self.strength:.2f}"
```

#### 6.3 验收标准

1. 时间窗口计算准确
2. 信号强度合理
3. 不做确定性预测
4. 可回溯到具体规则
5. 通过 5 个历史案例验证

---

### Phase 7：Evaluation Engine（评估引擎）

**目标**：持续验证系统能力，而不是"上线后就不管"。

#### 7.1 三套 Benchmark

```text
                    Evaluation
                         │
          ┌──────────────┼──────────────┐
          ↓              ↓              ↓
    MingLi-Bench     fate-bench    自建测试集
          │              │              │
     命理知识         历史事件        Agent能力
```

#### 7.2 MingLi-Bench 集成

```python
class MingLiBenchEvaluator:
    def run_benchmark(self) -> BenchmarkResult:
        """
        运行 MingLi-Bench 的 160 道题
        """
        results = []
        
        for question in load_mingli_bench():
            # 注入预计算命盘（--astro模式）
            chart = question.get_chart()
            
            # Agent推理
            analysis = self.agent.analyze(chart, question.text)
            
            # 匹配答案
            predicted = self._extract_answer(analysis.conclusion)
            correct = predicted == question.answer
            
            results.append({
                "id": question.id,
                "category": question.category,
                "correct": correct,
                "evidence_strength": analysis.strength
            })
        
        return BenchmarkResult(
            total=len(results),
            correct=sum(r["correct"] for r in results),
            accuracy=sum(r["correct"] for r in results) / len(results),
            by_category=self._group_by_category(results)
        )
```

#### 7.3 fate-bench 集成

```python
class FateBenchEvaluator:
    def verify_historical_events(self) -> List[Verification]:
        """
        验证历史人物的真实人生事件
        """
        cases = load_fate_bench()  # 295个问题、63个人
        
        verifications = []
        for case in cases:
            chart = self.chart_engine.calculate_chart(case.birth_info)
            
            # 分析事件窗口
            windows = self.time_engine.analyze_period(
                chart,
                case.event_year - 2,
                case.event_year + 2,
                case.event_type
            )
            
            # 检查是否在事件窗口内
            hit = any(w.year == case.event_year and w.strength > 0.5 for w in windows)
            
            verifications.append(Verification(
                person=case.person,
                event=case.event,
                year=case.event_year,
                predicted=hit,
                actual=True,
                matched=hit
            ))
        
        return verifications
```

#### 7.4 自建测试集

测试维度：
1. **排盘正确性**（100个边界case）
2. **十神正确性**（50个golden cases）
3. **大运正确性**（20个标准案例）
4. **规则调用正确性**（不引用不存在的规则）
5. **证据引用正确性**（结论能追溯到事实）
6. **流年分析一致性**（同一命盘重复分析结果一致）
7. **流派冲突处理**（正确标注不同流派的差异）
8. **幻觉率**（不编造命盘数据）
9. **前后回答一致性**（记忆系统）
10. **用户问题理解**（能正确理解事业/婚姻/健康等不同问题）

#### 7.5 验收标准

1. MingLi-Bench 准确率 > 40%（首个版本）
2. fate-bench 历史事件命中率 > 30%
3. 排盘正确性 100%
4. 规则引用准确率 > 95%
5. 幻觉率 < 5%
6. 完整测试报告

---

### Phase 8：Memory Layer（记忆层）

**目标**：保存用户的历史提问和命盘，形成个人档案。

#### 8.1 记忆分类

```text
/UserProfiles      # 用户档案（命盘、基础信息）
/Questions         # 历史提问
/Analyses          # 历史分析结果
/Experiments       # 验证记录
/Feedback          # 用户反馈
```

#### 8.2 数据结构

```python
@dataclass
class UserProfile:
    user_id: str
    birth_info: BirthInput
    chart: Chart
    created_at: datetime
    questions: List[str]       # 历史问题ID
    analyses: List[str]        # 历史分析ID
    preferences: Dict          # 流派偏好等

@dataclass
class QuestionRecord:
    id: str
    user_id: str
    question: str
    topic: str                 # career / marriage / health
    asked_at: datetime
    analysis_id: str

@dataclass
class AnalysisRecord:
    id: str
    question_id: str
    chart_snapshot: Dict       # 命盘快照
    facts: List[Fact]
    rules: List[str]
    evidence: Evidence
    conclusion: str
    strength: float
    school: str                # 采用的流派
    critique: Critique
    created_at: datetime
```

#### 8.3 验收标准

1. 用户档案可持久化
2. 历史问题可检索
3. 分析结果可回溯
4. 支持多用户
5. 数据导出功能

---

### Phase 9：Web UI（用户界面）

**目标**：清晰展示推理过程，而不是只给一个结论。

#### 9.1 界面结构

```text
┌─────────────────────────────────────┐
│         命理智能体                    │
├─────────────────────────────────────┤
│ 1. 输入生辰                          │
│    [ 阳历 ] [ 时辰 ] [ 经度 ]         │
├─────────────────────────────────────┤
│ 2. 命盘展示                          │
│    年柱  月柱  日柱  时柱             │
│    甲子  乙丑  丙寅  丁卯             │
│                                     │
│    十神  藏干  纳音  五行             │
├─────────────────────────────────────┤
│ 3. 提问                              │
│    [ 事业如何？ ]                     │
├─────────────────────────────────────┤
│ 4. 分析过程（可展开）                 │
│    ▼ 事实提取（5条）                  │
│    ▼ 规则匹配（3条）                  │
│    ▼ 证据链（2个证据）                │
│    ▼ 流派冲突（1个）                  │
│    ▼ 证据强度（0.68）                 │
├─────────────────────────────────────┤
│ 5. 推理结论                          │
│    [基于《滴天髓》官星理论...]        │
│                                     │
│    证据强度：68%                     │
│    流派：子平正统                     │
│    冲突：盲派理论认为...              │
├─────────────────────────────────────┤
│ 6. 审查报告（可选）                   │
│    ✓ 数据真实性                      │
│    ✓ 规则追溯性                      │
│    ✓ 流派一致性                      │
└─────────────────────────────────────┘
```

#### 9.2 关键设计

1. **命盘可视化**：四柱、十神、藏干清晰展示
2. **推理过程透明**：每一步都可展开查看
3. **证据强度可视化**：用进度条或颜色表示
4. **流派切换**：用户可选择不同流派查看差异
5. **历史记录**：可查看过往提问

#### 9.3 验收标准

1. 界面清晰易用
2. 推理过程可追溯
3. 证据强度可视化
4. 流派切换功能正常
5. 响应速度 < 2s

---

### Phase 10：API Layer（API层）

**目标**：提供标准 API，供第三方集成。

#### 10.1 核心接口

```python
# RESTful API

POST /api/chart
# 输入：生辰信息
# 输出：命盘JSON

POST /api/analyze
# 输入：命盘 + 问题
# 输出：分析结果（事实、规则、证据、结论）

GET /api/rules
# 查询规则库

GET /api/history/{user_id}
# 查询用户历史

POST /api/evaluate
# 运行benchmark
```

#### 10.2 验收标准

1. API文档完整（OpenAPI）
2. 接口响应稳定
3. 错误处理清晰
4. 支持批量请求
5. 有限流机制

---

### Phase 11-15：扩展能力

#### Phase 11：紫微斗数

基于 iztro，集成紫微斗数排盘和推理。

#### Phase 12：流年详批

基于 Time Engine，提供全年运势分析。

#### Phase 13：合婚分析

双命盘对比分析。

#### Phase 14：择吉系统

基于命盘和流年，推荐吉日。

#### Phase 15：MCP集成

提供 MCP Server，接入 Claude Desktop 等工具。

---

### Phase 16-20：生产就绪

#### Phase 16：性能优化

- 命盘计算缓存
- 规则匹配索引
- LLM调用优化

#### Phase 17：安全加固

- 用户数据加密
- API 鉴权
- 敏感信息脱敏

#### Phase 18：多语言支持

- 中文（简体/繁体）
- 英文
- 日韩文

#### Phase 19：移动端

- React Native / Flutter
- 小程序

#### Phase 20：商业化

- 订阅模式
- API 付费
- 企业版

---

## 四、技术栈

### 4.1 后端

| 组件 | 技术选型 | 理由 |
|------|---------|------|
| 排盘引擎 | Python (HeiGe-SuanMing) | 测试完整、可审计 |
| 规则引擎 | Python + SQLite | 查询效率、可扩展 |
| API 服务 | FastAPI | 高性能、异步 |
| LLM 集成 | LangChain / LlamaIndex | 灵活可替换 |
| 数据库 | PostgreSQL | 用户数据、历史记录 |
| 缓存 | Redis | 命盘缓存、会话管理 |

### 4.2 前端

| 组件 | 技术选型 |
|------|---------|
| Web | React + TypeScript |
| UI库 | Tailwind CSS |
| 图表 | ECharts / D3.js |
| 状态管理 | Zustand |

### 4.3 基础设施

| 组件 | 技术选型 |
|------|---------|
| 容器化 | Docker |
| 部署 | Kubernetes / Railway |
| 监控 | Prometheus + Grafana |
| 日志 | ELK Stack |

---

## 五、项目里程碑

### Milestone 1：核心能力验证（2个月）

- [ ] Phase 1-3 完成
- [ ] 排盘引擎测试通过
- [ ] 证据层 MVP
- [ ] 10个测试案例通过

### Milestone 2：推理能力验证（2个月）

- [ ] Phase 4-6 完成
- [ ] Reasoning + Critic Agent
- [ ] Time Engine
- [ ] MingLi-Bench 准确率 > 35%

### Milestone 3：评估体系建立（1个月）

- [ ] Phase 7 完成
- [ ] 三套 Benchmark 集成
- [ ] 自建测试集 100+
- [ ] 完整评估报告

### Milestone 4：产品化（2个月）

- [ ] Phase 8-10 完成
- [ ] Web UI
- [ ] API
- [ ] 用户系统

### Milestone 5：公开发布（1个月）

- [ ] 文档完善
- [ ] 性能优化
- [ ] 安全加固
- [ ] 上线运营

---

## 六、与现有项目的区别

### 6.1 vs. 普通"AI算命"

| 维度 | 普通AI算命 | 本项目 |
|------|-----------|-------|
| 排盘 | LLM算 | 确定性引擎 |
| 推理 | 直接输出结论 | 证据链 + 规则引用 |
| 验证 | 无 | 三套Benchmark |
| 流派 | 不区分 | 明确流派 + 冲突标注 |
| 可解释性 | 黑盒 | 全程可追溯 |

### 6.2 vs. MingLi-Bench

MingLi-Bench 是**评估工具**，本项目是**完整系统**。

我们使用 MingLi-Bench 来**持续验证**系统能力。

### 6.3 vs. HeiGe-SuanMing

HeiGe-SuanMing 是**排盘引擎**，本项目是**推理系统**。

我们使用 HeiGe-SuanMing 作为**排盘核心**，在其上构建证据层和推理层。

---

## 七、风险与应对

### 7.1 技术风险

| 风险 | 应对 |
|------|------|
| LLM 幻觉 | 证据层约束 + Critic Agent |
| 规则冲突 | 流派系统明确标注 |
| 性能瓶颈 | 缓存 + 异步 + 索引 |
| 准确率不达标 | 持续优化规则库 + 更强LLM |

### 7.2 产品风险

| 风险 | 应对 |
|------|------|
| 用户期望过高 | 明确说明是"推理工具"不是"预测工具" |
| 法律合规 | 免责声明 + 娱乐定位 |
| 商业化难 | 先做口碑，再做付费 |

---

## 八、验收标准

### 每个 Phase 完成后必须输出：

1. **修改了什么**：代码变更清单
2. **为什么修改**：设计决策
3. **文件清单**：新增/修改的文件
4. **数据结构**：核心数据模型
5. **API**：接口文档
6. **测试结果**：测试覆盖率 + 通过率
7. **构建结果**：能否正常运行
8. **已知问题**：当前缺陷
9. **未实现功能**：留待后续
10. **下一阶段建议**：接下来做什么

---

## 九、参考资源

### 9.1 GitHub 项目

| 项目 | 用途 | 链接 |
|------|------|------|
| HeiGe-SuanMing | 排盘引擎 + 规则库 | github.com/HeiGeAi/HeiGe-SuanMing |
| MingLi-Bench | 评估基准 | github.com/DestinyLinker/MingLi-Bench |
| fate-bench | 历史事件验证 | github.com/shunshi-ai/fate-bench |
| bazi-engine | TS 引擎参考 | github.com/openfate-ai/bazi-engine |
| iztro | 紫微斗数引擎 | github.com/SylarLong/iztro |
| xuziping-bazi | 方法论参考 | github.com/mengke-wang/xuziping-bazi |

### 9.2 经典文献

1. 《渊海子平》
2. 《滴天髓》
3. 《子平真诠》
4. 《三命通会》
5. 《穷通宝鉴》

### 9.3 现代研究

1. 寿星天文历算法
2. 真太阳时校正
3. 立春分界原理
4. 节气换月规则

---

## 十、最终愿景

构建一个**透明、可验证、可持续改进**的命理推理系统：

1. **不神化**：明确这是基于传统规则的推理工具
2. **不黑盒**：每个结论都能追溯到具体规则和证据
3. **不固化**：持续用 Benchmark 验证和改进
4. **不独断**：明确标注不同流派的差异
5. **不夸大**：用证据强度替代确定性预测

让用户在使用时能清楚地看到：
- 这个结论基于什么规则？
- 证据有多强？
- 不同流派怎么看？
- 哪些地方还不确定？

这才是一个负责任的命理 Agent 应该做的事。

---

**下一步**：Phase 1 排盘引擎集成，预计 2 周完成。
