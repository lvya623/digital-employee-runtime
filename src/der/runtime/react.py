"""ReACT 循环：Thought → Action（Skill 调用）→ Observation。

关键约束：工具返回的完整数据落到 artifacts，只有**摘要**进入后续推理，
否则几步之后上下文就会被 Observation 撑爆。
"""

from __future__ import annotations

from dataclasses import dataclass

from der.context.progressive import LoadedContext, ProgressiveContextLoader
from der.domain.models import ExecutionState, SkillSpec, Step, Task
from der.skills import SkillDispatcher
from der.skills.base import SkillContext, SkillResult


@dataclass(frozen=True)
class Observation:
    step_id: str
    skill: str
    summary: str
    full_ref: str
    tokens: int


class ReACTCycle:
    def __init__(
        self,
        dispatcher: SkillDispatcher,
        loader: ProgressiveContextLoader,
        max_steps: int = 12,
    ) -> None:
        self.dispatcher = dispatcher
        self.loader = loader
        self.max_steps = max_steps

    def act(
        self,
        task: Task,
        step: Step,
        state: ExecutionState,
        spec: SkillSpec,
        memory_snapshot: dict,
    ) -> tuple[SkillResult, Observation, LoadedContext]:
        state.emit(
            "react.thought",
            {"step": step.step_id, "skill": step.skill_name,
             "reason": step.rationale or spec.description},
            step.step_id,
        )
        # 只加载本步骤声明需要的上下文切片
        loaded = self.loader.load_for(spec, stage=f"step_{state.current_step}")
        ctx = SkillContext(
            task=task,
            step=step,
            slices=loaded.slices,
            artifacts=state.artifacts,
            memory=memory_snapshot,
            idempotency_key=f"{task.task_id}:{step.step_id}",
            emit=state.emit,
        )
        result = self.dispatcher.dispatch(step.skill_name, ctx)
        observation = Observation(
            step_id=step.step_id,
            skill=step.skill_name,
            summary=result.summary or result.error or "",
            full_ref=f"artifact://{step.step_id}",
            tokens=loaded.tokens,
        )
        state.emit(
            "react.observation",
            {"skill": step.skill_name, "ok": result.ok,
             "summary": observation.summary, "context_tokens": loaded.tokens,
             "trimmed": loaded.trimmed, "skipped": loaded.skipped},
            step.step_id,
        )
        self.observe(state, observation)
        return result, observation, loaded

    def observe(self, state: ExecutionState, observation: Observation) -> None:
        """写回摘要，不写回完整 Observation。"""
        state.artifacts[f"observation.{observation.step_id}"] = observation.summary
