"""上下文层：切片、预算、渐进式加载，以及用于对照的 Eager 实现。"""

from .budget import ContextBudget, ContextSlice, estimate_tokens
from .progressive import ContextStore, LoadedContext, ProgressiveContextLoader
from .baseline import EagerContextLoader

__all__ = [
    "ContextBudget", "ContextSlice", "estimate_tokens", "ContextStore",
    "LoadedContext", "ProgressiveContextLoader", "EagerContextLoader",
]
