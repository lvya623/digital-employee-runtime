import pytest

from der.context import ContextSlice, ContextStore, EagerContextLoader, ProgressiveContextLoader
from der.domain.errors import ContextSliceNotFound
from der.domain.models import SkillKind, SkillSpec


def _spec(*ids: str) -> SkillSpec:
    return SkillSpec("probe", SkillKind.TOOL, "probe", required_context=tuple(ids))


def test_only_declared_slices_are_loaded():
    store = ContextStore([
        ContextSlice("a", "内容A" * 20),
        ContextSlice("b", "内容B" * 20),
        ContextSlice("c", "内容C" * 20),
    ])
    loader = ProgressiveContextLoader(store, max_tokens=2048, reserved_output=0)
    loaded = loader.load_for(_spec("b"))
    assert set(loaded.slices) == {"b"}
    assert loaded.tokens > 0
    assert "c" not in loaded.prompt


def test_unknown_slice_fails_loudly():
    store = ContextStore([ContextSlice("a", "A")])
    loader = ProgressiveContextLoader(store, max_tokens=2048, reserved_output=0)
    with pytest.raises(ContextSliceNotFound):
        loader.load_for(_spec("missing"))


def test_budget_compression_is_recorded():
    store = ContextStore([ContextSlice("long", "政策条款" * 300)])
    loader = ProgressiveContextLoader(store, max_tokens=200, reserved_output=0)
    loaded = loader.load_for(_spec("long"))
    assert loaded.trimmed == ["long"]
    assert loaded.tokens <= 200
    assert "[已按预算压缩]" in loaded.slices["long"] or "压缩" in loaded.slices["long"]


def test_report_accumulates_per_step():
    store = ContextStore([ContextSlice("a", "AAA"), ContextSlice("b", "BBB")])
    loader = ProgressiveContextLoader(store, max_tokens=2048, reserved_output=0)
    loader.load_for(_spec("a"))
    loader.load_for(_spec("a", "b"))
    report = loader.report
    assert report["total_tokens"] == sum(s["tokens"] for s in report["steps"])
    assert report["max_step_tokens"] >= report["steps"][0]["tokens"]
    assert len(report["steps"]) == 2


def test_eager_costs_more_than_progressive_single_step():
    store = ContextStore([ContextSlice(f"s{i}", f"知识片段{i} " * 100) for i in range(8)])
    eager = EagerContextLoader(store).load_all()
    progressive = ProgressiveContextLoader(store, max_tokens=2048, reserved_output=0)
    one_step = progressive.load_for(_spec("s0"))
    assert eager.tokens > one_step.tokens * 3
    assert len(eager.slices) == 8
    assert len(one_step.slices) == 1
