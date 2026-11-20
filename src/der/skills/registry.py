from __future__ import annotations

from typing import Callable, Iterable

from der.domain.errors import (
    DuplicateSkillError,
    SkillDependencyError,
    SkillNotFoundError,
)
from der.domain.models import RiskLevel, SkillSpec

from .base import BaseSkill


class SkillRegistry:
    """能力注册中心：注册、版本、依赖解析、健康检查、给 Planner 的裁剪清单。"""

    def __init__(self) -> None:
        self._specs: dict[str, SkillSpec] = {}
        self._factories: dict[str, Callable[[], BaseSkill]] = {}

    def register(self, spec: SkillSpec, factory: Callable[[], BaseSkill]) -> None:
        if spec.name in self._specs:
            raise DuplicateSkillError(f"skill '{spec.name}' already registered")
        instance = factory()
        if instance.spec.name != spec.name:
            raise SkillDependencyError(
                f"factory for '{spec.name}' produces '{instance.spec.name}'"
            )
        self._specs[spec.name] = spec
        self._factories[spec.name] = factory

    def get_spec(self, name: str) -> SkillSpec:
        if name not in self._specs:
            raise SkillNotFoundError(name)
        return self._specs[name]

    def build(self, name: str) -> BaseSkill:
        if name not in self._factories:
            raise SkillNotFoundError(name)
        return self._factories[name]()

    def list_specs(self) -> list[SkillSpec]:
        return list(self._specs.values())

    def describe_for_planner(
        self, tags: Iterable[str] | None = None, max_items: int | None = None
    ) -> list[dict]:
        """工具清单本身也要受预算约束：按 tag 过滤，避免能力多了撑爆 prompt。"""
        wanted = set(tags or ())
        specs = [s for s in self._specs.values() if not wanted or (wanted & set(s.tags))]
        if max_items is not None:
            specs = specs[:max_items]
        return [s.planner_card() for s in specs]

    def resolve(self, names: Iterable[str]) -> list[str]:
        """按 depends_on 做拓扑排序，形成可组合执行的 Skill 链；检测环与缺失依赖。"""
        ordered: list[str] = []
        done: set[str] = set()
        visiting: set[str] = set()

        def visit(name: str) -> None:
            if name in done:
                return
            if name in visiting:
                raise SkillDependencyError(f"cycle detected at skill '{name}'")
            if name not in self._specs:
                raise SkillNotFoundError(name)
            visiting.add(name)
            for dep in self._specs[name].depends_on:
                if dep not in self._specs:
                    raise SkillDependencyError(f"'{name}' depends on unregistered '{dep}'")
                visit(dep)
            visiting.discard(name)
            done.add(name)
            ordered.append(name)

        for n in names:
            visit(n)
        return ordered

    def health(self) -> dict[str, bool]:
        """静态体检：高危 Skill 必须可补偿，所有能力必须有描述与版本。"""
        report: dict[str, bool] = {}
        for name, spec in self._specs.items():
            ok = bool(spec.description) and bool(spec.version)
            if spec.risk == RiskLevel.HIGH and not spec.compensatable:
                ok = False
            if not spec.required_context:
                ok = False
            report[name] = ok
        return report

    def __len__(self) -> int:
        return len(self._specs)
