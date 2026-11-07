"""Knowledge base loader + deterministic BM25 retrieval.

Mock mode never free-generates policy answers: the answer is the matched KB
paragraph verbatim, plus its doc/chunk citation.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

POLICY_NOUNS = [
    "公积金", "年假", "户口", "期权", "股票", "加盟", "押金", "保证金",
    "培训费", "肖像", "签证", "五险一金", "落户", "贷款", "广告合作", "会员费",
]

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "age": ["年龄", "多大", "岁数", "未成年", "未满18", "满18", "几岁", "周岁"],
    "health": ["健康证", "体检", "办证"],
    "equipment": ["装备", "头盔", "保温箱", "工服", "雨衣", "充电宝", "电动车", "电瓶车", "新国标"],
    "station": ["站点", "网点", "门店", "报到", "分配", "调度", "地址"],
    "salary": ["薪资", "工资", "单价", "结算", "日结", "周结", "提成", "收入", "多少钱", "报酬"],
    "insurance": ["保险", "意外险", "社保", "工伤", "赔付", "理赔"],
    "leave": ["请假", "调休", "休假", "休息"],
    "resignation": ["离职", "离职后", "辞职", "不干了", "再入职", "退出", "离职工资", "离职结算"],
    "safety": [
        "安全", "培训", "事故", "受伤", "摔了", "摔伤", "交通规则",
        "逆行", "闯红灯", "违规", "停单", "处罚",
    ],
}


@dataclass
class Chunk:
    doc_id: str
    doc_key: str
    title: str
    topic: str
    chunk_id: str
    heading: str
    content: str
    ordinal: int


@dataclass
class PolicyAnswer:
    topic: str
    doc_id: str
    chunk_id: str
    title: str
    heading: str
    answer: str
    sources: list[dict[str, str]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "title": self.title,
            "heading": self.heading,
            "answer": self.answer,
            "sources": self.sources,
        }


QUESTION_RE = re.compile(
    r"(吗|呢|什么|怎么|如何|多少|多久|多大|哪些|哪个|哪里|在哪|谁|"
    r"能不能|可不可以|要不要|是否|几天|几点|什么时候|几岁|有没有|是不是|多少钱)"
)


def has_policy_intent(text: str) -> bool:
    if QUESTION_RE.search(text):
        return True
    return bool(re.search(r"(请问|想问|咨询|问一下|请教)", text))


def looks_like_policy_question(text: str) -> bool:
    """True when the message asks about policy the KB should answer."""
    if not has_policy_intent(text):
        return False
    if KnowledgeBase.detect_topic(text):
        return True
    return any(noun in text for noun in POLICY_NOUNS)


QUERY_EXPANSIONS: dict[str, list[str]] = {
    "多久": ["天", "工作日", "时间"],
    "几天": ["天", "工作日"],
    "什么时候": ["时间", "天"],
    "多少钱": ["费用", "元", "价格"],
    "多少": ["费用", "元", "价格", "收入"],
    "谁": ["审批", "站长"],
    "怎么": ["流程", "如何"],
    "能不能": ["可以", "是否"],
}


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for run in re.findall(r"[a-z0-9]+|[\u4e00-\u9fa5]+", text.lower()):
        if run.isascii():
            tokens.append(run)
        else:
            tokens.extend(list(run))
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def parse_document(path: Path) -> tuple[dict[str, Any], list[Chunk]]:
    raw = path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    body = raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            meta = yaml.safe_load(parts[1]) or {}
            body = parts[2]
    doc_key = str(meta.get("doc_id", path.stem))
    title = str(meta.get("title", path.stem))
    topic = str(meta.get("topic", ""))
    chunks: list[Chunk] = []
    current_id: str | None = None
    current_heading = ""
    buffer: list[str] = []
    ordinal = 0

    def flush() -> None:
        nonlocal ordinal, buffer, current_id, current_heading
        if current_id is not None:
            content = " ".join(part.strip() for part in buffer if part.strip()).strip()
            ordinal += 1
            chunks.append(
                Chunk(
                    doc_id=doc_key,
                    doc_key=doc_key,
                    title=title,
                    topic=topic,
                    chunk_id=current_id,
                    heading=current_heading,
                    content=content,
                    ordinal=ordinal,
                )
            )
        buffer = []

    for line in body.splitlines():
        match = re.match(r"^###\s+([A-Za-z0-9-]+)\s+(.+?)\s*$", line)
        if match:
            flush()
            current_id = match.group(1)
            current_heading = match.group(2)
            continue
        if current_id is not None:
            buffer.append(line)
    flush()
    return meta, chunks


class KnowledgeBase:
    def __init__(self, kb_dir: str) -> None:
        self.kb_dir = Path(kb_dir)
        self.chunks: list[Chunk] = []
        for path in sorted(self.kb_dir.glob("*.md")):
            _, chunks = parse_document(path)
            self.chunks.extend(chunks)
        if len({chunk.doc_key for chunk in self.chunks}) < 9:
            raise RuntimeError("knowledge base must contain at least 9 documents")
        self._docs: dict[str, dict[str, str]] = {}
        for chunk in self.chunks:
            self._docs[chunk.doc_key] = {
                "doc_id": chunk.doc_id,
                "title": chunk.title,
                "topic": chunk.topic,
            }
        self.chunk_by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        self._corpus = [
            _tokenize(f"{chunk.heading} {chunk.heading} {chunk.heading} {chunk.content}")
            for chunk in self.chunks
        ]
        self._doc_len = [len(tokens) for tokens in self._corpus]
        self._avg_len = sum(self._doc_len) / max(len(self._doc_len), 1)
        self._tf = [Counter(tokens) for tokens in self._corpus]
        df: Counter[str] = Counter()
        for tokens in self._tf:
            for token in set(tokens):
                df[token] += 1
        total = len(self._tf)
        self._idf = {
            token: math.log(1 + (total - freq + 0.5) / (freq + 0.5))
            for token, freq in df.items()
        }

    # ------------------------------------------------------------------
    def docs(self) -> list[dict[str, str]]:
        return list(self._docs.values())

    def chunk_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "title": chunk.title,
                "topic": chunk.topic,
                "heading": chunk.heading,
                "content": chunk.content,
                "ordinal": chunk.ordinal,
            }
            for chunk in self.chunks
        ]

    # ------------------------------------------------------------------
    @staticmethod
    def detect_topic(text: str) -> str | None:
        scores: dict[str, int] = {}
        earliest: dict[str, int] = {}
        for topic, keywords in TOPIC_KEYWORDS.items():
            for keyword in keywords:
                position = text.find(keyword)
                if position >= 0:
                    scores[topic] = scores.get(topic, 0) + 1
                    earliest[topic] = min(earliest.get(topic, 10**6), position)
        if not scores:
            return None
        return max(scores, key=lambda topic: (scores[topic], -earliest[topic]))

    def _bm25(self, query_tokens: list[str], index: int) -> float:
        k1, b = 1.2, 0.75
        score = 0.0
        doc_len = self._doc_len[index]
        tf = self._tf[index]
        for token in query_tokens:
            if token not in tf:
                continue
            idf = self._idf.get(token, 0.0)
            freq = tf[token]
            denominator = freq + k1 * (1 - b + b * doc_len / max(self._avg_len, 1))
            score += idf * freq * (k1 + 1) / denominator
        return score

    def answer(self, question: str) -> PolicyAnswer | None:
        topic = self.detect_topic(question)
        if topic is None:
            return None
        tokens = _tokenize(question)
        for marker, extra in QUERY_EXPANSIONS.items():
            if marker in question:
                tokens.extend(extra)
        candidates = [
            (index, chunk)
            for index, chunk in enumerate(self.chunks)
            if chunk.topic == topic
        ]
        scored = [(self._bm25(tokens, index), chunk) for index, chunk in candidates]
        if not scored:
            return None
        best_score, best_chunk = max(scored, key=lambda item: (item[0], -item[1].ordinal))
        if best_score <= 0:
            return None
        return PolicyAnswer(
            topic=topic,
            doc_id=best_chunk.doc_id,
            chunk_id=best_chunk.chunk_id,
            title=best_chunk.title,
            heading=best_chunk.heading,
            answer=best_chunk.content,
            sources=[{"doc_id": best_chunk.doc_id, "chunk_id": best_chunk.chunk_id}],
        )
