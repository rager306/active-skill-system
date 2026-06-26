"""Tests for AGENTS.md harness + ratchet ledger (M033 S01)."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


# Ensure the harness/ and ratchet/ packages are importable from the project root.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from harness import HarnessRules, RatchetEntry, RatchetLedger, load_harness  # noqa: E402


# ── AGENTS.md sections ──────────────────────────────────────────────────


def test_agents_md_exists() -> None:
    md = _ROOT / "harness" / "AGENTS.md"
    assert md.is_file()
    text = md.read_text(encoding="utf-8")
    assert "## 1. Agent Protocol" in text
    assert "## 2. Framework Integration" in text
    assert "## 3. Evidence Requirements" in text
    assert "## 4. Ratchet Obligation" in text
    assert "## 5. Skill References" in text


def test_load_harness_parses_all_sections() -> None:
    rules = load_harness(_ROOT / "harness" / "AGENTS.md")
    assert isinstance(rules, HarnessRules)
    section_names = [h for h, _ in rules.sections]
    assert "1. Agent Protocol" in section_names
    assert "2. Framework Integration" in section_names
    assert "4. Ratchet Obligation" in section_names


def test_load_harness_required_sections() -> None:
    rules = load_harness(_ROOT / "harness" / "AGENTS.md")
    missing = rules.required_sections("1. Agent Protocol", "4. Ratchet Obligation")
    assert missing == []


def test_load_harness_returns_missing_sections() -> None:
    rules = load_harness(_ROOT / "harness" / "AGENTS.md")
    missing = rules.required_sections("Nonexistent Section")
    assert missing == ["Nonexistent Section"]


def test_load_harness_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_harness(tmp_path / "nonexistent.md")


def test_section_returns_body_for_present_heading() -> None:
    rules = load_harness(_ROOT / "harness" / "AGENTS.md")
    body = rules.section("2. Framework Integration")
    assert body is not None
    assert "L0 domain" in body
    assert "R002" in body


def test_section_returns_none_for_missing_heading() -> None:
    rules = load_harness(_ROOT / "harness" / "AGENTS.md")
    assert rules.section("Nonexistent") is None


# ── RatchetEntry invariant ──────────────────────────────────────────────


def test_ratchet_entry_rejects_invalid_id() -> None:
    with pytest.raises(ValueError, match="id must match"):
        RatchetEntry(
            id="not-a-valid-id", timestamp="2026-01-01T00:00:00+00:00",
            area="compiler", diff="x", justification="y", test_ref="z",
        )


def test_ratchet_entry_rejects_empty_area() -> None:
    with pytest.raises(ValueError, match="area must be a non-empty"):
        RatchetEntry(
            id="ratchet-abc12345", timestamp="2026-01-01T00:00:00+00:00",
            area="", diff="x", justification="y", test_ref="z",
        )


def test_ratchet_entry_rejects_empty_diff() -> None:
    with pytest.raises(ValueError, match="diff must be a non-empty"):
        RatchetEntry(
            id="ratchet-abc12345", timestamp="2026-01-01T00:00:00+00:00",
            area="compiler", diff="", justification="y", test_ref="z",
        )


def test_ratchet_entry_new_generates_id_and_timestamp() -> None:
    entry = RatchetEntry.new(area="compiler", diff="test", justification="why", test_ref="tests/x.py")
    assert entry.id.startswith("ratchet-")
    assert len(entry.id) > len("ratchet-")
    assert entry.timestamp.endswith("+00:00") or "T" in entry.timestamp
    assert entry.area == "compiler"
    assert entry.diff == "test"


def test_ratchet_entry_round_trip_via_json() -> None:
    entry = RatchetEntry.new(area="r007", diff="add import-linter", justification="layering", test_ref="tests/test_layering.py")
    roundtrip = RatchetEntry.from_json(entry.to_json())
    assert roundtrip == entry


# ── RatchetLedger lifecycle ─────────────────────────────────────────────


def test_ledger_load_from_missing_file_returns_empty(tmp_path: Path) -> None:
    ledger = RatchetLedger.load(tmp_path / "missing.jsonl")
    assert len(ledger) == 0
    assert ledger.entries == []


def test_ledger_append_persists_to_file(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = RatchetLedger(path)
    entry = RatchetEntry.new(area="compiler", diff="x", justification="y", test_ref="z.py")
    ledger.append(entry)
    assert path.is_file()
    text = path.read_text(encoding="utf-8").strip()
    assert json.loads(text)["id"] == entry.id


def test_ledger_rejects_duplicate_id(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = RatchetLedger(path)
    entry1 = RatchetEntry(id="ratchet-deadbeef", timestamp="2026-01-01T00:00:00+00:00",
                            area="compiler", diff="a", justification="b", test_ref="c")
    ledger.append(entry1)
    entry2 = RatchetEntry(id="ratchet-deadbeef", timestamp="2026-01-02T00:00:00+00:00",
                            area="compiler", diff="x", justification="y", test_ref="z")
    with pytest.raises(ValueError, match="already exists"):
        ledger.append(entry2)


def test_ledger_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger1 = RatchetLedger(path)
    e1 = RatchetEntry(id="ratchet-00000001", timestamp="2026-01-01T00:00:00+00:00",
                       area="compiler", diff="a", justification="b", test_ref="c")
    e2 = RatchetEntry(id="ratchet-00000002", timestamp="2026-01-02T00:00:00+00:00",
                       area="sql", diff="x", justification="y", test_ref="z")
    ledger1.append(e1)
    ledger1.append(e2)
    ledger2 = RatchetLedger.load(path)
    assert len(ledger2) == 2
    assert ledger2.entries[0] == e1
    assert ledger2.entries[1] == e2


def test_ledger_integrity_check(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = RatchetLedger(path)
    e1 = RatchetEntry(id="ratchet-00000001", timestamp="2026-01-01T00:00:00+00:00",
                       area="compiler", diff="a", justification="b", test_ref="c")
    e2 = RatchetEntry(id="ratchet-00000002", timestamp="2026-01-02T00:00:00+00:00",
                       area="sql", diff="x", justification="y", test_ref="z")
    ledger.append(e1)
    ledger.append(e2)
    result = ledger.integrity_check()
    assert result["count"] == 2
    assert result["unique_ids"] is True
    assert result["sorted"] is True


def test_ledger_find_by_area(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = RatchetLedger(path)
    ledger.append(RatchetEntry(id="ratchet-00000001", timestamp="2026-01-01T00:00:00+00:00",
                                area="compiler", diff="a", justification="b", test_ref="c"))
    ledger.append(RatchetEntry(id="ratchet-00000002", timestamp="2026-01-02T00:00:00+00:00",
                                area="sql", diff="x", justification="y", test_ref="z"))
    ledger.append(RatchetEntry(id="ratchet-00000003", timestamp="2026-01-03T00:00:00+00:00",
                                area="compiler", diff="p", justification="q", test_ref="r"))
    found = ledger.find_by_area("compiler")
    assert len(found) == 2
    assert all(e.area == "compiler" for e in found)


# ── Module hygiene (R002) ──────────────────────────────────────────────


def test_harness_module_infra_free() -> None:
    mod = importlib.import_module("harness")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"harness module must not contain '{forbidden}' (R002)"


def test_ratchet_module_infra_free() -> None:
    mod = importlib.import_module("ratchet")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"ratchet module must not contain '{forbidden}' (R002)"