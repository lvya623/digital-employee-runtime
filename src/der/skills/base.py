from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from der.domain.errors import NonRetryableError
from der.domain.models import SkillSpec, Step, Task
from der.logging_conf import get_logger

import time


@dataclass
class SkillContext:
    """传给 Skill 的全部输入。Skill 拿不到 DB、拿不到全量上下文，只能看到声明过的切片。"""

    task: Task
    step: Step
    slices: dict[str, str]
    artifacts: dict[str, Any]
    memory: dict[str, Any]
    idempotency_key: str
    emit: Callable[..., None] = lambda *args, **kwargs: None

    def require(self, key: str) -> str:
        """显式取上下文切片；缺失即失败，绝不静默降级。"""
        if key not in self.slices:
            raise NonRetryableError(f"context slice '{key}' was not loaded for {self.step.skill_name}")
        return self.slices[key]


@dataclass
class SkillResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    artifact_updates: dict[str, Any] = field(default_factory=dict)
    compensation: Callable[[], None] | None = None
    error: str | None = None
    retryable: bool = False
    needs_human: bool = False
    elapsed_ms: float = 0.0


class BaseSkill:
    """所有业务能力的统一外壳：校验契约、归类异常、计时、留痕。

    业务实现只写 _execute()，因此 AI 批量生成的多个 Skill 结构完全一致，
    人工 review 时可以「看一个，懂全部」。
    """

    spec: SkillSpec

    def __init__(self) -> None:
        self.log = get_logger(f"der.skill.{type(self).__name__}")

    def run(self, ctx: SkillContext) -> SkillResult:
        started = time.perf_counter()
        try:
            self._validate(ctx)
            result = self._execute(ctx)
            if not isinstance(result, SkillResult):
                raise NonRetryableError(f"{type(self).__name__}._execute must return SkillResult")
        except Exception as exc:  # 归类，不吞异常；日志保留完整堆栈
            self.log.warning(
                "skill failed: %s", exc,
                extra={"task_id": ctx.task.task_id, "step_id": ctx.step.step_id,
                       "skill": self.spec.name, "attempt": ctx.step.attempts},
                exc_info=True,
            )
            from der.domain.errors import NeedsHumanError, RetryableError

            result = SkillResult(
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                retryable=isinstance(exc, RetryableError) and self.spec.retryable,
                needs_human=isinstance(exc, NeedsHumanError),
            )
        result.elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        ctx.emit(
            "skill.finished",
            {"skill": self.spec.name, "ok": result.ok, "ms": result.elapsed_ms,
             "error": result.error},
            ctx.step.step_id,
        )
        return result

    def _validate(self, ctx: SkillContext) -> None:
        missing = [k for k in self.spec.required_context if k not in ctx.slices]
        if missing:
            raise NonRetryableError(
                f"{self.spec.name} requires context slices {missing}, got {sorted(ctx.slices)}"
            )

    def _execute(self, ctx: SkillContext) -> SkillResult:
        raise NotImplementedError
