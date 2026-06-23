"""Pytest configuration: hypothesis profiles, real-LLM gating, src on path.

- Property-based tests use Hypothesis; profile selected via HYPOTHESIS_PROFILE
  (default "dev"; CI sets "ci").
- Tests marked ``llm`` make real LLM calls and are skipped unless ``--runllm``
  is passed (keeps the default suite offline + deterministic + parallel-safe).
- Parallelism: ``pytest -n auto`` (pytest-xdist).
"""

from __future__ import annotations

import os

import pytest
from hypothesis import HealthCheck, Verbosity, settings

# ── Hypothesis profiles ────────────────────────────────────────────────────
settings.register_profile(
    "dev", max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
settings.register_profile(
    "ci", max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
settings.register_profile("debug", max_examples=10, verbosity=Verbosity.quiet, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


# ── Real-LLM gating ────────────────────────────────────────────────────────
def pytest_addoption(parser):
    parser.addoption(
        "--runllm",
        action="store_true",
        default=False,
        help="run tests marked `llm` (real provider calls)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runllm"):
        return
    skip_llm = pytest.mark.skip(reason="needs --runllm (real LLM call)")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip_llm)
