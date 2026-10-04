"""第一批结构规则样例。

这里只收录可由当前 Chart 事实直接验证的结构描述。经典文献的精确卷章和
版本需要后续逐条核校；在核校前，source 使用明确的“待校核”标记，不冒充
权威引文。
"""

from knowledge.rules import Rule, RuleRegistry

DEFAULT_RULES = (
    Rule(
        id="STRUCT_TEN_GOD_001",
        source="传统十神分类（待版本核校）",
        school="zi_ping_structural",
        category="ten_god",
        condition={"month_ten_god": "正官"},
        conclusion="月柱天干呈现正官关系；仅说明结构事实，不单独推出职业结论。",
        confidence="MEDIUM",
        evidence_required=("month_ten_god", "day_master"),
    ),
    Rule(
        id="STRUCT_RELATION_001",
        source="地支关系表（算法定义，待流派解释核校）",
        school="zi_ping_structural",
        category="relation",
        condition={"has_relation": "六冲"},
        conclusion="四支中存在六冲结构；具体取象需结合流派和其他证据。",
        confidence="HIGH",
        evidence_required=("relations",),
    ),
    Rule(
        id="STRUCT_RELATION_002",
        source="地支关系表（算法定义，待流派解释核校）",
        school="zi_ping_structural",
        category="relation",
        condition={"has_relation": "六合"},
        conclusion="四支中存在六合结构；具体取象需结合流派和其他证据。",
        confidence="HIGH",
        evidence_required=("relations",),
    ),
)


def default_registry() -> RuleRegistry:
    registry = RuleRegistry()
    registry.add_many(list(DEFAULT_RULES))
    return registry
