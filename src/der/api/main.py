"""FastAPI 入口：协议转换层，不承载状态机与业务逻辑。"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from der.domain.models import Task, new_id

from .deps import get_runtime
from .schemas import ConfirmOut, TaskIn, TaskOut

app = FastAPI(
    title="Digital Employee Runtime",
    version="0.1.0",
    description="执行型数字员工：Task → Planning → ReACT → Skill → 输出，非 RAG 问答",
)


def _make_task(req: TaskIn) -> Task:
    payload = {"text": req.text, "order_id": req.order_id, "channel": req.channel}
    if req.subtasks:
        payload["subtasks"] = req.subtasks
    return Task(
        task_id=new_id("task_"),
        goal=req.goal,
        payload=payload,
        meta={"human_confirmed": req.human_confirmed},
    )


def _plan_steps(state) -> list[str]:
    for event in state.trace:
        if event.kind == "plan.created":
            return list(event.detail.get("steps", []))
    return []


def _message(status: str, task_id: str) -> str:
    if status == "succeeded":
        return "数字员工已完成执行，结果见 /tasks/{id}/trace".replace("{id}", task_id)
    if status == "needs_human":
        return "高危动作需人工确认，确认后 POST /tasks/{id}/confirm".replace("{id}", task_id)
    if status == "rolled_back":
        return "执行失败，已逆序补偿回滚，现场保留供排查"
    return "执行未成功，请查看 /tasks/{id}/trace".replace("{id}", task_id)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "skills": len(get_runtime().registry)}


@app.get("/skills")
def list_skills() -> dict:
    """给 Planner 的紧凑能力清单（真实接口，不是写死的文档）。"""
    return {"skills": get_runtime().registry.describe_for_planner()}


@app.get("/skills/health")
def skills_health() -> dict:
    return get_runtime().registry.health()


@app.post("/tasks", response_model=TaskOut)
def create_task(req: TaskIn) -> TaskOut:
    runtime = get_runtime()
    task = _make_task(req)
    runtime.tasks[task.task_id] = task
    state = runtime.executor_for(task).run(task)
    return TaskOut(
        task_id=task.task_id,
        status=state.status.value,
        steps=_plan_steps(state),
        trace_events=len(state.trace),
        context_report=state.context_report,
        message=_message(state.status.value, task.task_id),
    )


@app.post("/tasks/delegate")
def delegate(req: TaskIn) -> dict:
    """复杂任务走 Multi-Agent 协作；子任务各自独立上下文与状态。"""
    runtime = get_runtime()
    task = _make_task(req)
    runtime.tasks[task.task_id] = task
    return runtime.coordinator().run(task)


@app.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    state = get_runtime().state_store.get(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="task not found")
    return {
        "task_id": task_id,
        "status": state.status.value,
        "steps": _plan_steps(state),
        "compensations": state.compensations,
        "context_report": state.context_report,
        "artifacts": {k: str(v)[:120] for k, v in state.artifacts.items()},
    }


@app.get("/tasks/{task_id}/trace")
def get_trace(task_id: str) -> dict:
    state = get_runtime().state_store.get(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="task not found")
    return {
        "task_id": task_id,
        "events": [
            {"kind": e.kind, "step_id": e.step_id, "detail": e.detail,
             "ts": e.ts.isoformat()}
            for e in state.trace
        ],
    }


@app.post("/tasks/{task_id}/confirm", response_model=ConfirmOut)
def confirm_task(task_id: str) -> ConfirmOut:
    runtime = get_runtime()
    task = runtime.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    task.meta["human_confirmed"] = True
    # 同一 task_id 重跑：step_id 不变 → 幂等键不变 → 不会重复退款
    state = runtime.executor_for(task).run(task)
    runtime.tasks[task_id] = task
    return ConfirmOut(
        task_id=task_id,
        status=state.status.value,
        message=_message(state.status.value, task_id),
    )
