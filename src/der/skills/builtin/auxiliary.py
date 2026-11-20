"""辅助与输出类 Skills。

注意：knowledge_lookup 是**可选**能力，不参与核心决策，也不直接生成答案。
这正是本项目与「RAG 问答系统」的分界线。
"""

from __future__ import annotations

from der.domain.models import SkillKind, SkillSpec

from ..base import BaseSkill, SkillContext, SkillResult
from .store import BusinessStore


class KnowledgeLookup(BaseSkill):
    spec = SkillSpec(
        name="knowledge_lookup",
        kind=SkillKind.TOOL,
        description="[辅助/非核心] 从知识切片中检索一句提示，仅作为后续 Skill 的输入",
        required_context=("kb.shipping", "kb.product"),
        produces=("kb.hint",),
        tags=("aux", "rag"),
    )

    def _execute(self, ctx: SkillContext) -> SkillResult:
        shipping = ctx.require("kb.shipping")
        product = ctx.require("kb.product")
        hint = "按标准售后流程处理"
        if "破损" in ctx.task.payload.get("text", "") and "补发" in shipping:
            hint = "破损类优先走补发流程，无需客户寄回"
        return SkillResult(
            ok=True, data={"hint": hint, "sources": ["kb.shipping", "kb.product"]},
            summary=f"辅助检索：{hint}",
            artifact_updates={"kb.hint": hint, "kb.product_len": len(product)},
        )


class WriteReply(BaseSkill):
    spec = SkillSpec(
        name="write_reply",
        kind=SkillKind.TOOL,
        description="按话术规范生成给客户的处理结果说明",
        required_context=("tone.guide", "customer.profile"),
        produces=("reply.text",),
        tags=("output", "core"),
    )

    def _execute(self, ctx: SkillContext) -> SkillResult:
        tone = ctx.require("tone.guide")
        receipts = ctx.artifacts.get("refund.receipt") or ctx.artifacts.get("reship.receipt") or {}
        facts = ctx.artifacts.get("order.facts", {})
        customer = facts.get("customer", "客户")
        content = (
            f"{customer}您好，您的工单已处理完成。"
            f"处理结果：{ctx.artifacts.get('ticket.category', '售后')}；"
            f"单号 {receipts.get('refund_id') or receipts.get('reship_id') or '已转人工'}。"
            "如有疑问可直接回复本消息。"
        )
        return SkillResult(
            ok=True, data={"reply": content, "tone_len": len(tone)},
            summary="已生成客户回复",
            artifact_updates={"reply.text": content},
        )


class Notify(BaseSkill):
    spec = SkillSpec(
        name="notify",
        kind=SkillKind.API,
        description="通过指定渠道把处理结果投递给客户；渠道临时不可用时可重试",
        required_context=("tone.guide",),
        produces=("notify.receipt",),
        retryable=True,
        tags=("output", "core"),
    )

    def __init__(self, store: BusinessStore) -> None:
        super().__init__()
        self.store = store

    def _execute(self, ctx: SkillContext) -> SkillResult:
        channel = ctx.task.payload.get("channel", "sms")
        content = ctx.artifacts.get("reply.text", "您的工单已处理完成")
        receipt = self.store.notify(channel, content, key=ctx.idempotency_key)
        return SkillResult(
            ok=True, data=receipt, summary=f"已通过 {channel} 通知客户",
            artifact_updates={"notify.receipt": receipt},
        )


class AuditLog(BaseSkill):
    spec = SkillSpec(
        name="audit_log",
        kind=SkillKind.TOOL,
        description="按审计规则记录本次执行摘要，供回放与复盘",
        required_context=("audit.rules",),
        produces=("audit.record",),
        tags=("output", "core"),
    )

    def __init__(self, store: BusinessStore) -> None:
        super().__init__()
        self.store = store

    def _execute(self, ctx: SkillContext) -> SkillResult:
        ctx.require("audit.rules")
        record = {
            "task_id": ctx.task.task_id,
            "category": ctx.artifacts.get("ticket.category"),
            "decision": ctx.artifacts.get("decision"),
            "receipts": {
                k: ctx.artifacts.get(k)
                for k in ("refund.receipt", "reship.receipt", "escalation.ticket")
                if ctx.artifacts.get(k)
            },
            "step": ctx.step.skill_name,
        }
        self.store.audit.append(record)
        return SkillResult(
            ok=True, data=record, summary="审计记录已落库",
            artifact_updates={"audit.record": record},
        )
