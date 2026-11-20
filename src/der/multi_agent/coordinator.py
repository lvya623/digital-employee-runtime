"""Coordinator：只在任务确实复杂时启用多智能体协作，并支持失败降级。"""

from __future__ import annotations

from typing import Callable

from der.domain.models import Task, new_id

from .bus import InMemoryBus, Message
from .worker import Worker, WorkerResult


class Coordinator:
    def __init__(
        self,
        bus: InMemoryBus | None = None,
        executor_factory: Callable[[str], object] | None = None,
        max_workers: int = 3,
    ) -> None:
        self.bus = bus or InMemoryBus()
        self.executor_factory = executor_factory
        self.max_workers = max_workers

    def is_complex(self, task: Task) -> bool:
        subtasks = task.payload.get("subtasks")
        return bool(subtasks) and len(subtasks) > 1

    def run(self, task: Task) -> dict:
        """把复杂任务拆给独立 Worker；单 Worker 失败不影响其他分支，最后聚合。"""
        if not self.is_complex(task):
            return {"delegated": False, "reason": "single-domain task, no delegation needed"}

        raw_subtasks = task.payload["subtasks"]
        worker_ids = [f"worker-{i + 1}" for i in range(min(len(raw_subtasks), self.max_workers))]
        if self.executor_factory is None:
            raise ValueError("Coordinator requires an executor_factory to isolate workers")

        results: list[WorkerResult] = []
        for i, raw in enumerate(raw_subtasks):
            if isinstance(raw, str):
                raw = {"goal": raw}
            wid = worker_ids[i % len(worker_ids)]
            child_payload = {**task.payload, **dict(raw.get("payload", {}))}
            child_payload.pop("subtasks", None)  # 避免子任务再次触发委托
            sub_task = Task(
                task_id=new_id("sub_"),
                goal=str(raw.get("goal", task.goal)),
                payload=child_payload,
                meta=dict(task.meta),
            )
            # 每个子任务拿到独立的 Executor：上下文、状态、记忆全部隔离
            worker = Worker(wid, self.executor_factory(wid, sub_task))  # type: ignore[arg-type]
            self.bus.send(Message("coordinator", worker.worker_id, "task.assign",
                                  {"task_id": sub_task.task_id, "goal": sub_task.goal}))
            result = worker.handle(sub_task)
            self.bus.send(Message(worker.worker_id, "coordinator", "task.result",
                                  {"ok": result.ok, "status": result.status,
                                   "task_id": result.task_id}))
            results.append(result)

        succeeded = [r for r in results if r.ok]
        return {
            "delegated": True,
            "workers": worker_ids,
            "total": len(results),
            "succeeded": len(succeeded),
            "degraded": len(succeeded) < len(results),
            "results": [r.__dict__ for r in results],
            "messages": len(self.bus.all_messages()),
        }
