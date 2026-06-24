"""L1 Domain - Active Skill System entities and invariants.

Pure domain. NO I/O, NO infrastructure imports. Frozen dataclasses with
__post_init__ invariant validation; violations raise ValueError. This
module imports ONLY from stdlib + typing (R002 - domain must be infra-free).

Entities (re-exported for convenient `from active_skill_system.domain import X`):

  Genome (and GenomeId)
    A self-contained unit of capability with a signature, a non-empty set
    of capabilities, and a list of invariants that must hold for any
    Expression derived from it.

  Expression (and ExpressionId)
    A concrete invocation of a Genome, with arguments, a timestamp, an
    evidence chain, and a status.

  Evolution (and EvolutionId, Mutation)
    A derivation: a new genome produced from one or more parents by
    applying a Mutation, with a fitness score in [0, 1].

  GovernancePolicy
    Policy constraints enforced by the runtime during evolution (max
    depth, review threshold, frozen flag).

Invariants are enforced at construction time (raise ValueError on
violation). Per-instance invariants (Genome.invariants) are exposed via
check_invariants() for the application layer.
"""

from active_skill_system.domain.evolution import (
    Evolution,
    EvolutionId,
    Mutation,
)
from active_skill_system.domain.expression import Expression, ExpressionId
from active_skill_system.domain.genome import Genome, GenomeId
from active_skill_system.domain.governance import GovernancePolicy

__all__ = [
    "Evolution",
    "EvolutionId",
    "Expression",
    "ExpressionId",
    "Genome",
    "GenomeId",
    "GovernancePolicy",
    "Mutation",
]
