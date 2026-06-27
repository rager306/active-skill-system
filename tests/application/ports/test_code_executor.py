"""Tests for CodeExecutorPort (M044 S01 T01)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from active_skill_system.application.ports.code_executor import (
    CodeExecutorPort,
    ExecutionResult,
)


def test_execution_result_ok_property():
    ok = ExecutionResult(stdout="hello", exit_code=0)
    assert ok.ok is True

    errored = ExecutionResult(error="boom")
    assert errored.ok is False

    bad_exit = ExecutionResult(exit_code=1)
    assert bad_exit.ok is False


def test_execution_result_defaults():
    r = ExecutionResult()
    assert r.stdout == ""
    assert r.exit_code == 0
    assert r.error is None
    assert r.ok is True


def test_execution_result_is_frozen():
    r = ExecutionResult(stdout="x")
    with pytest.raises(FrozenInstanceError):
        r.stdout = "y"  # type: ignore[misc]


def test_code_executor_port_is_protocol():
    class _Fake:
        def execute(self, code_path: str, *, timeout: float = 30.0) -> ExecutionResult:
            return ExecutionResult(stdout="ok")

    assert isinstance(_Fake(), CodeExecutorPort)
