"""L2 Application use-case — CompilerRepairPolicy + CompilerActionType (M016 S02).

Maps a ``CompilerGapClass`` (domain) to a ``CompilerActionType`` the compiler
optimization loop can execute. Mirrors the reasoning-domain ``RepairPolicy``
pattern (M009 S02) but is intentionally a separate type — the two domains
have different gap semantics (compiler gaps are schedule/transform-shaped,
not evidence/provenance-shaped) and benefit from an independent mapping
that can evolve separately.

Default mapping (M016 S02):
  Missing transform      → APPLY_TRANSFORM       (try the first candidate)
  Transform regression   → PICK_ALTERNATIVE      (skip this candidate)
  Loop-carried dep       → PICK_ALTERNATIVE      (different transform respects deps)
  Register spill         → PICK_ALTERNATIVE      (transform with smaller footprint)
  Perf regression        → PICK_ALTERNATIVE      (skip this candidate)

LOWERING_REPLAN is intentionally NOT in the default mapping — it is a
user-facing escape hatch that terminates the loop. Production policies
can route specific gap classes to LOWERING_REPLAN when the only
recovery is to redesign the lowering strategy (which the bounded
candidate loop cannot do).

Pure application. Depends on domain only; no I/O (R002).
"""

from __future__ import annotations

from dataclasses import dataclass

from active_skill_system.domain.compiler_types import CompilerActionType, CompilerGapClass

_DEFAULT_POLICY: dict[CompilerGapClass, CompilerActionType] = {
    CompilerGapClass.MISSING_TRANSFORM: CompilerActionType.APPLY_TRANSFORM,
    CompilerGapClass.TRANSFORM_REGRESSION: CompilerActionType.PICK_ALTERNATIVE,
    CompilerGapClass.LOOP_CARRIED_DEP: CompilerActionType.PICK_ALTERNATIVE,
    CompilerGapClass.REGISTER_SPILL: CompilerActionType.PICK_ALTERNATIVE,
    CompilerGapClass.PERF_REGRESSION: CompilerActionType.PICK_ALTERNATIVE,
}


@dataclass(frozen=True)
class CompilerRepairPolicy:
    """Maps ``CompilerGapClass`` → ``CompilerActionType``. Immutable; injectable.

    Separate from the reasoning-domain ``RepairPolicy`` — different gap
    taxonomy, different action vocabulary, independent evolution. Use
    ``default_policy()`` for the M016 S02 default mapping, or construct
    with a custom dict for testing or domain-specific overrides.
    """

    mapping: dict[CompilerGapClass, CompilerActionType]

    def __post_init__(self) -> None:
        if not isinstance(self.mapping, dict) or not self.mapping:
            raise ValueError(
                f"CompilerRepairPolicy.mapping must be a non-empty dict (got {self.mapping!r})"
            )
        for gap, action in self.mapping.items():
            if not isinstance(gap, CompilerGapClass):
                raise ValueError(
                    f"mapping key must be a CompilerGapClass (got {type(gap).__name__})"
                )
            if not isinstance(action, CompilerActionType):
                raise ValueError(
                    f"mapping value must be a CompilerActionType (got {type(action).__name__})"
                )

    def action_for(self, gap_class: CompilerGapClass) -> CompilerActionType:
        """Return the ActionType for a gap class, or LOWERING_REPLAN as fallback."""
        return self.mapping.get(gap_class, CompilerActionType.LOWERING_REPLAN)

    def covers(self, gap_class: CompilerGapClass) -> bool:
        """True if the policy has an explicit entry for this gap class."""
        return gap_class in self.mapping

    @classmethod
    def default_policy(cls) -> CompilerRepairPolicy:
        """M016 S02 default gap→action mapping (mirrors concept.md §7 idiom)."""
        return cls(mapping=dict(_DEFAULT_POLICY))
