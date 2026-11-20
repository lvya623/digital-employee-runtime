"""对照实现：传统的「一次性把检索结果全塞进 prompt」，仅用于量化对比。"""

from __future__ import annotations

from .budget import estimate_tokens
from .progressive import ContextStore, LoadedContext


class EagerContextLoader:
    """不按阶段、不按 Skill 声明，全部切片一次装入。保留它只是为了证明差距。"""

    def __init__(self, store: ContextStore) -> None:
        self.store = store

    def load_all(self) -> LoadedContext:
        parts: list[str] = []
        slices: dict[str, str] = {}
        for slice_id in self.store.ids():
            text = self.store.get(slice_id).text
            slices[slice_id] = text
            parts.append(f"[{slice_id}]\n{text}")
        prompt = "\n\n".join(parts)
        return LoadedContext(slices=slices, tokens=estimate_tokens(prompt), prompt=prompt)
