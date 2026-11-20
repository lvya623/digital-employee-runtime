"""Skills 层：声明式能力契约、注册表与动态调度。"""

from .base import BaseSkill, SkillContext, SkillResult
from .registry import SkillRegistry
from .loader import SkillDispatcher

__all__ = ["BaseSkill", "SkillContext", "SkillResult", "SkillRegistry", "SkillDispatcher"]
