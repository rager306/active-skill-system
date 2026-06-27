"""Tests for domain typed errors (M040 S02 T02)."""

from __future__ import annotations

from pathlib import Path

import pytest

from active_skill_system.domain.errors import (
    ActiveSkillError,
    BudgetExhausted,
    ContextLimitExceeded,
    EvolutionConverged,
    LLMUnavailable,
    ToolError,
)


def test_each_error_subclasses_active_skill_error():
    for cls in (ToolError, LLMUnavailable, BudgetExhausted, ContextLimitExceeded, EvolutionConverged):
        assert issubclass(cls, ActiveSkillError)


def test_errors_subclass_value_error_for_backward_compat():
    # Existing `except ValueError` sites must still catch during migration.
    for cls in (ActiveSkillError, ToolError, LLMUnavailable, BudgetExhausted):
        assert issubclass(cls, ValueError)


def test_error_instantiates_without_context():
    err = ToolError("transform failed")
    assert err.message == "transform failed"
    assert err.entity_id is None
    assert err.phase is None
    assert err.cause is None
    assert "transform failed" in str(err)


def test_error_carries_structured_context():
    inner = RuntimeError("db down")
    err = LLMUnavailable("no provider", entity_id="router", phase="route", cause=inner)
    assert err.entity_id == "router"
    assert err.phase == "route"
    assert err.cause is inner
    assert "entity_id='router'" in str(err)
    assert "phase='route'" in str(err)


def test_context_dict_for_logging():
    err = BudgetExhausted("max iterations", entity_id="loop-1", phase="evolve", cause=KeyError("x"))
    ctx = err.context()
    assert ctx["entity_id"] == "loop-1"
    assert ctx["phase"] == "evolve"
    assert ctx["cause_type"] == "KeyError"


def test_context_dict_without_cause():
    err = ToolError("bad args")
    ctx = err.context()
    assert ctx["cause_type"] is None
    assert ctx["entity_id"] is None


def test_catch_specific_typed_error():
    with pytest.raises(LLMUnavailable):
        raise LLMUnavailable("down")


def test_catch_as_value_error_backward_compat():
    # Old code catches ValueError — must still catch the typed error.
    with pytest.raises(ValueError):
        raise ToolError("fail")


def test_catch_as_active_skill_error():
    with pytest.raises(ActiveSkillError):
        raise EvolutionConverged("no improvement possible")


def test_errors_module_is_stdlib_only():
    """R003: domain module imports no third-party/infra."""
    src = Path("src/active_skill_system/domain/errors.py").read_text(encoding="utf-8")
    tree_dir = Path("src/active_skill_system/domain/errors.py")
    assert tree_dir.exists()
    import ast

    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name in ("__future__",) or alias.name in ("typing", "builtins"), (
                    f"unexpected import {alias.name!r}"
                )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert mod in ("__future__", "typing"), f"unexpected from-import {mod!r}"
