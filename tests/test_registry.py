import pytest

from der.domain.errors import DuplicateSkillError, SkillDependencyError, SkillNotFoundError
from der.domain.models import SkillKind, SkillSpec
from der.skills import SkillRegistry
from der.skills.base import BaseSkill, SkillResult
from der.skills.builtin.bootstrap import build_registry


class _Stub(BaseSkill):
    def __init__(self, spec: SkillSpec) -> None:
        self.spec = spec
        super().__init__()

    def _execute(self, ctx) -> SkillResult:
        return SkillResult(ok=True)


def _register(reg: SkillRegistry, spec: SkillSpec) -> None:
    reg.register(spec, lambda s=spec: _Stub(s))


def test_duplicate_registration_is_rejected():
    reg = SkillRegistry()
    spec = SkillSpec("a", SkillKind.TOOL, "A", required_context=("x",))
    _register(reg, spec)
    with pytest.raises(DuplicateSkillError):
        _register(reg, spec)


def test_unknown_skill_raises():
    reg = SkillRegistry()
    with pytest.raises(SkillNotFoundError):
        reg.get_spec("missing")


def test_resolve_respects_dependencies():
    reg, _ = build_registry()
    assert reg.resolve(["reship"]) == ["fetch_order", "reship"]
    assert reg.resolve(["notify", "reship"]) == ["notify", "fetch_order", "reship"]


def test_cycle_detection():
    reg = SkillRegistry()
    _register(reg, SkillSpec("a", SkillKind.TOOL, "A", required_context=("x",),
                             depends_on=("b",)))
    _register(reg, SkillSpec("b", SkillKind.TOOL, "B", required_context=("x",),
                             depends_on=("a",)))
    with pytest.raises(SkillDependencyError, match="cycle"):
        reg.resolve(["a"])


def test_planner_cards_are_filtered_and_bounded():
    reg, _ = build_registry()
    cards = reg.describe_for_planner(tags=("aux",))
    assert [c["name"] for c in cards] == ["knowledge_lookup"]
    assert len(reg.describe_for_planner(max_items=3)) == 3
    assert set(cards[0]) == {"name", "kind", "description", "required_context", "risk"}


def test_health_requires_compensation_for_high_risk():
    reg, _ = build_registry()
    assert len(reg) == 11
    assert all(reg.health().values())
