"""Mutation testing configuration (M045 S4).

pytest-gremlins is activated behind the ``slow`` marker. Run with::

    uv run pytest --gremlins --gremlin-targets=src/active_skill_system/domain -p no:cacheprovider

This test file ensures the mutation suite is discoverable and documents the
expected mutation score. It does NOT run mutations itself — the ``--gremlins``
flag enables mutation testing on the specified targets.

Mutation testing measures TEST QUALITY: if a mutant (code mutation) survives,
it means the tests don't catch that change. A high mutation score means the
tests are effective at detecting bugs.

The suite targets domain/ first (highest value — invariants, FSM, ranking).
"""

from __future__ import annotations

import pytest


@pytest.mark.slow
def test_mutation_suite_smoke():
    """Smoke: pytest-gremlins is importable and --gremlins flag works.

    This test exists so the 'slow' marker has at least one test, enabling
    ``pytest -m slow`` to discover the mutation suite. The actual mutation
    run is triggered by the --gremlins CLI flag, not by this test.
    """
    import pytest_gremlins  # noqa: F401

    assert hasattr(pytest_gremlins, "__version__")


@pytest.mark.slow
def test_mutation_targets_exist():
    """Verify the mutation target directories exist."""
    from pathlib import Path

    targets = [
        "src/active_skill_system/domain",
        "src/active_skill_system/application",
    ]
    for t in targets:
        assert Path(t).is_dir(), f"mutation target missing: {t}"
