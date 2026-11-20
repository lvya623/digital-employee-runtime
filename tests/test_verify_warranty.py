"""小卡 · 第 2 张：给新本事配一条验收。

这一站只测 CheckWarranty 自己，不碰注册中心——所以不用改 bootstrap.py。
跑完 pytest 从 24 passed 变成 25 passed，这个数字变化就是「我动过它」的硬证据。
"""

from __future__ import annotations

from der.context import ContextSlice, ContextStore, ProgressiveContextLoader
from der.domain.models import Step, Task, new_id
from der.skills.base import SkillContext
from der.skills.builtin.verify_warranty import CheckWarranty


def test_check_warranty_is_readonly_and_isolated():
    # 复用项目里真实的商品知识片，再故意混一片无关知识，
    # 验证「只领自己声明过的那片，不把整摞资料搬进来」。
    store = ContextStore([
        ContextSlice("kb.product", "降噪耳机支持一年内非人为损坏保修；配件缺失属于少件，走补发流程。"),
        ContextSlice("tone.guide", "回复话术：先给结论再给依据，全文控制在 120 字以内。"),
    ])
    loader = ProgressiveContextLoader(store, max_tokens=2048, reserved_output=0)
    loaded = loader.load_for(CheckWarranty.spec)
    assert set(loaded.slices) == {"kb.product"}
    assert "tone.guide" not in loaded.prompt

    # 正常路径：只查、只给结论，不动钱不发短信。
    task = Task(new_id("t_"), "校验保修", {"text": "耳机无法连接", "days_since_delivery": 30})
    step = Step("s1", "check_warranty")
    ctx = SkillContext(
        task=task,
        step=step,
        slices=loaded.slices,
        artifacts={"order.facts": {"days_since_delivery": 30}},
        memory={},
        idempotency_key=f"{task.task_id}:{step.step_id}",
    )
    result = CheckWarranty().run(ctx)
    assert result.ok, result.error
    assert result.data["eligible"] is True
    assert result.data["days"] == 30

    # 缺了声明的那片纸，必须显式失败，且不可重试（确定性错误，重试没意义）。
    broken_ctx = SkillContext(
        task=task, step=step, slices={}, artifacts={}, memory={}, idempotency_key="k"
    )
    failed = CheckWarranty().run(broken_ctx)
    assert not failed.ok
    assert not failed.retryable
    assert "kb.product" in (failed.error or "")
