"""Deterministic slot extraction for the 7 booking slots.

Rules only: regex + keyword dictionaries + small alias tables. No model call,
no case-id branching, so the same engine is used by the API and the eval
harness.
"""
from __future__ import annotations

import re
from datetime import date

from app.agent.guardrails import find_id_cards, find_phone_numbers

SLOT_ORDER = [
    "name",
    "birth_ym",
    "area_text",
    "job_type",
    "has_ebike",
    "start_text",
    "experience_text",
]

SLOT_LABELS = {
    "name": "称呼",
    "birth_ym": "出生年月",
    "area_text": "意向区域（到街道）",
    "job_type": "岗位意向",
    "has_ebike": "车辆情况",
    "start_text": "到岗时间",
    "experience_text": "配送经验",
}

SURNAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐"
    "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄"
    "和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁"
    "杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍"
    "虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚"
    "程嵇邢滑裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓"
    "牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙"
    "叶幸司韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴胥能苍双闻"
    "莘党翟谭贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛寿通边扈燕冀郏浦尚农温"
    "别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡"
    "国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾"
    "毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"
)
COMPOUND_SURNAMES = {"欧阳", "司马", "上官", "诸葛", "东方", "独孤", "慕容", "皇甫", "尉迟"}

NAME_BLACKLIST = {
    "你好", "您好", "在吗", "谢谢", "可以", "好的", "不是", "是的", "没有",
    "全职", "兼职", "待定", "明天", "后天", "随时", "下周", "下月", "今天",
    "报名", "骑手", "外卖", "配送", "工资", "薪资", "保险", "安全", "站点",
    "健康", "证件", "身份", "手机", "电话", "身份", "区域", "师傅", "老板",
    "新手", "经验", "什么", "怎么", "多少", "哪里", "哪个", "为什么", "不知",
    "不清楚", "都行", "看情况", "电动车", "电瓶车", "健康证", "身份证",
    "明天", "今天", "后天", "周末", "到岗", "入职", "报到", "配车", "公司",
    "没车", "有车", "张江", "望京", "粤海", "石牌", "国贸", "陆家嘴",
    "徐家汇", "五角场", "三里屯", "华强北", "科技园", "滨江", "西溪",
    "天府", "光谷", "新街口",
}

NAME_PATTERNS = [
    re.compile(r"(?:我叫|我名字叫|名字叫)\s*([\u4e00-\u9fa5·]{2,4})"),
    re.compile(r"名字[是为：:]?\s*([\u4e00-\u9fa5·]{2,4})"),
    re.compile(r"姓名[是为：:]?\s*([\u4e00-\u9fa5·]{2,4})"),
    re.compile(r"(?:叫我|可以叫我)\s*(?:小)?([\u4e00-\u9fa5]{1,3})"),
    re.compile(r"我是\s*([\u4e00-\u9fa5·]{2,4})"),
]

BIRTH_SEP_RE = re.compile(
    r"((?:19|20)\d{2})\s*[年./\-]\s*(1[0-2]|0?[1-9])(?![\d./\-])"
)
BIRTH_Y2_RE = re.compile(r"(?<!\d)(\d{2})\s*年\s*(1[0-2]|0?[1-9])\s*月?")
BIRTH_YEAR_RE = re.compile(r"((?:19|20)\d{2})\s*年(?:出生|生)?")

CITIES = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京",
    "天津", "重庆", "苏州", "西安", "长沙", "郑州", "合肥", "济南",
]

AREA_ALIASES = {
    "张江": "上海市浦东新区张江镇",
    "陆家嘴": "上海市浦东新区陆家嘴街道",
    "五角场": "上海市杨浦区五角场街道",
    "徐家汇": "上海市徐汇区徐家汇街道",
    "望京": "北京市朝阳区望京街道",
    "三里屯": "北京市朝阳区三里屯街道",
    "国贸": "北京市朝阳区建外街道",
    "粤海": "深圳市南山区粤海街道",
    "科技园": "深圳市南山区粤海街道",
    "华强北": "深圳市福田区华强北街道",
    "石牌": "广州市天河区石牌街道",
    "天河城": "广州市天河区天河南街道",
    "滨江": "杭州市滨江区西兴街道",
    "西溪": "杭州市西湖区蒋村街道",
    "天府": "成都市高新区桂溪街道",
    "光谷": "武汉市洪山区关东街道",
    "新街口": "南京市秦淮区朝天宫街道",
}

AREA_FILLER_RE = re.compile(
    r"(我想在|我想去|我住在|住在|我在|想在|想去|意向区域|区域|安排|"
    r"附近|那边|这边|跑单|送外卖|工作|上班|的话|这边|在|去|到|就|是)"
)
DISTRICT_STREET_RE = re.compile(
    r"([\u4e00-\u9fa5]{2,6}?(?:区|县))([\u4e00-\u9fa5]{1,8}?(?:街道|镇|乡))"
)
STREET_ONLY_RE = re.compile(r"([\u4e00-\u9fa5]{2,6}?(?:街道|镇|乡))")

FULLTIME_RE = re.compile(r"(全职|专职|全日制|只做全职|全天)")
PARTTIME_RE = re.compile(r"(兼职|业余|周末|节假日|晚上跑|下班后|只做半天|半天)")
UNDECIDED_RE = re.compile(r"(待定|不确定|还没想好|没想好|都可以|都行|看情况|无所谓)")

VEHICLE_NO_RE = re.compile(
    r"(没有电动车|没电动车|没有电瓶车|没电瓶车|没有车|没车|无车|不带车|"
    r"不骑车|公司提供|公司配|站点提供|站点配|不打算买|不想买车|借车)"
)
VEHICLE_YES_RE = re.compile(
    r"(有电动车|有电瓶车|自带车|自带电动车|我自己有车|我有车|已经有车|"
    r"自己买车|会买车|有车|买了电动车|电动车是自己的)"
)

DATE_ISO_RE = re.compile(r"((?:19|20)\d{2})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])")
DATE_CN_RE = re.compile(r"(1[0-2]|0?[1-9])\s*月\s*(0?[1-9]|[12]\d|3[01])\s*[日号]")
AFTER_DAYS_RE = re.compile(r"(\d+|[一二三四五六七八九十两])\s*天(?:后|以后)")

START_KEYWORDS: list[tuple[str, str]] = [
    ("一个月内", "一个月内"),
    ("一个星期内", "一周内"),
    ("一周内", "一周内"),
    ("7天内", "一周内"),
    ("七天内", "一周内"),
    ("一周后", "一周内"),
    ("1周后", "一周内"),
    ("半个月", "半个月"),
    ("两周", "半个月"),
    ("2周", "半个月"),
    ("随时", "随时"),
    ("立刻", "随时"),
    ("马上", "随时"),
    ("现在", "随时"),
    ("今天", "随时"),
    ("明天", "明天"),
    ("后天", "后天"),
    ("下周", "下周"),
    ("下星期", "下周"),
    ("下个月", "下个月"),
    ("下月", "下个月"),
    ("月底", "月底"),
    ("月初", "月初"),
]

NO_EXPERIENCE_RE = re.compile(
    r"(没做过|没有经验|没经验|没相关经验|没有相关经验|没这方面经验|"
    r"没有任何经验|没啥经验|无经验|零经验|新手|第一次|没跑过|没干过|没送过)"
)
HALF_YEAR_RE = re.compile(r"(半年|半年多)")
MONTH_EXP_RE = re.compile(r"(\d+|[一二三四五六七八九十两])\s*个月(?:多)?")
YEAR_EXP_RE = re.compile(
    r"(?<!\d)(\d{1,2}|[一二三四五六七八九十两])\s*年(?:多)?(?:外卖|配送|骑手|跑单)?"
)

CN_NUM = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

HEALTH_PROCESSING_RE = re.compile(r"(正在办|办理中|在办|办着呢|还在办)")
HEALTH_HOLDING_RE = re.compile(r"(有健康证|已经办了|办好了|持有健康证|健康证有)")
HEALTH_NONE_RE = re.compile(r"(没有健康证|没健康证|还没办|没办|没有办)")
HEALTH_UNKNOWN_RE = re.compile(r"(不知道|不清楚|不了解|不确定)")


def _is_valid_name(value: str) -> bool:
    value = value.strip().replace("·", "")
    if not 2 <= len(value) <= 4:
        return False
    if value in NAME_BLACKLIST:
        return False
    if value[:2] in COMPOUND_SURNAMES:
        return True
    return value[0] in SURNAMES


def extract_name(text: str) -> str | None:
    for pattern in NAME_PATTERNS:
        match = pattern.search(text)
        if match:
            candidate = match.group(1).strip()
            if _is_valid_name(candidate):
                return candidate
    stripped = text.strip()
    # A bare reply is only treated as a name when it is short (2-3 chars) or a
    # 4-char compound-surname name. Otherwise slot words such as "明天到岗" or
    # "公司配车" would be misread as names.
    if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", stripped) and _is_valid_name(stripped):
        if len(stripped) <= 3 or stripped[:2] in COMPOUND_SURNAMES:
            return stripped
    return None


def _two_digit_year(yy: int) -> int:
    return 1900 + yy if yy >= 40 else 2000 + yy


def extract_birth(text: str) -> tuple[str, bool] | None:
    match = BIRTH_SEP_RE.search(text)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        return f"{year:04d}-{month:02d}", False
    match = BIRTH_Y2_RE.search(text)
    if match:
        year = _two_digit_year(int(match.group(1)))
        month = int(match.group(2))
        return f"{year:04d}-{month:02d}", False
    match = BIRTH_YEAR_RE.search(text)
    if match:
        year = int(match.group(1))
        if 1940 <= year <= date.today().year:
            return f"{year:04d}-01", True
    return None


def extract_area(text: str) -> str | None:
    for alias in sorted(AREA_ALIASES, key=len, reverse=True):
        if alias in text:
            return AREA_ALIASES[alias]

    cleaned = AREA_FILLER_RE.sub(" ", text)
    match = DISTRICT_STREET_RE.search(cleaned)
    if match:
        fragment = match.group(1) + match.group(2)
    else:
        match = STREET_ONLY_RE.search(cleaned)
        if not match:
            return None
        fragment = match.group(1)
    city_name = ""
    for name in CITIES:
        if name in text:
            city_name = name
            break
    city_full = city_name + "市" if city_name else ""
    if city_full and fragment.startswith(city_full):
        return fragment
    if city_name and fragment.startswith(city_name):
        fragment = fragment[len(city_name):]
    return f"{city_full}{fragment}" if city_full else fragment


def extract_job_type(text: str) -> str | None:
    if UNDECIDED_RE.search(text):
        return "undecided"
    full = bool(FULLTIME_RE.search(text))
    part = bool(PARTTIME_RE.search(text))
    if full and not part:
        return "fulltime"
    if part and not full:
        return "parttime"
    return None


def extract_vehicle(text: str) -> bool | None:
    if VEHICLE_NO_RE.search(text):
        return False
    if VEHICLE_YES_RE.search(text):
        return True
    return None


def _cn_num(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    return CN_NUM.get(value)


def extract_start(text: str) -> str | None:
    match = DATE_ISO_RE.search(text)
    if match:
        year, month, day = (int(g) for g in match.groups())
        return f"{year:04d}-{month:02d}-{day:02d}"
    match = DATE_CN_RE.search(text)
    if match:
        month, day = int(match.group(1)), int(match.group(2))
        year = date.today().year
        try:
            target = date(year, month, day)
        except ValueError:
            return None
        if target < date.today():
            year += 1
        return f"{year:04d}-{month:02d}-{day:02d}"
    match = AFTER_DAYS_RE.search(text)
    if match:
        number = _cn_num(match.group(1))
        if number:
            return f"{number}天后"
    for keyword, normalized in START_KEYWORDS:
        if keyword in text:
            return normalized
    return None


def extract_experience(text: str) -> str | None:
    if re.search(r"(到岗|入职|报到)", text) and not re.search(
        r"(做过|跑过|干了|送过|配送经验|骑手经验)", text
    ):
        # "一个月内到岗" is a start date, not delivery experience.
        return None
    if NO_EXPERIENCE_RE.search(text):
        return "无经验"
    if HALF_YEAR_RE.search(text):
        return "半年"
    match = MONTH_EXP_RE.search(text)
    if match:
        number = _cn_num(match.group(1))
        if number:
            return f"{number}个月"
    match = YEAR_EXP_RE.search(text)
    if match and "出生" not in text and "生日" not in text:
        number = _cn_num(match.group(1))
        if number:
            return f"{number}年"
    return None


def extract_health_cert(text: str) -> str | None:
    if HEALTH_PROCESSING_RE.search(text):
        return "processing"
    if HEALTH_HOLDING_RE.search(text):
        return "holding"
    if HEALTH_NONE_RE.search(text):
        return "none"
    if HEALTH_UNKNOWN_RE.search(text):
        return "unknown"
    return None


def extract_slots(text: str) -> dict[str, object]:
    """Extract whatever slots are present in one user message."""
    result: dict[str, object] = {}
    name = extract_name(text)
    if name:
        result["name"] = name
    birth = extract_birth(text)
    if birth:
        result["birth_ym"] = birth[0]
        result["birth_year_only"] = birth[1]
    area = extract_area(text)
    if area:
        result["area_text"] = area
    job = extract_job_type(text)
    if job:
        result["job_type"] = job
    vehicle = extract_vehicle(text)
    if vehicle is not None:
        result["has_ebike"] = vehicle
    start = extract_start(text)
    if start:
        result["start_text"] = start
    experience = extract_experience(text)
    if experience:
        result["experience_text"] = experience
    health = extract_health_cert(text)
    if health:
        result["health_cert"] = health
    phones = find_phone_numbers(text)
    if phones:
        result["phones"] = phones
    ids = find_id_cards(text)
    if ids:
        result["id_cards"] = ids
    return result


def filled_fields(collected: dict[str, object]) -> list[str]:
    return [key for key in SLOT_ORDER if key in collected and collected[key] is not None]


def next_missing(collected: dict[str, object]) -> str | None:
    for key in SLOT_ORDER:
        if key not in collected or collected[key] is None:
            return key
    return None
