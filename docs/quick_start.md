# MingLi Agent 快速开始

本文档帮助你快速了解 MingLi Agent 项目的核心概念和开发流程。

---

## 项目定位

**一句话**：这是一个可验证的命理推理系统，不是"会算命的聊天机器人"。

**核心差异**：

| 传统 AI 算命 | MingLi Agent |
|-------------|--------------|
| LLM 直接算命盘 | 确定性引擎排盘 |
| 黑盒输出结论 | 证据链可追溯 |
| 无法验证 | 三套 Benchmark |
| 不区分流派 | 明确流派冲突 |

---

## 5 分钟理解核心架构

### 传统做法（错误）
```text
用户：我今年事业如何？
  ↓
LLM：根据你的八字，今年事业运不错
  ↓
用户：为什么？
  ↓
LLM：因为你的月柱有正官...（可能是编的）
```

### MingLi Agent（正确）
```text
用户：我今年事业如何？
  ↓
1. Bazi Engine 排盘（确定性计算）
   → 四柱：甲子年 乙丑月 丙寅日 丁卯时
   → 十神：正官在月柱
   → 大运：2028年行伤官运
  ↓
2. Evidence Layer 提取证据
   → 事实1：月柱正官透出
   → 事实2：日支与月支六合
   → 规则：《滴天髓》RULE_017："官星得令，宜从政或管理"
   → 证据强度：0.68
  ↓
3. Reasoning Agent 推理
   → 基于《滴天髓》理论，月柱正官透出且与日支六合...
  ↓
4. Critic Agent 审查
   → ✓ 数据真实性
   → ✓ 规则追溯性
   → ! 存在流派冲突：盲派认为...
  ↓
5. 返回用户
   → 结论 + 证据链 + 流派说明 + 证据强度
```

---

## 核心创新：Evidence Layer

这是整个项目最重要的设计。

### 为什么需要 Evidence Layer？

**问题**：LLM 会编造命理规则，无法验证。

**解决**：在 LLM 推理之前，先用确定性方法提取事实和匹配规则。

### 工作流程

```python
# 1. 提取事实（确定性）
facts = [
    Fact(type="ten_god", fact="月柱正官透出", confidence=1.0),
    Fact(type="relation", fact="日支与月支六合", confidence=1.0)
]

# 2. 匹配规则（查询规则库）
rules = [
    Rule(id="RULE_017", source="《滴天髓》", conclusion="官星得令，宜从政")
]

# 3. 形成证据
evidence = Evidence(
    facts=facts,
    rules=rules,
    strength=0.68,  # 基于事实数量和规则置信度计算
    conflicts=["RULE_043"]  # 标注冲突规则
)

# 4. LLM 只负责解释证据
prompt = f"""
基于以下事实和规则，解释用户问题。
事实：{facts}
规则：{rules}
要求：不编造规则，只解释已有证据。
"""
```

### 与传统 RAG 的区别

| 维度 | 传统 RAG | Evidence Layer |
|------|---------|----------------|
| 检索对象 | 文档块 | 结构化规则 |
| 匹配方式 | 语义相似度 | 条件匹配 + 语义 |
| 输出 | 相关文档 | 事实 + 规则 + 证据链 |
| 可验证性 | 低（文档可能无关） | 高（规则可追溯） |

---

## 项目结构

```text
agent-knowledge-os/
├── engines/              # 排盘引擎（Phase 1）
│   ├── bazi/            # 八字计算
│   └── ziwei/           # 紫微斗数（Phase 11）
│
├── knowledge/           # 知识库（Phase 2-3）
│   ├── rules/           # 规则库（《滴天髓》等）
│   ├── schools/         # 流派系统
│   └── evidence/        # 证据层 ★
│
├── agents/              # Agent（Phase 4-5）
│   ├── reasoning.py     # 推理 Agent
│   └── critic.py        # 审查 Agent
│
├── evaluation/          # 评估系统（Phase 7）
│   ├── mingli_bench.py  # MingLi-Bench 集成
│   └── fate_bench.py    # fate-bench 集成
│
├── api/                 # API 服务（Phase 10）
└── web/                 # Web UI（Phase 9）
```

---

## 开发流程

### Phase 0：规划（已完成 ✅）
- [x] 调研 GitHub 项目
- [x] 制定执行计划
- [x] 设计架构

### Phase 1：排盘引擎（2周）
```bash
# 1. 集成 HeiGe-SuanMing
git clone https://github.com/HeiGeAi/HeiGe-SuanMing.git
cd agent-knowledge-os
python scripts/import_heige.py

# 2. 实现接口
# engines/bazi/calculator.py

# 3. 编写测试
# tests/test_bazi_engine.py

# 4. 验收
pytest tests/test_bazi_engine.py  # 100% 通过
```

### Phase 2-3：规则库 + 证据层（6周）
```bash
# 1. 录入规则
# knowledge/rules/ditian.py

# 2. 实现证据层
# knowledge/evidence/facts.py
# knowledge/evidence/matcher.py
# knowledge/evidence/chain.py

# 3. 测试
pytest tests/test_evidence.py
```

### Phase 4-6：推理能力（2个月）
```bash
# 实现 Reasoning + Critic + Time Engine
pytest tests/test_reasoning.py
```

### Phase 7：评估体系（1个月）
```bash
# 集成 MingLi-Bench
python scripts/run_benchmark.py

# 目标：准确率 > 40%
```

---

## 如何贡献

### 贡献规则库

最有价值的贡献是补充传统命理规则：

```python
# knowledge/rules/ditian.py

RULE_017 = Rule(
    id="RULE_017",
    source="《滴天髓》卷二·官星章",
    school="classical",
    category="career",
    condition={
        "ten_god": {"正官": "month"},
        "strength": "medium"
    },
    conclusion="官星得令，宜从政或管理",
    confidence="MEDIUM",
    conflicts_with=["RULE_043"],  # 盲派不同看法
    evidence_required=["ten_god", "month_branch"]
)
```

### 贡献测试用例

```python
# tests/golden_cases/career.py

GOLDEN_CASES = [
    {
        "name": "某名人",
        "birth": BirthInput(...),
        "question": "事业如何？",
        "expected_facts": ["月柱正官透出", ...],
        "expected_rules": ["RULE_017", ...],
        "expected_conclusion": "适合从政",
    }
]
```

### 贡献流派系统

```python
# knowledge/schools/blind.py

class BlindSchool:
    """盲派命理体系"""
    
    def evaluate_strength(self, chart):
        """盲派的日主强弱判断法（与传统不同）"""
        pass
```

---

## 常见问题

### Q1：为什么不直接用 LLM 算命盘？

A：LLM 在数值计算上不可靠。八字排盘涉及：
- 立春分年（不是正月初一）
- 节气分月（不是农历月）
- 真太阳时校正（经度 + 均时差）
- 早晚子时判断

这些必须用确定性算法，否则排盘就是错的。

### Q2：为什么需要 Critic Agent？

A：单个 LLM 容易：
- 编造不存在的规则
- 跳过证据直接下结论
- 把低置信度说成确定性

Critic Agent 专门检查这些问题。

### Q3：为什么要区分流派？

A：传统命理本身存在不同理论体系：
- 子平正统：看格局用神
- 滴天髓派：看通关调候
- 盲派：看做功

同一命盘在不同流派下结论可能不同。必须告知用户这种差异，而不是假装只有一种正确答案。

### Q4：准确率能达到多少？

A：
- **排盘准确率**：100%（确定性计算）
- **MingLi-Bench 准确率**：目标 40%（MVP），长期 60%+
- **fate-bench 历史事件命中率**：目标 30%，长期 50%+

注意：命理推理本身就是不确定的，我们的目标不是"100% 准确预测"，而是"基于规则的可验证推理"。

### Q5：如何避免成为"迷信产品"？

A：
1. 明确定位为"推理工具"而非"预测工具"
2. 免责声明：仅供娱乐参考
3. 透明化：展示推理过程和证据强度
4. 不做确定性预测（用"证据强度 68%"而非"你一定会..."）
5. 标注流派冲突和不确定性

---

## 参考资料

### 必读文档
- [MINGLI_PLAN.md](../MINGLI_PLAN.md) - 完整执行计划
- [STRUCTURE.md](../STRUCTURE.md) - 项目结构
- [PHASE0_REPORT.md](../PHASE0_REPORT.md) - Phase 0 验收报告

### 参考项目
- [HeiGe-SuanMing](https://github.com/HeiGeAi/HeiGe-SuanMing) - 排盘引擎
- [MingLi-Bench](https://github.com/DestinyLinker/MingLi-Bench) - 评估基准
- [fate-bench](https://github.com/shunshi-ai/fate-bench) - 历史验证

### 经典文献
- 《渊海子平》- 子平体系基础
- 《滴天髓》- 用神理论
- 《子平真诠》- 格局理论
- 《三命通会》- 神煞体系

---

## 下一步

**当前状态**：Phase 0 完成 ✅

**立即行动**：
1. 阅读 [MINGLI_PLAN.md](../MINGLI_PLAN.md)
2. 克隆 HeiGe-SuanMing 到本地研究
3. 准备 Phase 1 开发环境

**预计时间线**：
- Phase 1：2周（排盘引擎）
- Phase 2-3：6周（规则库 + 证据层）
- Phase 4-6：2个月（推理能力）
- Phase 7：1个月（评估体系）

---

**最后更新**：2026-10-04  
**维护者**：MingLi Agent Team
