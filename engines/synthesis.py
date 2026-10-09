"""跨体系解释 v1：可追溯的象征解读，不把象征当科学事实或互相验证。"""

from __future__ import annotations

from typing import Any

SIGN_THEMES = {
    "白羊座": "主动尝试、直接表达",
    "金牛座": "稳定积累、具体感受",
    "双子座": "交流信息、保持好奇",
    "巨蟹座": "照顾关系、寻找归属",
    "狮子座": "创造表达、获得认可",
    "处女座": "整理细节、改进方法",
    "天秤座": "协调关系、权衡选择",
    "天蝎座": "深入探索、建立信任",
    "射手座": "拓展视野、寻找意义",
    "摩羯座": "承担责任、长期建设",
    "水瓶座": "独立思考、探索新方式",
    "双鱼座": "想象共情、感受边界",
}
ELEMENT_THEMES = {
    "木": "生长与规划",
    "火": "表达与连接",
    "土": "承接与稳定",
    "金": "取舍与边界",
    "水": "观察与流动",
}


def explain(
    question: str, bazi: dict | None, ziwei: dict | None, western: dict, unavailable: list[str]
) -> dict[str, Any]:
    evidence = []
    readings = []

    def add(identity, system, fact, interpretation):
        evidence.append({"id": identity, "system": system, "fact": fact})
        readings.append(
            {
                "system": system,
                "evidence_ids": [identity],
                "text": interpretation,
                "rule_id": "synthesis-symbolic-v1",
            }
        )

    if bazi:
        element = bazi["elements"]["day_master_element"]
        add(
            "bazi.day_master",
            "八字",
            f"日主 {bazi['day_master']}，五行 {element}",
            f"在五行象征语言中，{element}常用于讨论{ELEMENT_THEMES[element]}。"
            "这是观察角度，不能仅凭日主判定旺衰、喜用或性格。",
        )
    if ziwei:
        palace = ziwei["palaces"][ziwei["soul_index"]]
        stars = "、".join(palace["stars"]) or "无已排星曜"
        add(
            "ziwei.soul",
            "紫微",
            f"命宫 {palace['heavenly_stem']}{palace['earthly_branch']}，星曜 {stars}",
            f"紫微以宫位和星曜组合组织人生主题。当前命宫包含{stars}，"
            "可从自我定位与承担的角色切入；单个宫位不足以断定成就或命运。",
        )
    for body, label in (("sun", "太阳"), ("moon", "月亮"), ("ascendant", "上升")):
        p = western.get(body)
        if not p:
            continue
        candidates = p["possible_signs"]
        sign = p["sign"]
        role = {"sun": "自我表达", "moon": "情绪需求", "ascendant": "初始应对方式"}[body]
        text = (
            f"在西方占星的象征语言中，{label}对应{role}；{sign}可用于探索{SIGN_THEMES[sign]}。"
            if sign
            else f"{label}存在{' / '.join(candidates)}候选，暂不选择一个星座作解释。"
        )
        add(f"western.{body}", "西方星盘", f"{label}：{sign or ' / '.join(candidates)}", text)
    body_names = dict(
        sun="太阳",
        moon="月亮",
        mercury="水星",
        venus="金星",
        mars="火星",
        jupiter="木星",
        saturn="土星",
        uranus="天王星",
        neptune="海王星",
        pluto="冥王星",
    )
    if western.get("aspects"):
        aspect = western["aspects"][0]
        add(
            "western.aspect",
            "西方星盘",
            f"{' / '.join(body_names[body] for body in aspect['bodies'])} {aspect['name']}，容许度差 {aspect['orb_deg']:.2f}°",
            "相位描述两个天体位置的角距；象征上可用于探索不同需要如何互动，不能直接当作好坏结论。",
        )
    focus = "自我探索"
    title = "如何表达自己"
    prompt = "什么情况下你最能自然表达？外在角色和内在需要是否一致？"
    if any(word in question for word in ("关系", "感情", "伴侣", "沟通")):
        focus, title = "关系与沟通", "关系里的表达与边界"
        prompt = "在亲近关系中，你如何表达需要，又如何为彼此留出空间？"
    elif any(word in question for word in ("工作", "事业", "职业", "学习")):
        focus, title = "行动与角色", "找到适合自己的行动方式"
        prompt = "你当前承担的角色，是否允许你发挥自己的表达、规划和积累方式？"
    elif any(word in question for word in ("压力", "情绪", "焦虑", "节奏")):
        focus, title = "情绪与节奏", "压力之下，如何安顿自己"
        prompt = "什么情境容易消耗你？有哪些现实支持，能帮助你恢复日常节奏？"
    topics = [
        {
            "title": title,
            "prompt": prompt,
            "readings": [r for r in readings if "western.moon" not in r["evidence_ids"]],
        },
        {
            "title": "如何照顾自己的节奏",
            "prompt": "当压力增加，你需要独处、交流，还是更明确的边界？",
            "readings": [r for r in readings if r["system"] != "紫微"],
        },
    ]
    return {
        "version": "synthesis-symbolic-v1",
        "question": question,
        "focus": focus,
        "summary": "把不同体系当作几面镜子，分别观察表达、角色与需要，再用生活经验检验。",
        "themes": topics,
        "evidence": evidence,
        "unavailable": unavailable,
        "limits": [
            "出生事实与天文/历法计算，和象征性解释分开呈现。",
            "五行、星曜和西方元素不是同一套定义，不互相换算或互相证明。",
            "本版为固定、可追溯的探索框架，不是针对问题的预测或专业决策建议。",
        ],
    }
