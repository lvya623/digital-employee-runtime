"""运行时组装：整个进程共享 Registry 与业务系统，每个任务独立上下文与状态。"""

from __future__ import annotations

from dataclasses import dataclass, field

from der.config import settings
from der.domain.models import Task
from der.multi_agent import Coordinator
from der.runtime.executor import Executor
from der.runtime.state import InMemoryStateStore
from der.skills import SkillRegistry
from der.skills.builtin.bootstrap import build_context_store, build_registry
from der.skills.builtin.store import BusinessStore


@dataclass
class Runtime:
    registry: SkillRegistry
    business: BusinessStore
    state_store: InMemoryStateStore = field(default_factory=InMemoryStateStore)
    tasks: dict[str, Task] = field(default_factory=dict)

    def executor_for(self, task: Task) -> Executor:
        return Executor(
            self.registry,
            build_context_store(task),
            cfg=settings,
            state_store=self.state_store,
            backoff_base=0.0,  # API 场景不做退避等待，由调用方控制重试
        )

    def coordinator(self) -> Coordinator:
        def factory(_worker_id: str, sub_task: Task) -> Executor:
            return self.executor_for(sub_task)
        return Coordinator(executor_factory=factory)


_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        registry, business = build_registry()
        _runtime = Runtime(registry=registry, business=business)
    return _runtime


def reset_runtime() -> None:
    """测试用：清空进程内状态，保证用例互不干扰。"""
    global _runtime
    _runtime = None
