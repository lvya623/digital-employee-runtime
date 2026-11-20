"""量化对比：一次性 RAG 塞上下文 vs 渐进式按阶段加载。

口径说明：在 N 步的 ReACT 循环里，传统做法每一轮都要把全量检索结果重新交给模型，
所以真实成本 ≈ 单步全量 token × N；渐进式每步只携带本步骤声明的切片。
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from der.context import EagerContextLoader, ProgressiveContextLoader  # noqa: E402
from der.domain.models import Task  # noqa: E402
from der.skills.builtin.bootstrap import build_context_store, build_registry  # noqa: E402

PLAN = [
    "classify_ticket", "fetch_order", "assess_policy", "knowledge_lookup",
    "refund", "write_reply", "notify", "audit_log",
]


def main() -> dict:
    task = Task("bench", "售后工单", {"text": "商品有质量问题，希望退款"})
    store = build_context_store(task)
    registry, _ = build_registry()
    specs = [registry.get_spec(name) for name in PLAN]

    progressive = ProgressiveContextLoader(store, max_tokens=2048, reserved_output=512)
    print(f"知识切片：{len(store)} 片，全量 {store.total_tokens()} tokens\n")
    print(f"{'步骤':<20}{'加载片数':>8}{'本步 tokens':>14}")
    print("-" * 44)
    for i, spec in enumerate(specs):
        loaded = progressive.load_for(spec, stage=f"step_{i + 1}")
        print(f"{spec.name:<20}{len(loaded.slices):>8}{loaded.tokens:>14}")

    eager = EagerContextLoader(store).load_all()
    steps = len(specs)
    eager_total = eager.tokens * steps
    prog_total = progressive.report["total_tokens"]
    saving = (1 - prog_total / eager_total) * 100
    peak_ratio = progressive.report["max_step_tokens"] / eager.tokens * 100

    print("-" * 44)
    print(f"一次性塞入（单步）        : {eager.tokens:>6} tokens × {steps} 步 = {eager_total} tokens")
    print(f"渐进式按阶段加载（合计）  : {prog_total:>6} tokens")
    print(f"最大单步开销占全量比例    : {peak_ratio:.1f}%")
    print(f"上下文成本下降            : {saving:.1f}%")
    print("\n注：token 为轻量估算（CJK 1 字≈1 token，其余 4 字符≈1 token），")
    print("    用于同口径相对比较；接入真实模型后可替换为 tiktoken 精确计数。")
    return {
        "slices": len(store), "eager_single_step": eager.tokens,
        "steps": steps, "eager_total": eager_total,
        "progressive_total": prog_total,
        "max_step_tokens": progressive.report["max_step_tokens"],
        "peak_ratio_pct": round(peak_ratio, 1), "saving_pct": round(saving, 1),
    }


if __name__ == "__main__":
    main()
