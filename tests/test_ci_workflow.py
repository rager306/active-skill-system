"""Tests for the CI workflow (M039 S01 T02).

Asserts .github/workflows/ci.yml exists, parses as valid YAML, runs the three
gates (pytest, ruff check, lint-imports), triggers on push and pull_request,
and installs via uv. Fully offline — no gh subprocess.
"""

from __future__ import annotations

from pathlib import Path

import yaml

CI_PATH = Path(".github/workflows/ci.yml")


def _load_workflow() -> dict:
    assert CI_PATH.exists(), f"{CI_PATH} does not exist"
    return yaml.safe_load(CI_PATH.read_text(encoding="utf-8"))


def test_workflow_is_valid_yaml_and_has_a_job():
    wf = _load_workflow()
    assert isinstance(wf, dict)
    assert "jobs" in wf and wf["jobs"], "workflow must define at least one job"


def test_workflow_triggers_on_push_and_pull_request():
    wf = _load_workflow()
    triggers = wf.get(True) or wf.get("on") or {}
    assert "push" in triggers, "workflow must trigger on push"
    assert "pull_request" in triggers, "workflow must trigger on pull_request"


def _run_steps() -> list[str]:
    wf = _load_workflow()
    job = next(iter(wf["jobs"].values()))
    steps = job.get("steps", [])
    commands = []
    for step in steps:
        run = step.get("run")
        if run:
            commands.append(run)
    joined = "\n".join(commands)
    return joined


def test_workflow_runs_pytest_gate():
    assert "pytest" in _run_steps(), "workflow must run pytest"


def test_workflow_runs_ruff_gate():
    assert "ruff check" in _run_steps(), "workflow must run ruff check"


def test_workflow_runs_import_linter_gate():
    assert "lint-imports" in _run_steps(), "workflow must run lint-imports"


def test_workflow_installs_via_uv():
    steps_text = _run_steps()
    assert "uv sync" in steps_text or "uv pip install" in steps_text, (
        "workflow must install the project via uv"
    )


def test_workflow_has_concurrency_cancellation():
    wf = _load_workflow()
    concurrency = wf.get("concurrency", {})
    assert concurrency.get("cancel-in-progress") is True, (
        "workflow should cancel superseded runs"
    )
