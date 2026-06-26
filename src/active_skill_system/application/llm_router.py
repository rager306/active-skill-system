"""L2 Application — LLMRouter (M038 S01).

Multi-provider routing layer built on top of ``ModelRegistry`` and
``ModelSelector``. Selects the cheapest healthy provider/model for a pipeline
stage, then falls back through the provider chain on failure.

The router is pure application: provider instances (``LLMProviderPort``) are
INJECTED via the constructor — the application layer imports no adapters
(R002). ``ProviderHealth`` (domain) tracks consecutive failures per provider
so degraded providers are temporarily skipped by selection.

The layering seam (registry, providers, health map) is REQUIRED at
construction time — the router raises a clear error if any is missing, and a
``test_init_rejects_missing_*`` test makes the contract explicit (the same
pattern that caught an L2→L3 import leak in M016 S03 T03).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from active_skill_system.application.model_registry import ModelRegistry
from active_skill_system.application.model_selector import ModelSelector, StageType
from active_skill_system.application.ports.llm import LLMProviderPort
from active_skill_system.domain.model_genome import ModelCapability, ModelGenome
from active_skill_system.domain.provider_health import ProviderHealth


@dataclass(frozen=True)
class RoutingResult:
    """Outcome of a routed LLM request.

    Carries:
      - provider_id: the provider that ultimately served the request.
      - genome: the ModelGenome that was selected and used.
      - used_fallback: True when the primary provider failed and a fallback served.
      - attempts: ordered tuple of (provider_id, succeeded) for each provider tried.
    """

    provider_id: str
    genome: ModelGenome
    used_fallback: bool
    attempts: tuple[tuple[str, bool], ...] = ()


class LLMRouter:
    """Cost-aware, resilient multi-provider router.

    Usage::

        router = LLMRouter(registry=reg, providers={...})
        result = router.route_with_fallback(stage, required_caps, request)
    """

    def __init__(
        self,
        *,
        registry: ModelRegistry,
        providers: dict[str, LLMProviderPort],
        selector: ModelSelector | None = None,
        health: dict[str, ProviderHealth] | None = None,
        max_failures: int = 3,
    ) -> None:
        if not isinstance(registry, ModelRegistry):
            raise TypeError(f"registry must be a ModelRegistry (got {type(registry).__name__})")
        if not isinstance(providers, dict) or not providers:
            raise ValueError(f"providers must be a non-empty dict (got {providers!r})")
        bad = {k: type(v).__name__ for k, v in providers.items() if not _is_provider(v)}
        if bad:
            raise TypeError(f"providers values must be LLMProviderPort (got {bad})")
        self._registry = registry
        self._providers = dict(providers)
        self._selector = selector if selector is not None else ModelSelector()
        self._health: dict[str, ProviderHealth] = {
            pid: (health[pid] if health and pid in health else ProviderHealth(provider_id=pid))
            for pid in self._providers
        }
        self._max_failures = max_failures

    def health(self, provider_id: str) -> ProviderHealth:
        """Return the current health snapshot for a provider."""
        if provider_id not in self._health:
            raise KeyError(f"unknown provider_id {provider_id!r}")
        return self._health[provider_id]

    def select(
        self,
        stage: StageType,
        required_capabilities: frozenset[ModelCapability],
    ) -> ModelGenome | None:
        """Select the cheapest healthy model for the stage, or None."""
        candidates = self._selector.select(stage, required_capabilities, self._registry)
        if candidates is None:
            return None
        # Prefer healthy providers; if the selected model's provider is unhealthy,
        # fall back to the next cheapest healthy match.
        ordered = self._ordered_healthy_models(stage, required_capabilities)
        return ordered[0] if ordered else None

    def _ordered_healthy_models(
        self,
        stage: StageType,
        required_capabilities: frozenset[ModelCapability],
    ) -> list[ModelGenome]:
        """All candidate models for the stage, filtered to healthy providers, cheapest first."""
        if required_capabilities:
            models = [
                g
                for g in self._registry.list_all()
                if all(g.has_capability(c) for c in required_capabilities)
            ]
        else:
            models = list(self._registry.list_all())
        models = [g for g in models if self._health[g.provider_id].is_healthy(max_failures=self._max_failures)]
        preference = _stage_preference(stage)
        if preference:
            preferred = [g for g in models if g.has_capability(preference)]
            if preferred:
                models = preferred
        models.sort(key=lambda g: g.cost_input_per_1m + g.cost_output_per_1m)
        return models

    def route_with_fallback(
        self,
        stage: StageType,
        required_capabilities: frozenset[ModelCapability],
        request: dict[str, Any],
    ) -> RoutingResult | None:
        """Try providers in cost order; fall back on failure.

        ``request`` is passed to ``LLMProviderPort.complete`` as keyword args.
        On exception or a falsy return, the provider is marked unhealthy and
        the next healthy model is tried.
        """
        ordered = self._ordered_healthy_models(stage, required_capabilities)
        attempts: list[tuple[str, bool]] = []
        used_fallback = False
        for idx, genome in enumerate(ordered):
            provider = self._providers[genome.provider_id]
            if idx > 0:
                used_fallback = True
            try:
                result = provider.complete(**request)
            except Exception as e:  # noqa: BLE001 — router must not leak provider exceptions
                self._mark_failure(genome.provider_id, f"{type(e).__name__}: {e}")
                attempts.append((genome.provider_id, False))
                continue
            if not result:
                self._mark_failure(genome.provider_id, "provider returned no result")
                attempts.append((genome.provider_id, False))
                continue
            self._mark_success(genome.provider_id)
            attempts.append((genome.provider_id, True))
            return RoutingResult(
                provider_id=genome.provider_id,
                genome=genome,
                used_fallback=used_fallback,
                attempts=tuple(attempts),
            )
        if attempts:
            return None
        return None

    def _mark_failure(self, provider_id: str, error: str) -> None:
        self._health[provider_id] = self._health[provider_id].record_failure(error)

    def _mark_success(self, provider_id: str) -> None:
        self._health[provider_id] = self._health[provider_id].record_success()


def _is_provider(obj: Any) -> bool:
    """Duck-type check for LLMProviderPort (Protocol is runtime_checkable)."""
    return hasattr(obj, "complete") and hasattr(obj, "default_model")


def _stage_preference(stage: StageType) -> ModelCapability | None:
    prefs = {
        StageType.PARSE: ModelCapability.FAST,
        StageType.VISION_EXTRACTION: ModelCapability.VISION,
        StageType.SYNTHESIZE: ModelCapability.THINKING,
        StageType.REPAIR: ModelCapability.TOOLS,
    }
    return prefs.get(stage)
