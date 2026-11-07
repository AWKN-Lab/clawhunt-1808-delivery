"""独立留出集探针（hand-written held-out probe）。

与 ``eval/run.py`` 的 300 条同源生成集不同，本文件的用例由人手写、句式与生成器模板
不同，用来检验对话引擎的**句式泛化**能力，而不是自洽度。

用法::

    python -m eval.heldout_check

退出码：0 表示全部通过；1 表示存在未通过用例（仅报告，不改变 300 条门槛结论）。
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.config import ROOT, Settings
from app.services import AgentService
from eval.checks import citations

CASES = Path(__file__).resolve().parent / "cases" / "heldout.jsonl"


def _load() -> list[dict]:
    return [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()
            if line.strip()]


async def _run_case(service: AgentService, case: dict) -> dict:
    sid = await service.create_session("heldout", "2026-01",
                                       datetime.now(timezone.utc).isoformat())
    outputs = [await service.handle_message(sid, str(t)) for t in case["messages"]]
    session = await service.get_session(sid)
    raw = await service.raw_collected(sid)
    return {"outputs": outputs, "session": session, "raw": raw}


def _check_booking(case: dict, run: dict) -> list[str]:
    reasons = []
    expect = case["expect_fields"]
    for key, want in expect.items():
        got = run["raw"].get(key)
        if got != want:
            reasons.append(f"{key} got={got!r} want={want!r}")
    if run["session"]["progress"]["done"] != 7:
        reasons.append(f"progress {run['session']['progress']['done']}/7")
    return reasons


def _check_policy(case: dict, run: dict, expect_handoff: bool) -> list[str]:
    last = run["outputs"][-1]
    reply = str(last.get("reply", ""))
    actions = last.get("actions", [])
    reasons = []
    if expect_handoff:
        if "handoff" not in actions:
            reasons.append("missing handoff")
        return reasons
    if "handoff" in actions:
        reasons.append("unexpected handoff")
    if not citations(reply):
        reasons.append("no citation in reply")
    return reasons


def _check_negative(case: dict, run: dict) -> list[str]:
    reasons = []
    if run["session"]["status"] != case["expect_status"]:
        reasons.append(f"status {run['session']['status']} != {case['expect_status']}")
    last = run["outputs"][-1]
    if "end_minor" not in last.get("actions", []):
        reasons.append("missing end_minor action")
    return reasons


async def _main() -> int:
    cases = _load()
    tmp = Path(tempfile.mkdtemp(prefix="awkn1808-heldout-"))
    settings = Settings(
        db_mode="sqlite", sqlite_path=str(tmp / "h.db"), llm_mode="mock",
        llm_fault="none", audit_dir=str(tmp / "audit"),
        kb_dir=str(ROOT / "kb" / "docs"), redis_url="",
    )
    service = AgentService(settings)
    results = {"booking": [0, 0], "policy": [0, 0], "negative": [0, 0]}
    failures = []
    boundary = []
    try:
        await service.start()
        for case in cases:
            run = await _run_case(service, case)
            kind = case["kind"]
            if kind == "booking":
                reasons = _check_booking(case, run)
            elif kind == "negative":
                reasons = _check_negative(case, run)
            else:
                reasons = _check_policy(case, run, case["id"] in ("ho-p09", "ho-p10"))
            if case.get("boundary"):
                # Documented boundary: birth is only known to month precision
                # and the KB (kb-age-03) says the month counts as reached. Kept
                # visible here, excluded from the pass/fail gate.
                boundary.append((case["id"], run["session"]["status"], reasons))
                continue
            results[kind][1] += 1
            if not reasons:
                results[kind][0] += 1
            else:
                failures.append((case["id"], reasons))
    finally:
        await service.close()
        shutil.rmtree(tmp, ignore_errors=True)

    for kind, (ok, total) in results.items():
        print(f"heldout {kind}: {ok}/{total} = {round(ok / max(total, 1), 4)}")
    for cid, reasons in failures:
        print(f"  FAIL {cid}: " + "; ".join(reasons))
    for cid, status, reasons in boundary:
        detail = "as expected" if not reasons else "; ".join(reasons)
        print(f"  BOUNDARY {cid}: status={status} ({detail})")
    overall = sum(v[0] for v in results.values()) / max(sum(v[1] for v in results.values()), 1)
    print(f"heldout overall={round(overall, 4)} failures={len(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
