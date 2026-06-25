"""L2 Application — IaCTransformationSelector (M023 S03).

Mirrors TransformationSelector (M020) and SQLTransformationSelector (M022)
for the IaC domain.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from active_skill_system.domain.iac_types import IaCNodeKind, IaCTransformParams


@dataclass(frozen=True)
class IaCStageRequirements:
    stage_name: str
    allowed_kinds: frozenset[IaCNodeKind] = field(default_factory=frozenset)
    min_vars: int = 0

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.stage_name, str) or not self.stage_name.strip():
            errors.append("stage_name must be non-empty")
        if not isinstance(self.allowed_kinds, frozenset):
            errors.append("allowed_kinds must be frozenset")
        if not isinstance(self.min_vars, int) or self.min_vars < 0:
            errors.append("min_vars must be a non-negative int")
        if errors:
            raise ValueError("IaCStageRequirements invariant violation: " + "; ".join(errors))


class IaCTransformationSelector:
    def __init__(self) -> None:
        self._stages: dict[str, IaCStageRequirements] = {}

    def register_stage(self, stage: IaCStageRequirements) -> None:
        if not isinstance(stage, IaCStageRequirements):
            raise TypeError("stage must be a IaCStageRequirements")
        self._stages[stage.stage_name] = stage

    def stages(self) -> dict[str, IaCStageRequirements]:
        return dict(self._stages)

    def select_for_stage(self, stage_name, candidates):
        stage = self._stages.get(stage_name)
        if stage is None or not stage.allowed_kinds:
            return ()
        out = []
        for cand in candidates:
            if not isinstance(cand, IaCTransformParams):
                continue
            if cand.transform_type not in stage.allowed_kinds:
                continue
            out.append(cand)
        return tuple(out)
