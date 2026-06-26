"""L2 Application — Skill loader (M034 S01).

Parses SKILL.md files with front-matter (YAML-like key: value) and
body sections (markdown ## headers). The shape mirrors HarnessRules (M033)
but is skill-scoped: one file = one skill.

Pure application. NO infrastructure imports (R002).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SkillManifest:
    """Parsed SKILL.md manifest.

    Carries:
      - front_matter: dict of front-matter key/value pairs (name, description, version, ...).
      - sections: list of (heading, body) tuples in document order.
      - source_path: path to the loaded SKILL.md file.
    """

    front_matter: dict[str, str] = field(default_factory=dict)
    sections: list[tuple[str, str]] = field(default_factory=list)
    source_path: str = ""

    def section(self, heading: str) -> str | None:
        for h, b in self.sections:
            if h == heading:
                return b
        return None

    @property
    def name(self) -> str:
        return self.front_matter.get("name", "")

    @property
    def version(self) -> str:
        return self.front_matter.get("version", "")

    @property
    def description(self) -> str:
        return self.front_matter.get("description", "")


def _parse_front_matter(text: str) -> tuple[dict[str, str], list[str]]:
    """Parse a simple YAML-like front-matter block from the start of a file.

    The front-matter is delimited by `---` lines at the start of the file.
    Supports `key: value` and `key:` (multi-line) syntax (multi-line values
    are joined as a single block). Returns (front_matter_dict, remaining_lines).
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, lines
    # Find the closing `---`.
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, lines
    fm_lines = lines[1:end_idx]
    remaining = lines[end_idx + 1:]
    fm: dict[str, str] = {}
    current_key: str | None = None
    current_value: list[str] = []
    def _flush() -> None:
        nonlocal current_key, current_value
        if current_key is not None:
            fm[current_key] = "\n".join(current_value).strip()
        current_key = None
        current_value = []
    for line in fm_lines:
        if line.startswith(" ") or line.startswith("\t"):
            # Continuation of previous key.
            if current_key is not None:
                current_value.append(line.strip())
            continue
        # New key: value line.
        if ":" in line:
            _flush()
            key, _, value = line.partition(":")
            current_key = key.strip()
            current_value = [value.strip()] if value.strip() else []
    _flush()
    return fm, remaining


def _parse_sections(body_lines: list[str]) -> list[tuple[str, str]]:
    """Parse ## sections from body lines."""
    sections: list[tuple[str, list[str]]] = []
    current_heading: str | None = None
    for line in body_lines:
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
            current_heading = line[3:].strip()
        elif current_heading is not None:
            sections[-1][1].append(line)
    return [(h, "\n".join(b).strip()) for h, b in sections if h is not None]


def load_skill(skill_md_path: str | Path) -> SkillManifest:
    """Parse a SKILL.md file into a SkillManifest."""
    path = Path(skill_md_path)
    if not path.is_file():
        raise FileNotFoundError(f"SKILL.md not found: {path}")
    text = path.read_text(encoding="utf-8")
    front_matter, remaining = _parse_front_matter(text)
    sections = _parse_sections(remaining)
    return SkillManifest(
        front_matter=front_matter,
        sections=sections,
        source_path=str(path),
    )


def list_skills(skills_dir: str | Path) -> list[SkillManifest]:
    """Load all skills in a .agents/skills/ directory."""
    root = Path(skills_dir)
    if not root.is_dir():
        return []
    out: list[SkillManifest] = []
    for sub in sorted(root.iterdir()):
        if sub.is_dir() and (sub / "SKILL.md").is_file():
            try:
                out.append(load_skill(sub / "SKILL.md"))
            except (FileNotFoundError, ValueError):
                continue
    return out
