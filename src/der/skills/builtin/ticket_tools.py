"""售后工单场景的核心业务 Skills。

每个 Skill 只实现「这件事怎么做」；调度、上下文加载、状态与回滚全部由 runtime 负责。
"""

from __future__ import annotations

from der.domain.errors import NeedsHumanError, NonRetryableError
from der.domain.models import RiskLevel, SkillKind, SkillSpec

from ..base import BaseSkill, SkillContext, SkillResult
from .store import BusinessStore


class ClassifyTicket(BaseSkill):
    spec = SkillSpec(
        name="classify_ticket",
        kind=SkillKind.TOOL,
        description="判定工单类型（退款 / 补发 / 投诉），只读、无副作用",
        required_context=("ticket.intake", "customer.profile"),
        produces=("ticket.category",),
        tags=("intake", "core"),
    )

    def _execute(self, ctx: SkillContext) -> SkillResult:
        ticket = ctx.require("ticket.intake")
        if any(k in ticket for k in ("破损", "少件", "补发", "换货")):
            category = "reship"
        elif any(k in ticket for k in ("投诉", "态度", "升级", "人工")):
            category = "complaint"
        else:
            category = "refund"
        return SkillResult(
            ok=True, data={"category": category, "confidence": 0.92},
            summary=f"工单归类为 {category}",
            artifact_updates={"ticket.category": category},
        )


class FetchOrder(BaseSkill):
    spec = SkillSpec(
        name="fetch_order",
        kind=SkillKind.API,
        description="从订单服务取回订单事实，供后续决策使用",
        required_context=("order.snapshot", "customer.history"),
        produces=("order.facts",),
        tags=("intake", "core"),
    )

    def __init__(self, store: BusinessStore) -> None:
        super().__init__()
        self.store = store

    def _execute(self, ctx: SkillContext) -> SkillResult:
        ctx.require("customer.history")
        order_id = ctx.task.payload.get("order_id", "ORD-2026-001")
        order = self.store.get_order(order_id)
        return SkillResult(
            ok=True, data=order, summary=f"取回订单 {order_id}",
            artifact_updates={"order.facts": order},
        )


class AssessPolicy(BaseSkill):
    spec = SkillSpec(
        name="assess_policy",
        kind=SkillKind.TOOL,
        description="按退款政策与 SLA 规则判定是否可自动执行；超额需人工确认",
        required_context=("policy.refund", "sla.rules", "audit.rules"),
        produces=("decision",),
        risk=RiskLevel.MEDIUM,
        tags=("decision", "core"),
    )

    AUTO_REFUND_LIMIT = 500.0

    def _execute(self, ctx: SkillContext) -> SkillResult:
        policy = ctx.require("policy.refund")
        ctx.require("audit.rules")
        facts = ctx.artifacts.get("order.facts", {})
        amount = float(facts.get("amount", 0))
        if amount > self.AUTO_REFUND_LIMIT and not ctx.task.meta.get("human_confirmed"):
            raise NeedsHumanError(
                f"退款金额 {amount} 超过自动额度 {self.AUTO_REFUND_LIMIT}，需人工确认"
            )
        return SkillResult(
            ok=True,
            data={"decision": "approve_refund", "amount": amount, "policy_seen": len(policy)},
            summary=f"策略判定通过，可自动退款 {amount}",
            artifact_updates={"decision": "approve_refund"},
        )


class Refund(BaseSkill):
    """高危、可补偿、幂等：失败后必须能把钱退回去。"""

    spec = SkillSpec(
        name="refund",
        kind=SkillKind.API,
        description="对已支付订单执行退款，返回可用于回滚的补偿闭包",
        required_context=("policy.refund", "order.snapshot"),
        produces=("refund.receipt",),
        retryable=True,
        compensatable=True,
        risk=RiskLevel.HIGH,
        tags=("execution", "core", "money"),
    )

    def __init__(self, store: BusinessStore) -> None:
        super().__init__()
        self.store = store

    def _execute(self, ctx: SkillContext) -> SkillResult:
        ctx.require("policy.refund")
        facts = ctx.artifacts.get("order.facts")
        if not facts:
            raise NonRetryableError("refund requires order.facts from fetch_order")
        key = ctx.idempotency_key
        receipt = self.store.refund(facts["order_id"], key)
        return SkillResult(
            ok=True, data=receipt, summary=f"退款成功 {receipt['refund_id']}",
            artifact_updates={"refund.receipt": receipt},
            compensation=lambda: self.store.undo_refund(key),  # 逆序回滚时调用
        )


class Reship(BaseSkill):
    """Workflow 型能力：声明依赖，由 Registry 做拓扑排序后组合执行。"""

    spec = SkillSpec(
        name="reship",
        kind=SkillKind.WORKFLOW,
        description="依据补发政策创建补发单，依赖 fetch_order 提供的订单事实",
        required_context=("policy.reship", "order.snapshot"),
        depends_on=("fetch_order",),
        produces=("reship.receipt",),
        compensatable=True,
        risk=RiskLevel.MEDIUM,
        tags=("execution", "core"),
    )

    def __init__(self, store: BusinessStore) -> None:
        super().__init__()
        self.store = store

    def _execute(self, ctx: SkillContext) -> SkillResult:
        ctx.require("policy.reship")
        facts = ctx.artifacts.get("order.facts")
        if not facts:
            raise NonRetryableError("reship requires order.facts")
        key = ctx.idempotency_key
        receipt = self.store.create_reship(facts["order_id"], key)
        return SkillResult(
            ok=True, data=receipt, summary=f"补发单已创建 {receipt['reship_id']}",
            artifact_updates={"reship.receipt": receipt},
            compensation=lambda: self.store.undo_reship(key),
        )


class EscalateToHuman(BaseSkill):
    spec = SkillSpec(
        name="escalate_to_human",
        kind=SkillKind.API,
        description="按升级矩阵把复杂投诉转交人工队列，并保留完整上下文引用",
        required_context=("escalation.matrix", "customer.history"),
        produces=("escalation.ticket",),
        risk=RiskLevel.MEDIUM,
        tags=("execution", "core"),
    )

    def __init__(self, store: BusinessStore) -> None:
        super().__init__()
        self.store = store

    def _execute(self, ctx: SkillContext) -> SkillResult:
        matrix = ctx.require("escalation.matrix")
        facts = ctx.artifacts.get("order.facts", {})
        record = self.store.escalate(
            facts.get("order_id", "unknown"),
            f"{ctx.task.goal} | matrix_len={len(matrix)}",
        )
        return SkillResult(
            ok=True, data=record, summary="已转人工 L2 队列",
            artifact_updates={"escalation.ticket": record},
        )