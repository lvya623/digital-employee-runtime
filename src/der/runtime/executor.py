"""执行器：把 Planning / ReACT / Skill 调用串成一条可重试、可回滚的链路。"""

from __future__ import annotations

import time
from typing import Callable

from der.config import Settings, settings
from der.context.progressive import ContextStore, ProgressiveContextLoader
from der.domain.errors import PlanInvalidError
from der.domain.models import (
    ExecutionState,
    Plan,
    RiskLevel,
    Step,
    StepStatus,
    Task,
    TaskStatus,
)
from der.logging_conf import get_logger
from der.skills import SkillDispatcher, SkillRegistry

from .llm import LLMProvider, build_llm
from .memory import Memory
from .planner import Planner
from .react import ReACTCycle
from .state import InMemoryStateStore, StateStore


class Executor:
    """Task → Planning → ReACT → Tool/Skill 调用 → 输出，并全程留痕。"""

    def __init__(
        self,
        registry: SkillRegistry,
        context_store: ContextStore,
        cfg: Settings = settings,
        llm: LLMProvider | None = None,
        state_store: StateStore | None = None,
        memory: Memory | None = None,
        backoff_base: float = 0.01,
    ) -> None:
        self.registry = registry
        self.cfg = cfg
        self.log = get_logger("der.executor")
        self.loader = ProgressiveContextLoader(
            context_store, cfg.context_budget, cfg.reserved_output_tokens
        )
        self.planner = Planner(llm or build_llm(cfg), registry)
        self.react = ReACTCycle(
            SkillDispatcher(registry), self.loader, cfg.max_react_steps
        )
        self.state_store = state_store or InMemoryStateStore()
        self.memory = memory or Memory()
        self.backoff_base = backoff_base
        self._compensations: dict[str, list[tuple[str, Callable[[], None]]]] = {}

    def run(self, task: Task, plan: Plan | None = None) -> ExecutionState:
        state = ExecutionState(task.task_id)
        self._compensations[task.task_id] = []
        self.state_store.save(state)
        state.transition(TaskStatus.PLANNING)

        try:
            plan = plan or self.planner.build_plan(task)
            state.emit("plan.created", {
                "steps": [s.skill_name for s in plan.steps],
                "reasoning": plan.reasoning,
            })
            state.transition(TaskStatus.RUNNING)
        except Exception as exc:
            state.emit("plan.failed", {"error": f"{type(exc).__name__}: {exc}"})
            state.transition(TaskStatus.FAILED)
            self.state_store.save(state)
            return state

        try:
            for idx, step in enumerate(plan.steps):
                if idx >= self.cfg.max_react_steps:
                    raise PlanInvalidError("plan exceeds max_react_steps")
                state.current_step = idx
                spec = self.registry.get_spec(step.skill_name)

                # 高危动作必须人工确认，不靠模型自觉
                if spec.risk == RiskLevel.HIGH and not task.meta.get("human_confirmed"):
                    state.transition(TaskStatus.NEEDS_HUMAN)
                    state.emit("human.confirmation_required",
                               {"skill": step.skill_name, "risk": spec.risk.value},
                               step.step_id)
                    self.state_store.save(state)
                    return state

                result, loaded = self._run_step_with_retry(task, step, state, spec)

                if not result.ok:
                    if result.needs_human:
                        state.transition(TaskStatus.NEEDS_HUMAN)
                        state.emit("human.confirmation_required",
                                   {"skill": step.skill_name, "reason": result.error},
                                   step.step_id)
                        self.state_store.save(state)
                        return state
                    step.status = StepStatus.FAILED
                    step.error = result.error
                    state.emit("step.failed", {"skill": step.skill_name,
                                               "error": result.error}, step.step_id)
                    state.transition(TaskStatus.FAILED)
                    self._rollback(state)
                    return state

                if result.compensation is not None:
                    self._compensations.setdefault(task.task_id, []).append(
                        (step.skill_name, result.compensation)
                    )
                    state.compensations.append(step.skill_name)

                state.artifacts.update(result.artifact_updates)
                step.status = StepStatus.SUCCEEDED
                step.result = result.data
                state.context_report = self.loader.report
                state.emit("step.succeeded", {
                    "skill": step.skill_name, "tokens": loaded.tokens,
                    "summary": result.summary,
                }, step.step_id)
                self.memory.remember(f"last.{step.skill_name}", result.summary)

            state.transition(TaskStatus.SUCCEEDED)
            self._compensations.pop(task.task_id, None)
            state.context_report = self.loader.report
            state.emit("task.succeeded", {"steps": len(plan.steps),
                                          "context_tokens": state.context_report["total_tokens"]})
            self.state_store.save(state)
            return state
        except Exception as exc:
            # 归类后返回结构化失败，绝不把未处理异常抛到 API 层
            self.log.error("runtime error on %s: %s", task.task_id, exc, exc_info=True)
            state.emit("runtime.error", {"error": f"{type(exc).__name__}: {exc}"})
            if state.status in (TaskStatus.PLANNING, TaskStatus.RUNNING,
                                TaskStatus.NEEDS_HUMAN):
                state.transition(TaskStatus.FAILED)
            self._rollback(state)
            return state

    def _run_step_with_retry(self, task: Task, step: Step, state: ExecutionState, spec):
        attempt = 0
        while True:
            attempt += 1
            step.attempts = attempt
            result, _obs, loaded = self.react.act(
                task, step, state, spec, self.memory.snapshot()
            )
            if result.ok or not result.retryable or attempt > self.cfg.max_retries:
                return result, loaded
            state.emit("react.retry", {"skill": step.skill_name,
                                       "attempt": attempt,
                                       "next_backoff": self.backoff_base * (2 ** (attempt - 1))},
                       step.step_id)
            time.sleep(self.backoff_base * (2 ** (attempt - 1)))

    def _rollback(self, state: ExecutionState) -> None:
        """逆序执行补偿闭包；补偿失败时保留 FAILED 现场，不假装回滚成功。"""
        stack = self._compensations.pop(state.task_id, [])
        # 回滚不只撤销资金/发货副作用，也要撤销尚未投递的对外口径
        for key in ("reply.text", "notify.receipt"):
            state.artifacts.pop(key, None)
        incomplete = False
        for name, fn in reversed(stack):
            try:
                fn()
                state.emit("compensation.ok", {"skill": name})
            except Exception as exc:
                incomplete = True
                state.emit("compensation.failed", {"skill": name, "error": str(exc)})
        if incomplete:
            state.emit("rollback.incomplete", {"attempted": len(stack)})
            self.state_store.save(state)
            return
        if state.status == TaskStatus.FAILED:
            state.transition(TaskStatus.ROLLED_BACK)
        state.emit("rollback.completed", {"compensated": len(stack)})
        self.state_store.save(state)
