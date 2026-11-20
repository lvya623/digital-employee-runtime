"""Planning：把「一句话目标」拆成有序、可校验的执行步骤。"""

from __future__ import annotations

from dataclasses import dataclass

from der.domain.errors import PlanInvalidError, SkillNotFoundError
from der.domain.models import Plan, Step, Task
from der.skills import SkillRegistry

from .llm import LLMProvider


@dataclass
class Planner:
    llm: LLMProvider
    registry: SkillRegistry
    max_planner_skills: int = 16

    def build_plan(self, task: Task) -> Plan:
        """能力清单本身也受预算约束，避免 Skill 变多后工具描述撑爆 prompt。"""
        cards = self.registry.describe_for_planner(max_items=self.max_planner_skills)
        raw = self.llm.plan(task.goal, cards, task.payload)
        raw_steps = raw.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise PlanInvalidError("planner returned an empty step list")

        seen: set[str] = set()
        steps: list[Step] = []
        for i, item in enumerate(raw_steps):
            if not isinstance(item, dict) or not item.get("skill_name"):
                raise PlanInvalidError(f"step {i} has no skill_name")
            name = str(item["skill_name"])
            try:
                spec = self.registry.get_spec(name)
            except SkillNotFoundError as exc:
                raise PlanInvalidError(f"planner chose unknown skill '{name}'") from exc
            for dep in spec.depends_on:
                if dep not in seen:
                    raise PlanInvalidError(f"'{name}' needs '{dep}' to run earlier in the plan")
            steps.append(Step(
                step_id=f"{task.task_id}-s{i + 1}",
                skill_name=name,
                args=dict(item.get("args") or {}),
                rationale=str(item.get("rationale", "")),
                depends_on=spec.depends_on,
            ))
            seen.add(name)
        return Plan(task.task_id, steps, str(raw.get("reasoning", "")))
