from der.config import Settings
from der.domain.models import Plan, Step, Task, TaskStatus, new_id
from der.runtime.executor import Executor
from der.skills.builtin.bootstrap import build_context_store, build_registry

CFG = Settings(max_retries=0, context_budget=2048, reserved_output_tokens=0)


def _run():
    registry, _business = build_registry()
    task = Task(
        new_id("t_"), "处理售后工单",
        {"text": "商品有质量问题，希望退款", "order_id": "ORD-2026-001", "channel": "sms"},
        meta={"human_confirmed": True},
    )
    plan = Plan(task.task_id, [Step("s1", "classify_ticket"), Step("s2", "fetch_order")])
    executor = Executor(registry, build_context_store(task), cfg=CFG, backoff_base=0.0)
    return executor.run(task, plan=plan)


def test_react_thought_action_observation_trace():
    state = _run()
    assert state.status == TaskStatus.SUCCEEDED
    kinds = [e.kind for e in state.trace]
    assert kinds.count("react.thought") == 2
    assert kinds.count("react.observation") == 2
    assert kinds.count("step.succeeded") == 2
    assert not any(e.kind == "runtime.error" for e in state.trace)


def test_each_step_loads_only_its_declared_slices():
    state = _run()
    steps = state.context_report["steps"]
    assert steps[0]["loaded"] == ["ticket.intake", "customer.profile"]
    assert steps[1]["loaded"] == ["order.snapshot", "customer.history"]
    assert state.context_report["total_tokens"] == sum(s["tokens"] for s in steps)


def test_observation_written_back_is_summary_only():
    state = _run()
    for key, value in state.artifacts.items():
        if key.startswith("observation."):
            assert isinstance(value, str)
            assert len(value) < 200
