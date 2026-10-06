"""紫微斗数排盘：安命身宫、十二宫干支、十四主星、六吉六煞、禄存天马与生年四化。

安星规则取自《紫微斗数全书》安星诀，宫位下标以寅为 0、顺时针递增。
排盘是确定性计算，不作近似；闰月归属与晚子时的流派差异以策略参数显式声明。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import sxtwl

from engines.bazi.models import BirthInput
from engines.bazi.strategies import StrategyContext
from engines.bazi.sxtwl_provider import BRANCHES, STEMS, na_yin
from engines.ziwei.models import PALACE_NAMES, Palace, ZiweiChart

VERSION = "ziwei_v1"

LEAP_POLICIES = ("split", "preceding", "following")

# 定寅首（五虎遁）：甲己之年丙作首，乙庚之年戊为头，其余顺推。
TIGER_RULE = ("丙", "戊", "庚", "壬", "甲", "丙", "戊", "庚", "壬", "甲")

# 十干四化，顺序为化禄、化权、化科、化忌。
MUTAGEN_TABLE: dict[str, tuple[str, str, str, str]] = {
    "甲": ("廉贞", "破军", "武曲", "太阳"),
    "乙": ("天机", "天梁", "紫微", "太阴"),
    "丙": ("天同", "天机", "文昌", "廉贞"),
    "丁": ("太阴", "天同", "天机", "巨门"),
    "戊": ("贪狼", "太阴", "右弼", "天机"),
    "己": ("武曲", "贪狼", "天梁", "文曲"),
    "庚": ("太阳", "武曲", "太阴", "天同"),
    "辛": ("巨门", "太阳", "文曲", "文昌"),
    "壬": ("天梁", "紫微", "左辅", "武曲"),
    "癸": ("破军", "巨门", "太阴", "贪狼"),
}
MUTAGEN_NAMES = ("化禄", "化权", "化科", "化忌")

# 定禄存（按年干）：甲禄到寅宫，乙禄居卯府，丙戊禄在巳，丁己禄在午……
LU_CUN = ("寅", "卯", "巳", "午", "巳", "午", "申", "酉", "亥", "子")
# 安天魁天钺（按年干）：甲戊庚牛羊，乙己鼠猴乡，丙丁猪鸡位，辛年午寅，壬癸兔蛇藏。
KUI_YUE = (
    ("丑", "未"),
    ("子", "申"),
    ("亥", "酉"),
    ("亥", "酉"),
    ("丑", "未"),
    ("子", "申"),
    ("丑", "未"),
    ("午", "寅"),
    ("卯", "巳"),
    ("卯", "巳"),
)
# 安天马（按年支）：寅午戌流马在申，申子辰在寅，巳酉丑在亥，亥卯未在巳。
TIAN_MA = {
    "寅": "申", "午": "申", "戌": "申",
    "申": "寅", "子": "寅", "辰": "寅",
    "巳": "亥", "酉": "亥", "丑": "亥",
    "亥": "巳", "卯": "巳", "未": "巳",
}
# 安火铃二耀（按年支定起子时位，顺数至时支）：申子辰寅戌、寅午戌丑卯、巳酉丑卯戌、亥卯未酉戌。
HUO_LING = {
    "寅": ("丑", "卯"), "午": ("丑", "卯"), "戌": ("丑", "卯"),
    "申": ("寅", "戌"), "子": ("寅", "戌"), "辰": ("寅", "戌"),
    "巳": ("卯", "戌"), "酉": ("卯", "戌"), "丑": ("卯", "戌"),
    "亥": ("酉", "戌"), "卯": ("酉", "戌"), "未": ("酉", "戌"),
}

JU_BY_ELEMENT = {"水": 2, "木": 3, "金": 4, "土": 5, "火": 6}
JU_NUMERALS = {2: "二", 3: "三", 4: "四", 5: "五", 6: "六"}
JU_BY_NAME = {
    f"{element}{JU_NUMERALS[number]}局": number for element, number in JU_BY_ELEMENT.items()
}

# 安紫微诸星诀：紫微逆去天机星，隔一太阳武曲辰，连接天同空二宫，廉贞居处方是真。
ZIWEI_GROUP = ((0, "紫微"), (1, "天机"), (3, "太阳"), (4, "武曲"), (5, "天同"), (8, "廉贞"))
# 安天府诸星诀：天府顺行有太阴，贪狼而后巨门临，随来天相天梁继，七杀空三是破军。
TIANFU_GROUP = (
    (0, "天府"),
    (1, "太阴"),
    (2, "贪狼"),
    (3, "巨门"),
    (4, "天相"),
    (5, "天梁"),
    (6, "七杀"),
    (10, "破军"),
)

MAJOR_STAR_NAMES = frozenset(name for _, name in ZIWEI_GROUP) | frozenset(
    name for _, name in TIANFU_GROUP
)


def _palace_branch(index: int) -> str:
    """宫位下标转地支：寅为 0，卯为 1，依此类推。"""
    return BRANCHES[(index + 2) % 12]


def _palace_index(branch: str) -> int:
    """地支转宫位下标：寅为 0，顺时针递增。"""
    return (BRANCHES.index(branch) - 2) % 12


def five_element_class(stem: str, branch: str) -> str:
    """以命宫干支纳音定五行局，如甲子海中金为金四局。"""
    element = na_yin(stem, branch)[-1]
    return f"{element}{JU_NUMERALS[JU_BY_ELEMENT[element]]}局"


def ziwei_index(number: int, day: int) -> str:
    """起紫微星诀：局数除日数取商，凑足整除的加数偶则顺行、奇则逆行；返回地支。"""
    offset = 0
    while (day + offset) % number:
        offset += 1
    quotient = (day + offset) // number
    step = -offset if offset % 2 else offset
    return _palace_branch((quotient + step - 1) % 12)


def tianfu_index(ziwei: str) -> str:
    """天府与紫微起于同一寅轴、行进方向相反：紫微在寅则天府在寅，在卯则在丑。"""
    return _palace_branch((-_palace_index(ziwei)) % 12)


class ZiweiCalculator:
    """排本命盘；不含大限流年，不对任何星曜作吉凶判断。"""

    def calculate(
        self,
        birth: BirthInput | dict[str, Any],
        *,
        leap_month: str = "split",
        late_zi_next_day: bool = True,
    ) -> ZiweiChart:
        if isinstance(birth, dict):
            birth = BirthInput(**birth)
        if leap_month not in LEAP_POLICIES:
            raise ValueError(f"leap_month 只能是 {'、'.join(LEAP_POLICIES)}。")

        day_info = sxtwl.fromSolar(birth.year, birth.month, birth.day)
        lunar_year = day_info.getLunarYear()
        lunar_month = day_info.getLunarMonth()
        lunar_day = day_info.getLunarDay()
        is_leap = day_info.isLunarLeap()
        late_zi = birth.hour >= 23
        hour_index = ((birth.hour + 1) // 2) % 12

        month_index = self._month_index(lunar_month, lunar_day, is_leap, late_zi, leap_month)
        soul_index = (month_index - hour_index) % 12
        body_index = (month_index + hour_index) % 12

        year_stem = STEMS[(lunar_year - 4) % 10]
        year_branch = BRANCHES[(lunar_year - 4) % 12]
        yin_stem_index = STEMS.index(TIGER_RULE[STEMS.index(year_stem)])
        soul_stem = STEMS[(yin_stem_index + soul_index) % 10]
        soul_branch = _palace_branch(soul_index)

        ju_name = five_element_class(soul_stem, soul_branch)
        ziwei_day = lunar_day
        if late_zi and late_zi_next_day:
            tomorrow = date(birth.year, birth.month, birth.day) + timedelta(days=1)
            ziwei_day = sxtwl.fromSolar(tomorrow.year, tomorrow.month, tomorrow.day).getLunarDay()
        ziwei = ziwei_index(JU_BY_NAME[ju_name], ziwei_day)
        tianfu = tianfu_index(ziwei)

        stars = self._stars(year_stem, year_branch, month_index, hour_index, ziwei, tianfu)
        palaces = tuple(
            Palace(
                index=index,
                name=PALACE_NAMES[(index - soul_index) % 12],
                heavenly_stem=STEMS[(yin_stem_index + index) % 10],
                earthly_branch=_palace_branch(index),
                stars=tuple(stars[index]),
            )
            for index in range(12)
        )
        mutagens = dict(zip(MUTAGEN_TABLE[year_stem], MUTAGEN_NAMES, strict=True))

        return ZiweiChart(
            birth=birth,
            palaces=palaces,
            soul_index=soul_index,
            body_index=body_index,
            five_element_class=ju_name,
            lunar=(lunar_year, lunar_month, lunar_day, is_leap),
            mutagens=mutagens,
            context=self._context(leap_month, late_zi_next_day),
            evidence=(
                f"农历{lunar_year}年{'闰' if is_leap else ''}{lunar_month}月{lunar_day}日 "
                f"{BRANCHES[hour_index]}时",
                f"命宫{soul_stem}{soul_branch}，身宫{_palace_branch(body_index)}",
                f"{ju_name}（命宫干支纳音{na_yin(soul_stem, soul_branch)}）",
                f"紫微在{ziwei}，天府在{tianfu}",
                "生年"
                + year_stem
                + year_branch
                + "四化："
                + "、".join(
                    f"{star}{mutagen}"
                    for star, mutagen in zip(MUTAGEN_TABLE[year_stem], MUTAGEN_NAMES, strict=True)
                ),
            ),
        )

    @staticmethod
    def _month_index(
        lunar_month: int, lunar_day: int, is_leap: bool, late_zi: bool, leap_month: str
    ) -> int:
        """闰月归月策略：split 前半月算本月、后半月算下月；晚子时不改生月。"""
        if is_leap and leap_month == "following":
            lunar_month += 1
        elif is_leap and leap_month == "split" and lunar_day > 15 and not late_zi:
            lunar_month += 1
        return (lunar_month - 1) % 12

    @staticmethod
    def _stars(
        year_stem: str,
        year_branch: str,
        month_index: int,
        hour_index: int,
        ziwei: str,
        tianfu: str,
    ) -> list[list[str]]:
        stars: list[list[str]] = [[] for _ in range(12)]
        ziwei_at = _palace_index(ziwei)
        tianfu_at = _palace_index(tianfu)
        for offset, name in ZIWEI_GROUP:
            stars[(ziwei_at - offset) % 12].append(name)
        for offset, name in TIANFU_GROUP:
            stars[(tianfu_at + offset) % 12].append(name)

        # 六吉：左右按生月，昌曲按时支，魁钺按年干
        stars[(2 + month_index) % 12].append("左辅")
        stars[(8 - month_index) % 12].append("右弼")
        stars[(8 - hour_index) % 12].append("文昌")
        stars[(2 + hour_index) % 12].append("文曲")
        kui_branch, yue_branch = KUI_YUE[STEMS.index(year_stem)]
        stars[_palace_index(kui_branch)].append("天魁")
        stars[_palace_index(yue_branch)].append("天钺")

        # 禄存与羊陀按年干
        lu_at = _palace_index(LU_CUN[STEMS.index(year_stem)])
        stars[lu_at].append("禄存")
        stars[(lu_at + 1) % 12].append("擎羊")
        stars[(lu_at - 1) % 12].append("陀罗")

        # 六煞中的火铃按年支加时支，空劫按时支
        huo_start, ling_start = HUO_LING[year_branch]
        stars[(_palace_index(huo_start) + hour_index) % 12].append("火星")
        stars[(_palace_index(ling_start) + hour_index) % 12].append("铃星")
        hai_at = _palace_index("亥")
        stars[(hai_at - hour_index) % 12].append("地空")
        stars[(hai_at + hour_index) % 12].append("地劫")

        stars[_palace_index(TIAN_MA[year_branch])].append("天马")
        return stars

    @staticmethod
    def _context(leap_month: str, late_zi_next_day: bool) -> StrategyContext:
        return StrategyContext(
            school="三合派",
            policy=f"leap-{leap_month}|late-zi-{'next-day' if late_zi_next_day else 'current-day'}",
            version=VERSION,
            assumptions=(
                f"闰月出生的生月归属按「{leap_month}」：split=前半月归本月、后半月归下月，"
                "preceding=整月归本月，following=整月归下月。",
                "晚子时（23:00-24:00）"
                + ("按次日农历日起紫微" if late_zi_next_day else "按当日起紫微")
                + "；命身宫与辅曜仍按当日时辰起。",
                "年界取正月初一，用农历年干支定寅首与四化；立春分界的流派与此不同。",
                "仅排本命十二宫、十四主星、六吉六煞、禄存天马与生年四化；"
                "不含大限、流年、星曜亮度与其余杂曜。",
            ),
        )
