"""渐进式上下文：按任务阶段、按 Skill 声明动态加载，而不是一次性塞入。"""

from __future__ import annotations

from dataclasses import dataclass, field

from der.domain.errors import ContextSliceNotFound
from der.domain.models import SkillSpec

from .budget import ContextBudget, ContextSlice, estimate_tokens


class ContextStore:
    """所有可用知识片的登记处。未登记的 id 被引用时直接抛错，不静默降级。"""

    def __init__(self, slices: list[ContextSlice] | None = None) -> None:
        self._slices: dict[str, ContextSlice] = {}
        for s in slices or []:
            self.add(s)

    def add(self, slice_: ContextSlice) -> None:
        self._slices[slice_.slice_id] = slice_

    def get(self, slice_id: str) -> ContextSlice:
        if slice_id not in self._slices:
            raise ContextSliceNotFound(slice_id)
        return self._slices[slice_id]

    def ids(self) -> list[str]:
        return list(self._slices)

    def total_tokens(self) -> int:
        return sum(s.tokens for s in self._slices.values())

    def __len__(self) -> int:
        return len(self._slices)


@dataclass
class LoadedContext:
    slices: dict[str, str] = field(default_factory=dict)
    tokens: int = 0
    trimmed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    prompt: str = ""


def _compress(text: str, max_tokens: int) -> str:
    """预算不足时做摘要式截断，并显式留痕；完整内容仍可从 artifact 取回。"""
    budget_chars = max(64, max_tokens)
    if len(text) <= budget_chars:
        return text
    candidate = text[:budget_chars] + " …[已按上下文预算压缩，完整内容见 artifact]"
    while estimate_tokens(candidate) > max_tokens and budget_chars > 64:
        budget_chars = int(budget_chars * 0.8)
        candidate = text[:budget_chars] + " …[已压缩]"
    return candidate


class ProgressiveContextLoader:
    """每个步骤新建预算，只加载 SkillSpec.required_context 声明的切片。"""

    def __init__(
        self,
        store: ContextStore,
        max_tokens: int = 2048,
        reserved_output: int = 512,
    ) -> None:
        self.store = store
        self.max_tokens = max_tokens
        self.reserved_output = reserved_output
        self.report: dict = {"strategy": "progressive", "steps": [], "total_tokens": 0,
                             "max_step_tokens": 0, "trimmed_total": 0}

    def load_for(self, spec: SkillSpec, stage: str | None = None) -> LoadedContext:
        budget = ContextBudget(self.max_tokens, self.reserved_output)
        loaded = LoadedContext()
        parts: list[str] = []

        for slice_id in spec.required_context:
            slice_ = self.store.get(slice_id)
            tokens = slice_.tokens
            if tokens > budget.available:
                if slice_.compressible and budget.available >= 64:
                    text = _compress(slice_.text, budget.available)
                    tokens = estimate_tokens(text)
                    if tokens > budget.available:
                        keep = max(0, budget.available - 24)
                        text = text[:keep] + " …[已按预算压缩]"
                        tokens = estimate_tokens(text)
                    loaded.trimmed.append(slice_id)
                    budget.trimmed.append(slice_id)
                else:
                    loaded.skipped.append(slice_id)
                    continue
            else:
                text = slice_.text
            budget.add(tokens)
            loaded.slices[slice_id] = text
            parts.append(f"[{slice_id}]\n{text}")

        loaded.tokens = budget.used
        loaded.prompt = "\n\n".join(parts)
        self.report["steps"].append({
            "skill": spec.name,
            "stage": stage or spec.kind.value,
            "loaded": list(loaded.slices),
            "tokens": loaded.tokens,
            "trimmed": list(loaded.trimmed),
            "skipped": list(loaded.skipped),
        })
        self.report["total_tokens"] += loaded.tokens
        self.report["max_step_tokens"] = max(self.report["max_step_tokens"], loaded.tokens)
        self.report["trimmed_total"] += len(loaded.trimmed)
        return loaded

    def reset_report(self) -> None:
        self.report = {"strategy": "progressive", "steps": [], "total_tokens": 0,
                       "max_step_tokens": 0, "trimmed_total": 0}
