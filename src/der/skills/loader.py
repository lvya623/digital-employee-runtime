from __future__ import annotations

from .base import BaseSkill, SkillContext, SkillResult
from .registry import SkillRegistry


class SkillDispatcher:
    """动态调度：运行时按名字从 Registry 取实现，编排层不 import 业务模块。"""

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def dispatch(self, name: str, ctx: SkillContext) -> SkillResult:
        skill: BaseSkill = self.registry.build(name)
        return skill.run(ctx)

    def dispatch_chain(self, names: list[str], ctx_factory) -> list[SkillResult]:
        """组合执行：先拓扑排序，再按序调度；任一步失败即停止并返回已完成结果。"""
        chain = self.registry.resolve(names)
        results: list[SkillResult] = []
        for name in chain:
            results.append(self.dispatch(name, ctx_factory(name)))
            if not results[-1].ok:
                break
        return results
