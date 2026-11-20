import pytest

from der.config import Settings
from der.context import ContextSlice, ContextStore
from der.domain.errors import InvalidTransitionError
from der.domain.models import (
    ExecutionState,
    Plan,
    RiskLevel,
    SkillKind,
    SkillSpec,
    Step,
    Task,
    TaskStatus,
    new_id,
)
from der.runtime.executor import Executor
from der.skills import SkillRegistry
from der.skills.base import BaseSkill, SkillContext, SkillResult

LOG: list[str] = []


class OkWithCompensation(BaseSkill):
    spec = SkillSpec("ok_comp", SkillKind.API, "带补偿的成功步骤",
                     required_context=("a",), compensatable=True,
                     risk=RiskLevel.MEDIUM)

    def _execute(self, ctx: SkillContext) -> SkillResult:
        LOG.append("run")
        return SkillResult(ok=True, summary="done",
                           compensation=lambda: LOG.append("undo"))


class Failing(BaseSkill):
    spec = SkillSpec("fail", SkillKind.TOOL, "确定性失败",
                     required_context=("a",), retryable=False)

    def _execute(self, ctx: SkillContext) -> SkillResult:
        return SkillResult(ok=False, error="boom", retryable=False)


class Flaky(BaseSkill):
    spec = SkillSpec("flaky", SkillKind.API, "前两次暂时失败",
                     required_context=("a",), retryable=True)

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[int] = []

    def _execute(self, ctx: SkillContext) -> SkillResult:
        self.calls.append(1)
        if len(self.calls) < 3:
            return SkillResult(ok=False, error="temporary", retryable=True)
        return SkillResult(ok=True, summary="recovered")


class HighRisk(BaseSkill):
    spec = SkillSpec("high", SkillKind.API, "高危动作",
                     required_context=("a",), compensatable=True,
                     risk=RiskLevel.HIGH)

    def _execute(self, ctx: SkillContext) -> SkillResult:
        return SkillResult(ok=True, compensation=lambda: None)


CFG = Settings(max_retries=2, context_budget=2048, reserved_output_tokens=0,
               max_react_steps=12)


def _executor(*skills) -> Executor:
    reg = SkillRegistry()
    for cls in skills:
        obj = cls()
        reg.register(cls.spec, lambda o=obj: o)
    store = ContextStore([ContextSlice("a", "上下文A")])
    return Executor(reg, store, cfg=CFG, backoff_base=0.0)


def _task(**meta) -> Task:
    return Task(new_id("t_"), "测试任务", {}, meta=meta)


def test_failure_triggers_reverse_compensation():
    LOG.clear()
    task = _task()
    state = _executor(OkWithCompensation, Failing).run(
        task, plan=Plan(task.task_id, [Step("s1", "ok_comp"), Step("s2", "fail")])
    )
    assert state.status == TaskStatus.ROLLED_BACK
    assert LOG == ["run", "undo"]
    assert any(e.kind == "compensation.ok" for e in state.trace)
    assert any(e.kind == "rollback.completed" for e in state.trace)


def test_retryable_failure_recovers():
    flaky = Flaky()
    reg = SkillRegistry()
    reg.register(Flaky.spec, lambda: flaky)
    task = _task()
    state = Executor(reg, ContextStore([ContextSlice("a", "A")]), cfg=CFG,
                     backoff_base=0.0).run(task, plan=Plan(task.task_id,
                                                           [Step("s1", "flaky")]))
    assert state.status == TaskStatus.SUCCEEDED
    assert len(flaky.calls) == 3
    assert sum(1 for e in state.trace if e.kind == "react.retry") == 2


def test_high_risk_requires_human_and_confirmation_is_idempotent():
    task = _task()
    executor = _executor(HighRisk)
    plan = Plan(task.task_id, [Step("s1", "high")])
    state = executor.run(task, plan=plan)
    assert state.status == TaskStatus.NEEDS_HUMAN
    assert any(e.kind == "human.confirmation_required" for e in state.trace)

    task.meta["human_confirmed"] = True
    state2 = executor.run(task, plan=plan)
    assert state2.status == TaskStatus.SUCCEEDED
    assert not any(e.kind == "runtime.error" for e in state2.trace)


def test_state_machine_rejects_illegal_transition():
    state = ExecutionState("t")
    with pytest.raises(InvalidTransitionError):
        state.transition(TaskStatus.SUCCEEDED)
