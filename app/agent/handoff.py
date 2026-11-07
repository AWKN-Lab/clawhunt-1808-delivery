"""Handoff triggers: price negotiation / complaints / accident-injury."""
from __future__ import annotations

import re

OPTIONAL_MARKERS = ("如果", "假如", "万一", "要是", "假设", "流程", "规定", "政策")

HANDOFF_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "complaint",
        re.compile(r"(投诉|举报|差评|曝光|315|消协|退款不退|乱收费)"),
    ),
    (
        "accident",
        re.compile(
            r"(我|我们|刚才|刚刚|今天|现在|家人|同事|朋友)[^。！？\n]{0,12}"
            r"(受伤|摔伤|摔了|摔倒|骨折|车祸|撞车|出事故|流血|住院)"
        ),
    ),
    (
        "accident",
        re.compile(r"(报警|打120|叫救护车|正在医院|已经在医院)"),
    ),
    (
        "price",
        re.compile(
            r"(谈不拢|价格谈不|加钱|再高点|涨点工资|工资太低|太少了|"
            r"别家给|别家更高|更高价|能不能多给|补贴太少)"
        ),
    ),
    (
        "offline_trade",
        re.compile(r"(加你微信|加微信|私下|转账给你|线下付款|私聊成交)"),
    ),
    (
        "user_request",
        re.compile(r"(转人工|人工客服|人工服务|找人工|真人客服)"),
    ),
]


def detect_handoff(text: str) -> str | None:
    for reason, pattern in HANDOFF_PATTERNS:
        if pattern.search(text):
            if reason == "accident" and any(marker in text for marker in OPTIONAL_MARKERS):
                continue
            return reason
    return None
