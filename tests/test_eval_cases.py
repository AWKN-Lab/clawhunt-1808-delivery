"""Dataset composition and determinism checks (AC2)."""
from __future__ import annotations

import json
from pathlib import Path

CASES = Path(__file__).resolve().parent.parent / "eval" / "cases"


def _rows(name: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (CASES / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_case_composition() -> None:
    booking = _rows("booking.jsonl")
    policy = _rows("policy.jsonl")
    negative = _rows("negative.jsonl")
    injection = _rows("injection.jsonl")
    total = len(booking) + len(policy) + len(negative) + len(injection)
    assert total >= 300
    assert len(negative) >= 30
    assert len(injection) >= 10
    assert len({case["id"] for case in booking + policy + negative + injection}) == total


def test_policy_cases_cover_nine_topics() -> None:
    policy = _rows("policy.jsonl")
    assert {case["expect"]["topic"] for case in policy} == {
        "age", "health", "equipment", "station", "salary",
        "insurance", "leave", "resignation", "safety",
    }
    assert all(case["expect"]["doc_id"].startswith("kb-") for case in policy)
    assert all(case["expect"]["chunk_id"].startswith("kb-") for case in policy)


def test_injection_cases_all_expect_block() -> None:
    injection = _rows("injection.jsonl")
    assert all(case["expect"]["blocked"] is True for case in injection)
    assert len(injection) >= 10


def test_negative_cases_have_boundary_and_handoff() -> None:
    negative = _rows("negative.jsonl")
    statuses = {case["expect"]["status"] for case in negative}
    assert {"active", "handoff", "end_minor"} <= statuses
