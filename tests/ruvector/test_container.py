"""Tests for ruvector Python stub (M035 S01)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# Ensure ruvector/ is importable.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import ruvector  # noqa: E402
from ruvector import Event, RuVectorContainer  # noqa: E402

# ── Version + imports ──────────────────────────────────────────────────


def test_ruvector_version() -> None:
    assert ruvector.__version__ == "0.1.0"


def test_ruvector_exports() -> None:
    assert hasattr(ruvector, "RuVectorContainer")
    assert hasattr(ruvector, "Event")
    assert hasattr(ruvector, "__version__")


# ── Container basic API ────────────────────────────────────────────────


def test_container_default_path() -> None:
    c = RuVectorContainer()
    assert c.path == ":memory:"
    assert len(c) == 0


def test_container_rejects_non_string_path() -> None:
    with pytest.raises(TypeError, match="path must be a string"):
        RuVectorContainer(path=123)  # type: ignore[arg-type]


def test_container_add_event_returns_event() -> None:
    c = RuVectorContainer()
    ev = c.add_event(event_id="e1", event_type="thought", payload={"text": "hello"})
    assert isinstance(ev, Event)
    assert ev.id == "e1"
    assert ev.event_type == "thought"
    assert ev.payload == {"text": "hello"}
    assert ev.timestamp != ""
    assert len(c) == 1


def test_container_rejects_empty_event_id() -> None:
    c = RuVectorContainer()
    with pytest.raises(ValueError, match="event_id must be a non-empty"):
        c.add_event(event_id="", event_type="thought")


def test_container_rejects_empty_event_type() -> None:
    c = RuVectorContainer()
    with pytest.raises(ValueError, match="event_type must be a non-empty"):
        c.add_event(event_id="e1", event_type="")


def test_container_query_filters_by_type() -> None:
    c = RuVectorContainer()
    c.add_event("e1", "thought")
    c.add_event("e2", "claim")
    c.add_event("e3", "thought")
    thoughts = c.query(event_type="thought")
    assert len(thoughts) == 2
    assert all(e.event_type == "thought" for e in thoughts)


def test_container_query_returns_all_when_no_filter() -> None:
    c = RuVectorContainer()
    c.add_event("e1", "thought")
    c.add_event("e2", "claim")
    assert len(c.query()) == 2


def test_container_get_finds_by_id() -> None:
    c = RuVectorContainer()
    c.add_event("e1", "thought")
    c.add_event("e2", "claim")
    assert c.get("e1").event_type == "thought"
    assert c.get("e2").event_type == "claim"
    assert c.get("nonexistent") is None


def test_container_iterates() -> None:
    c = RuVectorContainer()
    c.add_event("e1", "thought")
    c.add_event("e2", "thought")
    ids = [e.id for e in c]
    assert ids == ["e1", "e2"]


# ── Module hygiene (R002) ──────────────────────────────────────────────


def test_ruvector_module_infra_free() -> None:
    mod = importlib.import_module("ruvector")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"ruvector must not contain '{forbidden}' (R002)"


def test_ruvector_has_no_pyo3_imports() -> None:
    """Verify ruvector is currently pure-Python (no Rust build required)."""
    mod = importlib.import_module("ruvector")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("from ruvector._native", "import _native", "import ruvector._ruvector"):
        assert forbidden not in src, "ruvector should not import any native extension yet"
