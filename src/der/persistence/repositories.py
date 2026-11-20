"""把执行轨迹落到数据库，支持回放与审计。"""

from __future__ import annotations

from typing import Any

from der.domain.models import Event, ExecutionState, TaskStatus

from .db import EventRecord, TaskRecord, init_db, make_sessionmaker


class DatabaseStateStore:
    """Executor 的 StateStore 实现之一，替换 InMemoryStateStore 无需改编排层。"""

    def __init__(self, engine) -> None:
        init_db(engine)
        self.Session = make_sessionmaker(engine)

    def save(self, state: ExecutionState) -> None:
        with self.Session() as session:
            session.merge(TaskRecord(
                task_id=state.task_id,
                status=state.status.value,
                context_report=state.context_report,
            ))
            session.query(EventRecord).filter_by(task_id=state.task_id).delete()
            for seq, event in enumerate(state.trace):
                session.add(EventRecord(
                    task_id=event.task_id, seq=seq, kind=event.kind,
                    step_id=event.step_id, detail=event.detail, ts=event.ts,
                ))
            session.commit()

    def get(self, task_id: str) -> ExecutionState | None:
        with self.Session() as session:
            record = session.get(TaskRecord, task_id)
            if record is None:
                return None
            rows = (session.query(EventRecord)
                    .filter_by(task_id=task_id).order_by(EventRecord.seq).all())
            state = ExecutionState(task_id=task_id, status=TaskStatus(record.status))
            state.trace = [Event(r.task_id, r.kind, r.step_id, r.detail or {}, r.ts)
                           for r in rows]
            state.context_report = record.context_report or {}
            return state

    def ids(self) -> list[str]:
        with self.Session() as session:
            return [r[0] for r in session.query(TaskRecord.task_id).all()]

    def trace(self, task_id: str) -> list[dict[str, Any]]:
        state = self.get(task_id)
        if state is None:
            return []
        return [{"kind": e.kind, "step_id": e.step_id,
                 "detail": e.detail, "ts": e.ts.isoformat()} for e in state.trace]
