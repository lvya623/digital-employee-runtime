"""异常体系：所有失败都必须被归类，禁止用裸 except 吞掉。"""

from __future__ import annotations


class DERError(Exception):
    """本仓库所有可预期异常的基类。"""


class SkillError(DERError):
    """Skill 执行期错误。"""


class SkillNotFoundError(DERError):
    pass


class DuplicateSkillError(DERError):
    pass


class SkillDependencyError(DERError):
    pass


class ContextSliceNotFound(DERError):
    pass


class ContextBudgetExceeded(DERError):
    pass


class PlanInvalidError(DERError):
    pass


class InvalidTransitionError(DERError):
    pass


class CompensationError(DERError):
    pass


class RetryableError(SkillError):
    """暂时性失败（超时、限流、下游 5xx），允许指数退避重试。"""


class NonRetryableError(SkillError):
    """确定性失败（参数非法、业务规则拒绝），重试没有意义。"""


class NeedsHumanError(SkillError):
    """高危或不确定场景，需要人工确认后再继续。"""
