"""L2 Application — SQLTransformationSelector (M022 S01).

Per-stage selection for SQL plan optimization, analogous to
``TransformationSelector`` (M020) for the compiler domain.
Filters ``SQLTransformParams`` candidates based on a
``SQLStageRequirements`` definition: only candidates whose
``transform_type`` is in ``allowed_kinds`` AND (for ADD_INDEX candidates)
whose ``cols >= min_cols`` are kept.

Mirrors the per-stage selection pattern from
``application/transformation_selector.py`` (M020).

Pure application. NO infrastructure imports (R002).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from active_skill_system.domain.sql_types import SQLNodeKind, SQLTransformParams


@dataclass(frozen=True)
class SQLStageRequirements:
    """Requirements a candidate SQLTransformParams must satisfy for a given stage.

    Carries:
      - stage_name: human-readable name (non-empty string).
      - allowed_kinds: frozenset[SQLNodeKind] of transform kinds allowed.
      - min_cols: minimum cols for ADD_INDEX candidates (int >= 1).
    """

    stage_name: str
    allowed_kinds: frozenset[SQLNodeKind] = field(default_factory=frozenset)
    min_cols: int = 1

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.stage_name, str) or not self.stage_name.strip():
            errors.append(f"stage_name must be a non-empty string (got {self.stage_name!r})")
        if not isinstance(self.allowed_kinds, frozenset):
            errors.append(f"allowed_kinds must be a frozenset (got {type(self.allowed_kinds).__name__})")
        else:
            for kind in self.allowed_kinds:
                if not isinstance(kind, SQLNodeKind):
                    errors.append(
                        f"allowed_kinds elements must be SQLNodeKind (got {type(kind).__name__})"
                    )
        if not isinstance(self.min_cols, int) or isinstance(self.min_cols, bool) or self.min_cols < 1:
            errors.append(f"min_cols must be an int >= 1 (got {self.min_cols!r})")
        if errors:
            raise ValueError("SQLStageRequirements invariant violation: " + "; ".join(errors))


class SQLTransformationSelector:
    """Per-stage selector for SQLTransformParams candidates.

    Mirrors TransformationSelector (M020) for the SQL domain.
    """

    def __init__(self) -> None:
        self._stages: dict[str, SQLStageRequirements] = {}

    def register_stage(self, stage: SQLStageRequirements) -> None:
        if not isinstance(stage, SQLStageRequirements):
            raise TypeError(f"stage must be a SQLStageRequirements (got {type(stage).__name__})")
        self._stages[stage.stage_name] = stage

    def stages(self) -> dict[str, SQLStageRequirements]:
        return dict(self._stages)

    def select_for_stage(
        self,
        stage_name: str,
        candidates: tuple[SQLTransformParams, ...] | list[SQLTransformParams],
    ) -> tuple[SQLTransformParams, ...]:
        stage = self._stages.get(stage_name)
        if stage is None:
            return ()
        if not stage.allowed_kinds:
            return ()
        out: list[SQLTransformParams] = []
        for cand in candidates:
            if not isinstance(cand, SQLTransformParams):
                continue
            if cand.transform_type not in stage.allowed_kinds:
                continue
            if cand.transform_type is SQLNodeKind.SQL_TRANSFORM_ADD_INDEX:
                cols = int(cand.params.get("cols", 1))
                if cols < stage.min_cols:
                    continue
            out.append(cand)
        return tuple(out)
