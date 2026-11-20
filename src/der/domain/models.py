from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable
import uuid

from .errors import InvalidTransitionError


def utcnow() -> datetime:
    """统一使用带时区的 UTC 时间，避免日志与轨迹出现本地时间歧义。"""
    return datetime.now(timezone.utc)


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    NEEDS_HUMAN = "needs_human"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SkillKind(str, Enum):
    API = "api"
    WORKFLOW = "workflow"
    TOOL = "tool"


ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.PLANNING, TaskStatus.FAILED},
    TaskStatus.PLANNING: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.NEEDS_HUMAN},
    TaskStatus.RUNNING: {
        TaskStatus.SUCCEEDED,
        TaskStatus.FAILED,
        TaskStatus.NEEDS_HUMAN,
        TaskStatus.ROLLED_BACK,
    },
    TaskStatus.NEEDS_HUMAN: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.ROLLED_BACK},
    TaskStatus.FAILED: {TaskStatus.ROLLED_BACK},
    TaskStatus.SUCCEEDED: set(),
    TaskStatus.ROLLED_BACK: set(),
}


@dataclass(frozen=True)
class SkillSpec:
    """能力的声明式契约。

    required_context 是渐进式上下文的锚点：Skill 只声明自己这一步需要哪几片知识，
    编排层据此按需加载，而不是把全部检索结果一次性塞进 prompt。
    """

    name: str
    kind: SkillKind
    description: str
    version: str = "1.0.0"
    required_context: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    retryable: bool = True
    compensatable: bool = False
    risk: RiskLevel = RiskLevel.LOW
    tags: tuple[str, ...] = ()

    def planner_card(self) -> dict[str, Any]:
        """给 Planner 的紧凑清单：只暴露决策所需信息，不暴露实现细节。"""
        return {
            "name": self.name,
            "kind": self.kind.value,
            "description": self.description,
            "required_context": list(self.required_context),
            "risk": self.risk.value,
        }


@dataclass
class Task:
    task_id: str
    goal: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=utcnow)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Step:
    step_id: str
    skill_name: str
    args: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    depends_on: tuple[str, ...] = ()
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class Plan:
    task_id: str
    steps: list[Step] = field(default_factory=list)
    reasoning: str = ""
    created_by: str = "planner"


@dataclass
class Event:
    task_id: str
    kind: str
    step_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    ts: datetime = field(default_factory=utcnow)
    event_id: str = field(default_factory=lambda: new_id("ev_"))


@dataclass
class ExecutionState:
    """执行链路的当前位置。注意：这里不存业务数据，业务数据放 artifacts / Memory。"""

    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    current_step: int = 0
    trace: list[Event] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    compensations: list[str] = field(default_factory=list)
    context_report: dict[str, Any] = field(default_factory=dict)

    def emit(self, kind: str, detail: dict[str, Any] | None = None, step_id: str | None = None) -> None:
        """记录一次可回放的事件；所有状态变化都必须经过这里。"""
        self.trace.append(Event(self.task_id, kind, step_id=step_id, detail=detail or {}))

    def transition(self, nxt: TaskStatus) -> None:
        """状态机转移校验，非法转移直接失败而不是悄悄改状态。"""
        if nxt not in ALLOWED_TRANSITIONS.get(self.status, set()):
            raise InvalidTransitionError(
                f"{self.status.value} -> {nxt.value} is not allowed"
            )
        old = self.status
        self.status = nxt
        self.emit("state.transition", {"from": old.value, "to": nxt.value})
