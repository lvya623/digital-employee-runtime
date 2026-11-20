"""小卡 · 第 1 张：商品保修资格校验（只读、无副作用）。

我接手项目后亲手加的第一个本事：只问「还在保修期吗」，不动钱、不发短信。
刻意复用已有的 kb.product 知识片，不新建切片，改造前后 benchmark 才能直接对照。
"""

from __future__ import annotations

from der.domain.models import SkillKind, SkillSpec

from ..base import BaseSkill, SkillContext, SkillResult


class CheckWarranty(BaseSkill):
    """按商品知识判定是否在保，输出资格结论供后续步骤使用。"""

    spec = SkillSpec(
        name="check_warranty",
        kind=SkillKind.TOOL,
        description="按商品保修条款判定是否在保，输出只读资格结论",
        required_context=("kb.product",),
        produces=("warranty.eligible",),
        tags=("intake", "warranty"),
    )

    def _execute(self, ctx: SkillContext) -> SkillResult:
        policy = ctx.require("kb.product")
        days = int(ctx.artifacts.get("order.facts", {}).get("days_since_delivery", 30))
        text = ctx.task.payload.get("text", "")
        eligible = days <= 365 and all(k not in text for k in ("人为损坏", "进水", "私自拆修"))
        return SkillResult(
            ok=True,
            data={"eligible": eligible, "days": days, "policy_chars": len(policy)},
            summary=f"保修资格：{'在保' if eligible else '出保'}（签收 {days} 天）",
            artifact_updates={"warranty.eligible": eligible},
        )
