"""把业务 Skills 注册进 Registry，并准备默认上下文切片。

这是整个仓库唯一允许 import 具体业务实现的地方（除 API 组装外）。
"""

from __future__ import annotations

from der.context import ContextSlice, ContextStore
from der.domain.models import Task
from der.skills import SkillRegistry

from .auxiliary import AuditLog, KnowledgeLookup, Notify, WriteReply
from .store import BusinessStore
from .verify_warranty import CheckWarranty
from .ticket_tools import (
    AssessPolicy,
    ClassifyTicket,
    EscalateToHuman,
    FetchOrder,
    Refund,
    Reship,
)

DEFAULT_SLICES: list[ContextSlice] = [
    ContextSlice(
        "customer.profile",
        "客户档案：林女士，注册 3 年，历史订单 14 笔，近 12 个月无争议记录，会员等级金卡，"
        "偏好短信通知，收货地址为上海市杨浦区。客户沟通偏好简洁、明确给出处理单号，"
        "避免使用模板化道歉话术。历史满意度评分 4.7/5，属于低风险客群。",
        stage="intake",
    ),
    ContextSlice(
        "customer.history",
        "历史工单摘要：2025-11 物流延误咨询，已闭环；2026-03 发票信息修改，已闭环；"
        "2026-07 商品使用咨询，已闭环。近 90 天无退款、无投诉、无升级记录。"
        "历史处理均由自动流程完成，未触发人工队列。",
        stage="intake",
    ),
    ContextSlice(
        "order.snapshot",
        "订单快照：ORD-2026-001，客户林女士，实付 268.00 元，商品为降噪耳机 x1，"
        "支付状态已支付，物流状态已签收，签收时间 2026-11-16，发票已开具。"
        "订单所属店铺为自营旗舰店，适用七日无理由与质量问题三十天换新政策。",
        stage="intake",
    ),
    ContextSlice(
        "policy.refund",
        "退款政策：已签收商品在七日内且不影响二次销售可申请无理由退款；"
        "经质检确认的质量问题全额退款且运费由商家承担。单笔金额不超过 500 元的"
        "退款可由数字员工自动执行；超过 500 元必须经人工复核后执行。"
        "退款原路退回，预计 1-3 个工作日到账。已开具发票的订单需同步红冲。",
        stage="decision",
    ),
    ContextSlice(
        "policy.reship",
        "补发政策：运输破损、少件、错发情形，客户上传照片并经系统核验后，"
        "可创建补发单，无需客户寄回原商品。补发单当日 18:00 前进入仓库作业队列，"
        "预计 48 小时内发出。同一订单 30 天内仅允许一次自动补发，"
        "第二次需人工审核。高价值商品（单价超过 1000 元）补发需复核。",
        stage="decision",
    ),
    ContextSlice(
        "sla.rules",
        "SLA 规则：售后工单首次响应不超过 10 分钟；自动处理链路端到端不超过 5 分钟；"
        "需人工介入的工单必须在 30 分钟内进入人工队列并附带完整执行轨迹。"
        "超过 SLA 的工单自动升级至值班主管，并在审计记录中标注超时原因。",
        stage="decision",
    ),
    ContextSlice(
        "audit.rules",
        "审计规则：所有涉及资金、发货、客户信息变更的操作必须记录任务 ID、步骤 ID、"
        "幂等键、操作前后状态与补偿结果。执行轨迹保留 180 天，可用于回放与争议举证。"
        "禁止在日志中写入完整手机号、银行卡号等敏感字段，需脱敏后记录。",
        stage="decision",
    ),
    ContextSlice(
        "kb.shipping",
        "物流知识：签收后 24 小时内反馈破损可走快速补发；外包装完好但内件破损"
        "需要客户提供开箱照片。补发包裹使用同一承运商，单号生成后自动同步到订单备注。"
        "偏远地区补发时效可能延长 1-2 天，需提前告知客户。",
        stage="aux",
    ),
    ContextSlice(
        "kb.product",
        "商品知识：降噪耳机支持一年内非人为损坏保修；配件缺失属于少件，走补发流程；"
        "耳机连接异常优先提供固件升级指引，不直接触发退款。商品序列号可在包装盒底部查看。",
        stage="aux",
    ),
    ContextSlice(
        "escalation.matrix",
        "升级矩阵：客户明确要求人工、涉及媒体曝光、同一问题三次以上重复反馈、"
        "金额超过 500 元、或政策未覆盖的例外情形，转人工 L2 队列。"
        "转人工时必须携带订单事实、已执行步骤与上下文引用，禁止让客户重复描述问题。",
        stage="execution",
    ),
    ContextSlice(
        "tone.guide",
        "回复话术：先给结论再给依据，一句话说明处理结果，明确给出处理单号与预计时效。"
        "不使用「非常抱歉给您带来不便」等空泛模板，不承诺政策以外的补偿。"
        "全文控制在 120 字以内，结尾提供可直接回复的追问入口。",
        stage="output",
    ),
]


def build_context_store(task: Task | None = None) -> ContextStore:
    """把工单原文作为独立切片登记；其余知识片按阶段预置。"""
    store = ContextStore(list(DEFAULT_SLICES))
    text = (task.payload.get("text", "") if task else "") or "商品有质量问题，希望退款"
    store.add(ContextSlice("ticket.intake", text, stage="intake"))
    return store


def build_registry(store: BusinessStore | None = None) -> tuple[SkillRegistry, BusinessStore]:
    """注册全部能力。工厂闭包负责注入业务系统，编排层永远拿不到 store。"""
    business = store or BusinessStore()
    registry = SkillRegistry()

    registry.register(ClassifyTicket.spec, ClassifyTicket)
    registry.register(CheckWarranty.spec, CheckWarranty)
    registry.register(FetchOrder.spec, lambda s=business: FetchOrder(s))
    registry.register(AssessPolicy.spec, AssessPolicy)
    registry.register(Refund.spec, lambda s=business: Refund(s))
    registry.register(Reship.spec, lambda s=business: Reship(s))
    registry.register(EscalateToHuman.spec, lambda s=business: EscalateToHuman(s))
    registry.register(KnowledgeLookup.spec, KnowledgeLookup)
    registry.register(WriteReply.spec, WriteReply)
    registry.register(Notify.spec, lambda s=business: Notify(s))
    registry.register(AuditLog.spec, lambda s=business: AuditLog(s))
    return registry, business
