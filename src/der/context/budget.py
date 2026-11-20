"""上下文预算与切片。所有文本进入 prompt 之前都必须经过这里。"""

from __future__ import annotations

from dataclasses import dataclass, field


def estimate_tokens(text: str) -> int:
    """轻量估算：CJK 约 1 字 1 token，其余按 4 字符 1 token。

    不依赖 tiktoken，保证零配置可跑；误差对相对比较（Eager vs Progressive）无影响。
    """
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return cjk + ((other + 3) // 4 if other else 0)


@dataclass
class ContextSlice:
    slice_id: str
    text: str
    stage: str = "general"
    compressible: bool = True

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)


@dataclass
class ContextBudget:
    max_tokens: int
    reserved_output: int = 512
    used: int = 0
    trimmed: list[str] = field(default_factory=list)

    @property
    def available(self) -> int:
        return max(0, self.max_tokens - self.reserved_output - self.used)

    def add(self, tokens: int) -> None:
        if tokens > self.available:
            from der.domain.errors import ContextBudgetExceeded

            raise ContextBudgetExceeded(
                f"need {tokens} tokens but only {self.available} available"
            )
        self.used += tokens

    def snapshot(self) -> dict:
        return {
            "max_tokens": self.max_tokens,
            "reserved_output": self.reserved_output,
            "used": self.used,
            "available": self.available,
            "trimmed": list(self.trimmed),
        }
