"""执行链路的状态存储。默认内存实现，可替换为数据库实现而不改 Executor。"""

from __future__ import annotations

from typing import Protocol

from der.domain.models import ExecutionState, TaskStatus


class StateStore(Protocol):
    def save(self, state: ExecutionState) -> None: ...
    def get(self, task_id: str) -> ExecutionState | None: ...
    def ids(self) -> list[str]: ...


class InMemoryStateStore:
    def __init__(self) -> None:
        self._states: dict[str, ExecutionState] = {}

    def save(self, state: ExecutionState) -> None:
        self._states[state.task_id] = state

    def get(self, task_id: str) -> ExecutionState | None:
        return self._states.get(task_id)

    def ids(self) -> list[str]:
        return list(self._states)


def is_terminal(state: ExecutionState) -> bool:
    return state.status in (TaskStatus.SUCCEEDED, TaskStatus.ROLLED_BACK)
