"""Worker：每个子任务拥有隔离的 Executor（独立的上下文加载器、状态与记忆）。"""

from __future__ import annotations

from dataclasses import dataclass

from der.domain.models import Task, TaskStatus
from der.runtime.executor import Executor


@dataclass(frozen=True)
class WorkerResult:
    worker_id: str
    task_id: str
    ok: bool
    status: str
    summary: str
    steps: int


class Worker:
    def __init__(self, worker_id: str, executor: Executor) -> None:
        self.worker_id = worker_id
        self.executor = executor

    def handle(self, task: Task) -> WorkerResult:
        state = self.executor.run(task)
        done = sum(1 for e in state.trace if e.kind == "step.succeeded")
        return WorkerResult(
            worker_id=self.worker_id,
            task_id=task.task_id,
            ok=state.status == TaskStatus.SUCCEEDED,
            status=state.status.value,
            summary=state.artifacts.get("reply.text", ""),
            steps=done,
        )
