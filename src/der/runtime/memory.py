"""Memory 与 State 解耦：State 是「执行到第几步」，Memory 是「关于这件事的事实」。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Memory:
    working: dict[str, Any] = field(default_factory=dict)
    long_term: dict[str, Any] = field(default_factory=dict)

    def remember(self, key: str, value: Any, *, long_term: bool = False) -> None:
        if long_term:
            self.long_term[key] = value
        else:
            self.working[key] = value

    def recall(self, key: str, default: Any = None) -> Any:
        if key in self.working:
            return self.working[key]
        return self.long_term.get(key, default)

    def promote(self, *keys: str) -> None:
        """把验证过的事实从工作记忆提升到长期记忆（跨会话复用）。"""
        for key in keys:
            if key in self.working:
                self.long_term[key] = self.working.pop(key)

    def snapshot(self) -> dict[str, Any]:
        """传给 Skill 的是快照，不是 Memory 对象本身，避免业务代码反向写状态。"""
        return {**self.long_term, **self.working}

    def clear_working(self) -> None:
        self.working.clear()
