"""Dialogue state machine: 7 slots, policy QA, guardrails, downgrade."""
from __future__ import annotations

from typing import Any

from app.agent.audit import Audit
from app.agent.events import Outbox
from app.agent.guardrails import (
    REFUSAL_REPLY,
    SYSTEM_PROMPT,
    detect_injection,
    mask_name,
    mask_phone,
    redact_before_model,
)
from app.agent.handoff import detect_handoff
from app.agent.kb import KnowledgeBase, has_policy_intent, looks_like_policy_question
from app.agent.minor import age_at, is_minor
from app.agent.slots import (
    SLOT_LABELS,
    SLOT_ORDER,
    extract_slots,
)
from app.agent.vault import Vault
from app.llm.base import LLMError, LLMRequest, LLMTimeout
from app.models import MessageOut, Progress

FALLBACK_PREFIX = (
    "（模型服务暂时不可用，已保留你的填写进度并已申请转人工。"
    "你可以继续按提示填写，也可稍后由人工顾问联系你。）"
)

SLOT_QUESTIONS = {
    "name": "你好，我是骑手报名助手。请问怎么称呼你？",
    "birth_ym": "请告诉我你的出生年月，例如 1995-03。",
    "area_text": "你想在哪个区域跑单？请具体到街道或镇，例如“浦东新区张江镇”。",
    "job_type": "岗位意向是全职、兼职，还是待定？",
    "has_ebike": "你有自己的电动车吗？",
    "start_text": "大概什么时候能到岗？",
    "experience_text": "之前做过配送吗？大概做了多久？",
}

QUICK_REPLIES = {
    "name": ["我叫张三", "叫我小李"],
    "birth_ym": ["1995-03", "2000年6月"],
    "area_text": ["张江", "望京街道", "粤海街道"],
    "job_type": ["全职", "兼职", "待定"],
    "has_ebike": ["有电动车", "没有电动车", "公司配车"],
    "start_text": ["随时", "明天", "一周内", "下个月"],
    "experience_text": ["没做过", "做过1年", "做过3年"],
}

JOB_LABELS = {"fulltime": "全职", "parttime": "兼职", "undecided": "待定"}
HEALTH_LABELS = {
    "none": "无健康证",
    "holding": "已有健康证",
    "processing": "健康证办理中",
    "unknown": "健康证情况未说明",
}


def _filled_fields(collected: dict[str, Any]) -> list[str]:
    result = []
    for key in SLOT_ORDER:
        if key == "name":
            if collected.get("name_token"):
                result.append(key)
            continue
        if collected.get(key) is not None:
            result.append(key)
    return result


def _next_slot(collected: dict[str, Any]) -> str | None:
    filled = set(_filled_fields(collected))
    for key in SLOT_ORDER:
        if key not in filled:
            return key
    return None


class DialogueEngine:
    def __init__(
        self,
        db,
        kb: KnowledgeBase,
        vault: Vault,
        llm,
        audit: Audit,
        outbox: Outbox,
        settings,
    ) -> None:
        self.db = db
        self.kb = kb
        self.vault = vault
        self.llm = llm
        self.audit = audit
        self.outbox = outbox
        self.settings = settings

    # ------------------------------------------------------------------
    @staticmethod
    def _progress(collected: dict[str, Any]) -> Progress:
        fields = _filled_fields(collected)
        return Progress(done=len(fields), total=7, fields=fields)

    @staticmethod
    def _out(
        reply: str,
        quick_replies: list[str],
        collected: dict[str, Any],
        actions: list[str],
    ) -> dict[str, Any]:
        return MessageOut(
            reply=reply,
            quick_replies=quick_replies,
            progress=DialogueEngine._progress(collected),
            actions=actions,  # type: ignore[arg-type]
        ).model_dump()

    @staticmethod
    def _slot_display(key: str, value: Any) -> str:
        if key == "has_ebike":
            return "有电动车" if value else "没有电动车"
        if key == "job_type":
            return JOB_LABELS.get(str(value), str(value))
        return str(value)

    def build_candidate(
        self, session: dict[str, Any], collected: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        collected = collected if collected is not None else session["collected"]
        return {
            "name_token": collected.get("name_token"),
            "phone_token": collected.get("phone_token"),
            "birth_ym": collected.get("birth_ym"),
            "area_text": collected.get("area_text"),
            "job_type": collected.get("job_type"),
            "has_ebike": collected.get("has_ebike"),
            "start_text": collected.get("start_text"),
            "experience_text": collected.get("experience_text"),
            "health_cert": collected.get("health_cert", "unknown"),
            "source_channel": session["source_channel"],
            "status": "completed",
            "consent_version": session["consent_version"],
            "consent_at": session["consent_at"],
        }

    # ------------------------------------------------------------------
    async def handle(self, session: dict[str, Any], text: str) -> dict[str, Any]:
        sid = session["id"]
        status = session["status"]
        collected = dict(session["collected"] or {})

        if status == "end_minor":
            return self._out(
                "会话已结束：未满18周岁不能报名骑手，成年后再来吧。", [], collected, ["end_minor"]
            )
        if status == "handoff":
            return self._out("已转人工，人工顾问会尽快联系你。", [], collected, ["handoff"])
        if status == "completed":
            return self._out("报名已完成，如需修改信息请联系人工顾问。", [], collected, [])

        # 1) injection gate — no model call, no state change
        pattern_id = detect_injection(text)
        if pattern_id:
            self.audit.event(sid, "injection_blocked", pattern=pattern_id, text_len=len(text))
            masked = redact_before_model(text, [])["text"]
            await self.db.add_message(sid, "user", str(masked), pii_masked=False)
            await self.db.add_message(sid, "assistant", REFUSAL_REPLY, pii_masked=False)
            return self._out(REFUSAL_REPLY, [], collected, [])

        # 2) deterministic extraction (original text, before tokenisation)
        raw = extract_slots(text)
        replacements: list[tuple[str, str]] = []
        pii_found = False
        for value in raw.get("id_cards", []):  # type: ignore[union-attr]
            token = await self.vault.tokenize("id_card", str(value))
            replacements.append((str(value), token))
            pii_found = True
        for value in raw.get("phones", []):  # type: ignore[union-attr]
            token = await self.vault.tokenize("phone", str(value))
            replacements.append((str(value), token))
            collected["phone_token"] = token
            pii_found = True
        name = raw.get("name")
        if name:
            name_token = await self.vault.tokenize("name", str(name))
            replacements.append((str(name), name_token))
            collected["name_token"] = name_token

        # 3) handoff triggers (complaint / accident / price / offline trade)
        reason = detect_handoff(text)
        if reason:
            await self._persist(sid, status="handoff", collected=collected, ended_reason=reason)
            self.audit.event(sid, "handoff.requested", reason=reason)
            await self.outbox.emit(
                sid,
                "handoff.requested",
                {"session_id": sid, "reason": reason, "progress": self._progress(collected).model_dump()},
            )
            await self.db.add_message(sid, "user", str(redact_before_model(text, replacements)["text"]))
            reply = "已为你转接人工顾问，请稍候，人工会尽快联系你。"
            await self.db.add_message(sid, "assistant", reply)
            return self._out(reply, [], collected, ["handoff"])

        # 4) apply slots
        new_slots: list[str] = []
        for key in SLOT_ORDER:
            if key == "name":
                continue
            if key in raw:
                value = raw[key]
                if value is not None:
                    collected[key] = value
                    new_slots.append(key)
        if raw.get("health_cert"):
            collected["health_cert"] = raw["health_cert"]
        if name:
            new_slots.append("name")

        for key in new_slots:
            self.audit.event(sid, "slot.updated", field=key)

        # 5) minor gate — immediate terminal
        birth = collected.get("birth_ym")
        if birth and is_minor(str(birth)):
            reply = (
                f"抱歉，按出生年月 {birth} 计算你未满18周岁，不能报名骑手。"
                "报名流程已终止，成年后再来吧。"
            )
            await self._persist(sid, status="end_minor", collected=collected, ended_reason="minor")
            self.audit.event(sid, "end_minor", birth_ym=birth)
            await self.db.add_message(sid, "user", str(redact_before_model(text, replacements)["text"]))
            await self.db.add_message(sid, "assistant", reply)
            return self._out(reply, [], collected, ["end_minor"])

        # 6) policy QA (extractive) or KB miss -> handoff
        policy_intent = has_policy_intent(text)
        policy = self.kb.answer(text) if policy_intent else None
        policy_reply = ""
        actions: list[str] = []
        if policy is not None:
            policy_reply = f"{policy.answer}\n（出处：{policy.doc_id}｜{policy.chunk_id}）"
            if policy.topic == "station":
                actions.append("show_stations")
            self.audit.event(sid, "policy.answered", chunk_id=policy.chunk_id, doc_id=policy.doc_id)
        elif policy_intent and looks_like_policy_question(text):
            reason = "kb_miss"
            await self._persist(sid, status="handoff", collected=collected, ended_reason=reason)
            self.audit.event(sid, "handoff.requested", reason=reason)
            await self.outbox.emit(
                sid,
                "handoff.requested",
                {"session_id": sid, "reason": reason, "progress": self._progress(collected).model_dump()},
            )
            await self.db.add_message(sid, "user", str(redact_before_model(text, replacements)["text"]))
            reply = "这个问题知识库暂时没有答案，已为你转人工顾问，请稍候。"
            await self.db.add_message(sid, "assistant", reply)
            return self._out(reply, [], collected, ["handoff"])

        # 7) completion
        next_slot = _next_slot(collected)
        candidate = None
        if next_slot is None:
            candidate = self.build_candidate(session, collected)
            await self._persist(
                sid, status="completed", collected=collected, candidate=candidate
            )
            self.audit.event(sid, "candidate.completed", fields=_filled_fields(collected))
            await self.outbox.emit(sid, "candidate.completed", candidate)
            actions.append("booking_confirmed")
            masked_phone = ""
            phone_token = collected.get("phone_token")
            if phone_token:
                resolved = await self.vault.resolve(str(phone_token))
                masked_phone = f"手机号 {mask_phone(resolved[1])} 仅用于联系确认。" if resolved else ""
            display_name = "已登记"
            name_token = collected.get("name_token")
            if name_token:
                resolved_name = await self.vault.resolve(str(name_token))
                if resolved_name:
                    display_name = mask_name(resolved_name[1])
            reply_draft = (
                "报名信息已提交："
                f"称呼 {display_name}，"
                f"出生年月 {collected.get('birth_ym')}，"
                f"意向区域 {collected.get('area_text')}，"
                f"岗位 {JOB_LABELS.get(str(collected.get('job_type')), '')}，"
                f"车辆 {'有电动车' if collected.get('has_ebike') else '没有电动车'}，"
                f"到岗 {collected.get('start_text')}，"
                f"经验 {collected.get('experience_text')}。"
                f"{masked_phone}"
            )
            quick = ["查看附近站点", "转人工"]
        else:
            await self._persist(sid, collected=collected, candidate=None)
            bits = []
            if new_slots:
                values = []
                for key in new_slots:
                    if key == "name" and name:
                        values.append(f"{SLOT_LABELS[key]} {mask_name(str(name))}")
                    else:
                        values.append(
                            f"{SLOT_LABELS[key]} {self._slot_display(key, collected.get(key))}"
                        )
                bits.append("好的，已记录：" + "；".join(values) + "。")
            if raw.get("phones"):
                bits.append(
                    f"已收到联系方式，手机号 {mask_phone(str(raw['phones'][0]))} 仅用于联系确认。"
                )
            if policy_reply:
                bits.append(policy_reply)
            bits.append(SLOT_QUESTIONS[next_slot])
            reply_draft = "\n".join(bits)
            quick = QUICK_REPLIES.get(next_slot, [])

        # 8) model call with pre-model PII scrubbing (audit proves clean payload)
        safe_text = redact_before_model(text, replacements)["text"]
        await self.db.add_message(sid, "user", str(safe_text), pii_masked=pii_found)
        payload = {
            "model": self.settings.openai_model
            if self.settings.llm_mode == "openai"
            else "mock-rule-engine",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": safe_text},
            ],
            "context": {
                "next_slot": next_slot,
                "draft_text": reply_draft,
                "policy_sources": policy.sources if policy else [],
            },
            "temperature": 0.2,
        }
        self.audit.model_request(sid, str(payload["model"]), self.settings.llm_mode, payload)

        reply = reply_draft
        try:
            response = await self.llm.complete(
                LLMRequest(
                    system=SYSTEM_PROMPT,
                    user_text=str(safe_text),
                    context=payload["context"],
                    model=str(payload["model"]),
                )
            )
            reply = response.text.strip() or reply_draft
            if policy is not None and policy.chunk_id not in reply:
                reply = f"{reply}\n（出处：{policy.doc_id}｜{policy.chunk_id}）"
        except (LLMTimeout, LLMError) as exc:
            self.audit.event(sid, "model.fault", kind=type(exc).__name__, message=str(exc))
            reply = f"{FALLBACK_PREFIX}\n{reply_draft}"
            if "handoff" not in actions:
                actions.append("handoff")

        await self.db.add_message(sid, "assistant", reply)
        return self._out(reply, quick, collected, actions)

    # ------------------------------------------------------------------
    async def _persist(
        self,
        sid: str,
        *,
        status: str | None = None,
        collected: dict[str, Any] | None = None,
        candidate: dict[str, Any] | None = None,
        ended_reason: str | None = None,
    ) -> None:
        await self.db.update_session(
            sid,
            status=status,
            collected=collected,
            candidate=candidate,
            ended_reason=ended_reason,
        )
