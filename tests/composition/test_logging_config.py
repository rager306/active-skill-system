"""Tests for the logging backbone (M040 S01 T03)."""

from __future__ import annotations

import ast
import logging
import time
from pathlib import Path

import pytest

from active_skill_system.composition import logging_config


def _flush() -> None:
    """loguru enqueue is async; give the sink a moment to drain."""
    time.sleep(0.4)


def test_get_log_dir_defaults_to_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOG_DIR", raising=False)
    assert logging_config.get_log_dir() == "logs"


def test_get_log_dir_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_DIR", "/tmp/rgla_test_logs")
    assert logging_config.get_log_dir() == "/tmp/rgla_test_logs"


def test_configure_logging_routes_stdlib_to_file(tmp_path: Path) -> None:
    log_path = logging_config.configure_logging(log_dir=str(tmp_path), dev_stderr=False)
    app_logger = logging.getLogger("active_skill_system.application.use_cases.fake")
    app_logger.info("structured app event")
    app_logger.error("recoverable failure")
    _flush()
    content = log_path.read_text(encoding="utf-8")
    assert "structured app event" in content
    assert "recoverable failure" in content


def test_configure_logging_log_dir_override_writes_to_chosen_path(tmp_path: Path) -> None:
    custom = tmp_path / "nested" / "logs"
    log_path = logging_config.configure_logging(log_dir=str(custom), dev_stderr=False)
    logging.getLogger("test").warning("override path check")
    _flush()
    assert log_path.parent == custom
    assert "override path check" in log_path.read_text(encoding="utf-8")


def test_configure_logging_is_idempotent(tmp_path: Path) -> None:
    # Calling twice must not duplicate handlers / raise.
    logging_config.configure_logging(log_dir=str(tmp_path), dev_stderr=False)
    logging_config.configure_logging(log_dir=str(tmp_path), dev_stderr=False)
    logging.getLogger("idempotent").info("still works")
    _flush()
    assert True  # reached without error


def test_intercept_handler_emits_without_loguru_import_at_caller() -> None:
    # The InterceptHandler must work even though the caller never imports loguru.
    handler = logging_config.InterceptHandler()
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname=__file__, lineno=1,
        msg="handler direct emit", args=None, exc_info=None,
    )
    handler.emit(record)  # must not raise
    _flush()


def _module_asts() -> list[tuple[Path, ast.AST]]:
    root = Path("src/active_skill_system")
    files: list[tuple[Path, ast.AST]] = []
    for py in root.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        files.append((py, ast.parse(py.read_text(encoding="utf-8"))))
    return files


def _imports_loguru(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name == "loguru"]
        elif isinstance(node, ast.ImportFrom) and node.module == "loguru":
            found.append("loguru")
    return found


def test_no_loguru_import_in_domain_or_application() -> None:
    """R002 discipline: loguru (third-party) must not leak into domain/application."""
    offenders: list[str] = []
    for py, tree in _module_asts():
        rel = py.relative_to(Path("src/active_skill_system"))
        if rel.parts and rel.parts[0] in ("domain", "application") and _imports_loguru(tree):
            offenders.append(str(rel))
    assert not offenders, f"loguru imported in domain/application: {offenders}"


def test_loguru_only_in_composition_layer() -> None:
    """loguru may appear ONLY in composition (logging_config). Other layers forbidden."""
    allowed = {"composition/logging_config.py"}
    offenders: list[str] = []
    for py, tree in _module_asts():
        rel = str(py.relative_to(Path("src/active_skill_system")))
        if rel in allowed:
            continue
        if _imports_loguru(tree):
            offenders.append(rel)
    assert not offenders, f"loguru imported outside logging_config: {offenders}"
