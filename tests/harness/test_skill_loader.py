"""Tests for skill loader (M034 S01)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# Ensure the harness/ package is importable from the project root.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from harness.skill_loader import SkillManifest, list_skills, load_skill  # noqa: E402

# ── SKILL.md files exist with valid front-matter ────────────────────────


def test_compiler_loop_skill_exists() -> None:
    path = _ROOT / ".agents" / "skills" / "compiler-loop" / "SKILL.md"
    assert path.is_file()
    skill = load_skill(path)
    assert isinstance(skill, SkillManifest)
    assert skill.name == "compiler-loop"
    assert skill.version == "1.0.0"
    assert "compiler" in skill.description.lower()


def test_sql_plan_opt_skill_exists() -> None:
    path = _ROOT / ".agents" / "skills" / "sql-plan-opt" / "SKILL.md"
    assert path.is_file()
    skill = load_skill(path)
    assert skill.name == "sql-plan-opt"
    assert "sql" in skill.description.lower()


def test_iac_plan_opt_skill_exists() -> None:
    path = _ROOT / ".agents" / "skills" / "iac-plan-opt" / "SKILL.md"
    assert path.is_file()
    skill = load_skill(path)
    assert skill.name == "iac-plan-opt"
    assert "iac" in skill.description.lower() or "infrastructure" in skill.description.lower()


# ── Skill loader: front-matter parsing ──────────────────────────────────


def test_load_skill_parses_front_matter() -> None:
    path = _ROOT / ".agents" / "skills" / "compiler-loop" / "SKILL.md"
    skill = load_skill(path)
    assert "name" in skill.front_matter
    assert "version" in skill.front_matter
    assert "license" in skill.front_matter


def test_load_skill_parses_sections() -> None:
    path = _ROOT / ".agents" / "skills" / "compiler-loop" / "SKILL.md"
    skill = load_skill(path)
    section_names = [h for h, _ in skill.sections]
    # Each skill has at minimum a "When to use this skill" section.
    assert any("When to use" in n for n in section_names)


def test_load_skill_section_lookup() -> None:
    path = _ROOT / ".agents" / "skills" / "compiler-loop" / "SKILL.md"
    skill = load_skill(path)
    body = skill.section("When to use this skill")
    assert body is not None
    assert "CompilerMetrics" in body


def test_load_skill_returns_none_for_missing_section() -> None:
    path = _ROOT / ".agents" / "skills" / "compiler-loop" / "SKILL.md"
    skill = load_skill(path)
    assert skill.section("Nonexistent Section") is None


def test_load_skill_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_skill(tmp_path / "nonexistent.md")


# ── Skill loader: list_skills ────────────────────────────────────────────


def test_list_skills_returns_all_three() -> None:
    skills = list_skills(_ROOT / ".agents" / "skills")
    names = {s.name for s in skills}
    assert "compiler-loop" in names
    assert "sql-plan-opt" in names
    assert "iac-plan-opt" in names
    # Verify the 3 new M034 skills are present (other skills may also exist).
    m034_skills = [s for s in skills if s.name in {"compiler-loop", "sql-plan-opt", "iac-plan-opt"}]
    assert len(m034_skills) == 3


def test_list_skills_returns_empty_for_missing_dir(tmp_path: Path) -> None:
    assert list_skills(tmp_path / "nonexistent") == []


# ── Skills reference real composition helpers ──────────────────────────


def test_compiler_loop_references_real_composition_helper() -> None:
    path = _ROOT / ".agents" / "skills" / "compiler-loop" / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    assert "composition/compiler_evolution.py" in text or "active_skill_system.composition.compiler_evolution" in text


def test_sql_plan_opt_references_real_composition_helper() -> None:
    path = _ROOT / ".agents" / "skills" / "sql-plan-opt" / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    assert "composition/sql_evolution.py" in text or "active_skill_system.composition.sql_evolution" in text


def test_iac_plan_opt_references_real_composition_helper() -> None:
    path = _ROOT / ".agents" / "skills" / "iac-plan-opt" / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    assert "composition/iac_evolution.py" in text or "active_skill_system.composition.iac_evolution" in text


# ── Module hygiene (R002) ──────────────────────────────────────────────


def test_skill_loader_module_infra_free() -> None:
    mod = importlib.import_module("harness.skill_loader")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"harness.skill_loader must not contain '{forbidden}' (R002)"
