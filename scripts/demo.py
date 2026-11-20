"""一键演示：完整跑通一条数字员工执行链路，再演示失败回滚。

不依赖任何 API Key、数据库或外部服务。
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from der.config import Settings  # noqa: E402
from der.domain.models import Task, TaskStatus, new_id  # noqa: E402
from der.runtime.executor import Executor  # noqa: E402
from der.skills.builtin.bootstrap import build_context_store, build_registry  # noqa: E402
from der.skills.builtin.store import BusinessStore  # noqa: E402


def _task(text: str, channel: str = "sms", task_id: str | None = None) -> Task:
    return Task(
        task_id or new_id("task_"),
        "处理客户售后工单并给出处理结果",
        {"text": text, "order_id": "ORD-2026-001", "channel": channel},
        meta={"human_confirmed": True},
    )


def _print_state(label: str, state, business: BusinessStore) -> None:
    print(f"\n--- {label} ---")
    for event in state.trace:
        if event.kind == "plan.created":
            print("计划： " + " → ".join(event.detail["steps"]))
    for step in state.context_report.get("steps", []):
        print(f"  {step['skill']:<18} 加载 {len(step['loaded'])} 片 / {step['tokens']:>4} tokens")
    print(f"状态： {state.status.value}")
    print(f"轨迹事件： {len(state.trace)} 条 | 上下文合计： "
          f"{state.context_report.get('total_tokens', 0)} tokens")
    print(f"退款单：{len(business.refunds)} | 补发单：{len(business.reships)} | "
          f"通知：{len(business.notifications)} | 审计：{len(business.audit)}")
    if state.artifacts.get("reply.text"):
        print("客户回复： " + state.artifacts["reply.text"])


def main() -> None:
    print("=" * 68)
    print("Digital Employee Runtime · 售后工单数字员工")
    print("Task → Planning → ReACT → Skill → 输出（不是 RAG 问答）")
    print("=" * 68)

    registry, business = build_registry()
    cfg = Settings(max_retries=1, context_budget=2048, reserved_output_tokens=512)

    ok_task = _task("商品有质量问题，希望退款")
    ok_state = Executor(registry, build_context_store(ok_task), cfg=cfg,
                        backoff_base=0.0).run(ok_task)
    _print_state("场景 A：正常执行", ok_state, business)
    assert ok_state.status == TaskStatus.SUCCEEDED, "demo 应正常完成"

    before = len(business.refunds)
    bad_task = _task("商品有质量问题，希望退款", channel="")  # 通知渠道不可用
    bad_state = Executor(registry, build_context_store(bad_task), cfg=cfg,
                         backoff_base=0.0).run(bad_task)
    _print_state("场景 B：下游失败 → 逆序补偿回滚", bad_state, business)
    print(f"回滚校验：退款单 {before} → {len(business.refunds)}（应保持不变）")
    assert bad_state.status == TaskStatus.ROLLED_BACK
    assert len(business.refunds) == before, "失败必须回滚已产生的副作用"

    print("\n全部断言通过。下一步： python benchmarks/context_cost.py")


if __name__ == "__main__":
    main()
