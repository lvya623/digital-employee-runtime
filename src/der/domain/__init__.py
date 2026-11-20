"""领域模型：跨层唯一的数据契约，禁止依赖任何框架或 IO。"""

from .models import (
    ALLOWED_TRANSITIONS,
    Event,
    ExecutionState,
    Plan,
    RiskLevel,
    SkillKind,
    SkillSpec,
    Step,
    StepStatus,
    Task,
    TaskStatus,
    new_id,
    utcnow,
)
from .errors import (
    CompensationError,
    ContextBudgetExceeded,
    ContextSliceNotFound,
    DERError,
    DuplicateSkillError,
    InvalidTransitionError,
    NeedsHumanError,
    NonRetryableError,
    PlanInvalidError,
    RetryableError,
    SkillDependencyError,
    SkillError,
    SkillNotFoundError,
)

__all__ = [
    "ALLOWED_TRANSITIONS", "Event", "ExecutionState", "Plan", "RiskLevel",
    "SkillKind", "SkillSpec", "Step", "StepStatus", "Task", "TaskStatus",
    "new_id", "utcnow", "CompensationError", "ContextBudgetExceeded",
    "ContextSliceNotFound", "DERError", "DuplicateSkillError",
    "InvalidTransitionError", "NeedsHumanError", "NonRetryableError",
    "PlanInvalidError", "RetryableError", "SkillDependencyError",
    "SkillError", "SkillNotFoundError",
]
