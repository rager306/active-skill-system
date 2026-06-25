"""L2 Application — TransformationSelector (M020 S01).

Per-stage transformation selection (analogous to ``ModelSelector`` from M011
for LLM models). Filters ``TransformParams`` candidates based on a
``StageRequirements`` definition: only candidates whose
``transform_type`` is in ``allowed_kinds`` AND (for TILE candidates)
whose ``tile_size >= min_tile_size`` are kept.

Used by the EvolutionEngine integration path to seed the genome with
stage-appropriate candidates before mutation/evaluation. Pure
application; no infrastructure imports (R002).

Mirrors the per-stage selection pattern from
``application/model_selector.py`` (M011).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from active_skill_system.domain.compiler_types import CompilerNodeKind, TransformParams


@dataclass(frozen=True)
class StageRequirements:
    """Requirements a candidate TransformParams must satisfy for a given stage.

    Carries:
      - stage_name: human-readable name (non-empty string).
      - allowed_kinds: frozenset[CompilerNodeKind] of transform kinds allowed.
      - min_tile_size: minimum tile_size for TILE candidates (int >= 1).
    """

    stage_name: str
    allowed_kinds: frozenset[CompilerNodeKind] = field(default_factory=frozenset)
    min_tile_size: int = 1

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.stage_name, str) or not self.stage_name.strip():
            errors.append(f"stage_name must be a non-empty string (got {self.stage_name!r})")
        if not isinstance(self.allowed_kinds, frozenset):
            errors.append(f"allowed_kinds must be a frozenset (got {type(self.allowed_kinds).__name__})")
        else:
            for kind in self.allowed_kinds:
                if not isinstance(kind, CompilerNodeKind):
                    errors.append(
                        f"allowed_kinds elements must be CompilerNodeKind (got {type(kind).__name__})"
                    )
        if not isinstance(self.min_tile_size, int) or isinstance(self.min_tile_size, bool) or self.min_tile_size < 1:
            errors.append(f"min_tile_size must be an int >= 1 (got {self.min_tile_size!r})")
        if errors:
            raise ValueError("StageRequirements invariant violation: " + "; ".join(errors))


class TransformationSelector:
    """Per-stage selector for TransformParams candidates.

    Stages are registered via ``register_stage(stage_requirements)``;
    ``select_for_stage(stage_name, candidates)`` returns a tuple of
    candidates matching the stage's ``allowed_kinds`` and ``min_tile_size``.
    Empty tuple is returned for unknown stages or over-constrained
    selections — the EvolutionEngine handles empty genomes via the
    ratchet semantics (M015 S03).
    """

    def __init__(self) -> None:
        self._stages: dict[str, StageRequirements] = {}

    def register_stage(self, stage: StageRequirements) -> None:
        """Register a stage. Later registration with the same stage_name wins."""
        if not isinstance(stage, StageRequirements):
            raise TypeError(f"stage must be a StageRequirements (got {type(stage).__name__})")
        self._stages[stage.stage_name] = stage

    def stages(self) -> dict[str, StageRequirements]:
        """Return a snapshot of registered stages."""
        return dict(self._stages)

    def select_for_stage(
        self,
        stage_name: str,
        candidates: tuple[TransformParams, ...] | list[TransformParams],
    ) -> tuple[TransformParams, ...]:
        """Return candidates matching the stage requirements.

        Filters by:
          - ``candidate.transform_type in stage.allowed_kinds``
          - for TILE candidates: ``candidate.params["tile_size"] >= stage.min_tile_size``

        Unknown stage returns empty tuple. Empty allowed_kinds also returns
        empty tuple (signals "match nothing").
        """
        stage = self._stages.get(stage_name)
        if stage is None:
            return ()
        if not stage.allowed_kinds:
            return ()
        out: list[TransformParams] = []
        for cand in candidates:
            if not isinstance(cand, TransformParams):
                continue
            if cand.transform_type not in stage.allowed_kinds:
                continue
            # Apply min_tile_size constraint for TILE candidates.
            if cand.transform_type is CompilerNodeKind.TRANSFORM_TILE:
                tile_size = int(cand.params.get("tile_size", 1))
                if tile_size < stage.min_tile_size:
                    continue
            out.append(cand)
        return tuple(out)
