# Phase 0 验收报告

**项目名称**：MingLi Agent（命理智能体）  
**阶段**：Phase 0 - 项目规划  
**完成日期**：2026-10-04  
**状态**：✅ 完成

---

## 1. 修改了什么

### 新增文件
- `MINGLI_PLAN.md`：完整的 20 阶段执行计划
- `STRUCTURE.md`：项目结构说明和迁移策略
- `README.md`：全新的项目说明（覆盖原 CreatorOS 说明）

### 调研成果
- 完成 GitHub 和 X/Twitter 的系统调研
- 识别 7 个核心排盘引擎项目
- 识别 2 个紫微斗数引擎
- 识别 2 个评估基准系统
- 识别 6 个综合命理系统

### 架构设计
- 确定核心分层架构（Chart Tools → Evidence Layer → Reasoning/Critic）
- 设计 Evidence Layer（证据层）作为核心创新
- 设计流派系统处理理论冲突
- 设计双模型架构（Analyst + Critic）
- 设计三套 Benchmark 评估体系

---

## 2. 为什么修改

### 项目转型原因

**原方向**：CreatorOS（内容创作系统）
- 涉及多平台发布、内容策略、Analytics 等复杂业务
- 难以形成可验证的评估体系
- 与用户的核心需求（命理推理）不匹配

**新方向**：MingLi Agent（命理推理系统）
- 有明确的规则和评估基准（MingLi-Bench + fate-bench）
- 可以形成"计算 → 证据 → 推理 → 验证"的闭环
- 技术上更具挑战性和创新性（Evidence Layer）
- 更适合作为 Agent 系统的验证场景

### 核心创新：Evidence Layer

传统 AI 算命的问题：
```text
命盘 → LLM → "你今年财运不错"（黑盒，不可验证）
```

MingLi Agent 的解决方案：
```text
命盘 → 事实提取 → 规则匹配 → 证据链 → 结论（全程可追溯）
```

这是整个项目最重要的设计决策。

---

## 3. 文件清单

### 核心文档
```text
MINGLI_PLAN.md       # 完整执行计划（20个Phase，约5000行）
STRUCTURE.md         # 项目结构说明
README.md            # 项目说明（全新）
PHASE0_REPORT.md     # 本验收报告
```

### 保留文件
```text
PLAN.md              # 原 CreatorOS 计划（保留参考）
pyproject.toml       # 项目配置（保留）
requirements.txt     # 依赖（待更新）
.gitignore           # 版本控制（保留）
```

### 待创建目录（Phase 1+）
```text
engines/             # 排盘引擎
knowledge/           # 规则库、证据层
evaluation/          # 评估系统
api/                 # API 服务
web/                 # Web UI
docs/                # 文档
```

---

## 4. 数据结构

### 核心数据模型

#### 4.1 BirthInput（输入）
```python
@dataclass
class BirthInput:
    year: int           # 阳历年
    month: int          # 阳历月
    day: int            # 阳历日
    hour: int           # 时辰（0-23）
    minute: int         # 分钟
    longitude: float    # 经度（真太阳时校正）
    gender: str         # 性别（男/女）
```

#### 4.2 Chart（命盘）
```python
@dataclass
class Chart:
    pillars: List[Pillar]       # 四柱（年月日时）
    ten_gods: Dict              # 十神
    hidden_stems: Dict          # 藏干
    nayin: Dict                 # 纳音
    elements: Dict              # 五行强弱
    dayun: List[DaYun]          # 大运
    relations: List[Relation]   # 刑冲合害
```

#### 4.3 Fact（事实）
```python
@dataclass
class Fact:
    type: str           # ten_god / branch_relation / strength / element
    fact: str           # 具体事实描述
    chart_element: str  # 对应命盘要素
    confidence: float   # 0.0 - 1.0
```

#### 4.4 Rule（规则）
```python
@dataclass
class Rule:
    id: str                    # RULE_001
    source: str                # 《滴天髓》
    school: str                # classical / modern / blind
    category: str              # career / marriage / health
    condition: Dict            # 条件匹配
    conclusion: str            # 结论描述
    confidence: str            # HIGH / MEDIUM / LOW
    conflicts_with: List[str]  # 冲突规则ID
    evidence_required: List[str]
```

#### 4.5 Evidence（证据）
```python
@dataclass
class Evidence:
    topic: str                # career / marriage / health
    facts: List[Fact]         # 相关事实
    rules: List[str]          # 匹配的规则ID
    sources: List[str]        # 规则来源
    strength: float           # 证据强度（0.0-1.0）
    conflicts: List[str]      # 冲突规则
    school: str               # 采用的流派
```

#### 4.6 Analysis（分析结果）
```python
@dataclass
class Analysis:
    id: str
    user_id: str
    question: str
    chart: Chart
    facts: List[Fact]
    rules: List[str]
    evidence: Evidence
    conclusion: str
    strength: float
    critique: Critique
    created_at: datetime
```

---

## 5. API

### Phase 0 不涉及 API 实现

计划的 API 接口（Phase 10）：

```python
# 排盘
POST /api/chart
Input: BirthInput
Output: Chart

# 分析
POST /api/analyze
Input: Chart + Question
Output: Analysis

# 查询规则
GET /api/rules?category=career&school=classical

# 历史记录
GET /api/history/{user_id}
```

---

## 6. 测试结果

### Phase 0 测试项

Phase 0 是规划阶段，无代码实现，测试项为文档完整性检查：

- [x] MINGLI_PLAN.md 包含 20 个 Phase
- [x] 每个 Phase 有明确的目标和验收标准
- [x] 核心数据结构已定义
- [x] 技术栈已选型
- [x] 参考项目已调研
- [x] 架构图清晰
- [x] 风险已识别
- [x] 目标指标已设定

### 文档质量

| 指标 | 结果 |
|------|------|
| 计划完整性 | ✅ 20/20 Phase |
| 数据模型定义 | ✅ 6 个核心模型 |
| 参考项目调研 | ✅ 15+ 项目 |
| 架构设计 | ✅ 核心架构 + Evidence Layer |
| 风险识别 | ✅ 技术风险 + 产品风险 |
| 验收标准 | ✅ 每个 Phase 10 项清单 |

---

## 7. 构建结果

### Phase 0 无构建产物

当前项目仍保留原 CreatorOS 的运行环境：

```bash
# 虚拟环境可正常激活
source .venv/bin/activate

# 依赖可正常安装（未更新 requirements.txt）
pip install -r requirements.txt

# 原有测试可通过（未修改）
pytest tests/
```

### Phase 1 构建计划

Phase 1 需要：
1. 更新 `requirements.txt`（添加 HeiGe-SuanMing 相关依赖）
2. 创建 `engines/` 目录
3. 实现排盘引擎接口
4. 编写 100+ 排盘测试用例

---

## 8. 已知问题

### 8.1 原 CreatorOS 代码未清理

**问题**：项目中仍保留大量 CreatorOS 相关代码（内容创作、平台发布、Analytics 等）

**影响**：
- 代码仓库混乱
- 新开发者可能困惑项目定位
- 占用磁盘空间

**计划**：
- Phase 1-10：标记为 DEPRECATED，但保留
- Phase 11：统一清理废弃代码

### 8.2 技术栈尚未验证

**问题**：HeiGe-SuanMing 的集成方式未验证

**风险**：
- API 可能不兼容
- 性能可能不达标
- 测试覆盖可能不足

**应对**：Phase 1 第一周完成技术预研

### 8.3 规则库数据来源

**问题**：传统命理典籍的规则化方式未确定

**风险**：
- 规则提取可能耗时长
- 不同流派的规则可能冲突
- 规则置信度难以量化

**应对**：Phase 2 先实现 50 条基础规则，逐步扩展

### 8.4 LLM 幻觉控制

**问题**：即使有 Evidence Layer，LLM 仍可能编造规则

**风险**：
- 用户信任度降低
- 评估指标不达标

**应对**：
- Critic Agent 严格检查
- 规则白名单机制
- 持续监控幻觉率

### 8.5 评估基准的准入门槛

**问题**：MingLi-Bench 和 fate-bench 的准确率目标可能过高

**风险**：
- MVP 可能达不到 40% 准确率
- 历史事件验证可能难以实现

**应对**：
- 先以 20% 为 MVP 目标
- 逐步优化规则库
- 如果长期无法达标，考虑调整评估方式

---

## 9. 未实现功能

Phase 0 是规划阶段，以下所有功能均未实现：

### 核心功能（Phase 1-7）
- [ ] 排盘引擎
- [ ] 规则库
- [ ] 证据层
- [ ] 推理 Agent
- [ ] 审查 Agent
- [ ] 时间轴引擎
- [ ] 评估系统

### 产品功能（Phase 8-10）
- [ ] 用户记忆系统
- [ ] Web UI
- [ ] RESTful API

### 扩展功能（Phase 11-15）
- [ ] 紫微斗数
- [ ] 流年详批
- [ ] 合婚分析
- [ ] 择吉系统
- [ ] MCP Server

### 生产功能（Phase 16-20）
- [ ] 性能优化
- [ ] 安全加固
- [ ] 多语言支持
- [ ] 移动端
- [ ] 商业化

---

## 10. 下一阶段建议

### Phase 1 准备工作（本周）

#### 优先级 P0（必须完成）
1. **HeiGe-SuanMing 技术预研**
   - [ ] 克隆项目到本地
   - [ ] 阅读核心代码（`bazi/` 目录）
   - [ ] 运行原项目的 158 个八字测试
   - [ ] 确定集成方式（直接调用 / 适配器 / 重写）

2. **排盘引擎接口设计**
   - [ ] 定义 `engines/bazi/calculator.py` 接口
   - [ ] 确定输入输出格式
   - [ ] 设计错误处理机制

3. **测试用例准备**
   - [ ] 收集 100 个排盘测试用例（边界 case）
   - [ ] 定义测试格式（JSON / YAML）
   - [ ] 准备 golden cases（历史名人命盘）

#### 优先级 P1（建议完成）
4. **环境准备**
   - [ ] 更新 `requirements.txt`
   - [ ] 创建 `engines/` 目录结构
   - [ ] 设置 CI/CD（GitHub Actions）

5. **文档完善**
   - [ ] 编写 `docs/architecture.md`
   - [ ] 编写 `docs/bazi_engine.md`
   - [ ] 更新贡献指南

#### 优先级 P2（可选）
6. **社区调研**
   - [ ] 联系 HeiGe-SuanMing 作者
   - [ ] 查看 MingLi-Bench 最新进展
   - [ ] 加入相关技术社区

### Phase 1 执行（第 2-3 周）

**目标**：排盘引擎测试通过率 100%

**关键产出**：
- `engines/bazi/calculator.py`
- `engines/integrations/heige.py`
- `tests/test_bazi_engine.py`（100+ 测试）
- Phase 1 验收报告

**验收标准**：
1. 四柱计算准确率 100%
2. 十神计算准确率 100%
3. 大运计算准确率 100%
4. 真太阳时校正准确率 100%
5. 立春分界测试通过
6. 节气换月测试通过
7. 早晚子时测试通过
8. 闰月测试通过
9. 历史名人命盘对照通过（10个 golden cases）
10. API 文档完整

### Phase 2-3 展望（第 4-8 周）

**Phase 2：规则库**
- 录入 50+ 规则（优先《滴天髓》）
- 实现规则匹配引擎
- 设计流派系统

**Phase 3：证据层**
- 实现事实提取
- 实现规则匹配
- 实现证据链构建
- 实现证据强度计算

---

## 总结

### 完成情况

✅ **已完成**：
- 项目转型决策
- 完整执行计划（20 个 Phase）
- 核心架构设计（Evidence Layer）
- 技术选型和调研
- 数据模型设计
- 风险识别和应对

❌ **未完成**：
- 任何代码实现
- 依赖更新
- 环境配置

### 关键决策

1. **项目转型**：从 CreatorOS 转向 MingLi Agent
2. **核心创新**：Evidence Layer（证据层）
3. **技术选型**：HeiGe-SuanMing + FastAPI + React
4. **评估体系**：MingLi-Bench + fate-bench + 自建测试
5. **双模型架构**：Analyst + Critic

### 下一步

**Phase 1 启动时间**：2026-10-07（预计）  
**Phase 1 预计完成**：2026-10-21（2周）  
**Phase 2-3 预计完成**：2026-11-25（6周）

**Phase 0 状态**：✅ 完成，可以进入 Phase 1

---

**报告人**：Claude Code  
**审核人**：待确定  
**日期**：2026-10-04
