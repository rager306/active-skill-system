"""L2 Application — Ratchet ledger (M033 S01).

Append-only JSONL log of permanent improvements. Each entry is a
frozen dataclass with: id, timestamp, area, diff, justification, test_ref.

The ratchet principle (D002): every agent error becomes a permanent
improvement. Existing entries are immutable — only superseded by new
entries with higher ids.

Pure application. NO infrastructure imports (R002).
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# id format: ratchet-<uuid8> (short, sortable).
_ID_PATTERN = re.compile(r"^ratchet-[a-f0-9]{1,16}$")


@dataclass(frozen=True)
class RatchetEntry:
    """One permanent improvement entry.

    Carries:
      - id: unique entry id (e.g. "ratchet-a1b2c3d4"). Immutable.
      - timestamp: ISO 8601 UTC string.
      - area: short tag (e.g. "compiler", "r007", "impeccable"). Non-empty.
      - diff: human-readable description of the change.
      - justification: why this improvement is permanent.
      - test_ref: path or identifier of the test that prevents regression.
    """

    id: str
    timestamp: str
    area: str
    diff: str
    justification: str
    test_ref: str

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.id, str) or not _ID_PATTERN.match(self.id):
            errors.append(
                f"id must match {_ID_PATTERN.pattern!r} (got {self.id!r})"
            )
        if not isinstance(self.timestamp, str) or not self.timestamp:
            errors.append("timestamp must be a non-empty string")
        if not isinstance(self.area, str) or not self.area.strip():
            errors.append("area must be a non-empty string")
        if not isinstance(self.diff, str) or not self.diff.strip():
            errors.append("diff must be a non-empty string")
        if not isinstance(self.justification, str) or not self.justification.strip():
            errors.append("justification must be a non-empty string")
        if not isinstance(self.test_ref, str) or not self.test_ref.strip():
            errors.append("test_ref must be a non-empty string")
        if errors:
            raise ValueError("RatchetEntry invariant violation: " + "; ".join(errors))

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @staticmethod
    def from_json(line: str) -> "RatchetEntry":
        d = json.loads(line)
        return RatchetEntry(
            id=d["id"], timestamp=d["timestamp"], area=d["area"],
            diff=d["diff"], justification=d["justification"], test_ref=d["test_ref"],
        )

    @staticmethod
    def new(
        area: str, diff: str, justification: str, test_ref: str,
    ) -> "RatchetEntry":
        """Create a new ratchet entry with auto-generated id and timestamp."""
        return RatchetEntry(
            id=f"ratchet-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            area=area, diff=diff, justification=justification, test_ref=test_ref,
        )


@dataclass(frozen=True)
class HarnessRules:
    """Parsed AGENTS.md rules.

    Carries:
      - sections: list of (heading, body) tuples in document order.
      - source_path: path to the loaded AGENTS.md file.
    """

    sections: list[tuple[str, str]] = field(default_factory=list)
    source_path: str = ""

    def section(self, heading: str) -> str | None:
        """Return the body of the first section matching `heading` (case-sensitive)."""
        for h, b in self.sections:
            if h == heading:
                return b
        return None

    def required_sections(self, *headings: str) -> list[str]:
        """Return the list of `headings` that are missing from sections."""
        present = {h for h, _ in self.sections}
        return [h for h in headings if h not in present]


# ── Module-level exports ──────────────────────────────────────────────────


def load_harness(agents_md_path: str | Path) -> HarnessRules:
    """Parse AGENTS.md into HarnessRules.

    Sections start with `## ` (level-2 markdown headings). Anything before
    the first heading is treated as the preamble (not a section).
    """
    path = Path(agents_md_path)
    if not path.is_file():
        raise FileNotFoundError(f"AGENTS.md not found: {path}")
    text = path.read_text(encoding="utf-8")
    sections: list[tuple[str, str]] = []
    current_heading: str | None = None
    current_body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            # Flush previous section.
            if current_heading is not None:
                sections.append((current_heading, "\n".join(current_body).strip()))
            current_heading = line[3:].strip()
            current_body = []
        elif current_heading is not None:
            current_body.append(line)
    if current_heading is not None:
        sections.append((current_heading, "\n".join(current_body).strip()))
    return HarnessRules(sections=sections, source_path=str(path))


class RatchetLedger:
    """Append-only ratchet ledger backed by a JSONL file.

    Public API:
      - load(path): read all entries (sorted by id) from JSONL.
      - append(entry): reject duplicate id; persist immediately.
      - entries: list of entries in insertion order.
      - find_by_area(area): filter entries by area.
    """

    def __init__(self, path: str | Path, entries: list[RatchetEntry] | None = None) -> None:
        self._path = Path(path)
        self._entries: list[RatchetEntry] = list(entries) if entries is not None else []

    @property
    def path(self) -> Path:
        return self._path

    @property
    def entries(self) -> list[RatchetEntry]:
        return list(self._entries)

    def __iter__(self) -> Iterator[RatchetEntry]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def find_by_area(self, area: str) -> list[RatchetEntry]:
        return [e for e in self._entries if e.area == area]

    def append(self, entry: RatchetEntry, *, persist: bool = True) -> None:
        """Append a new entry. Reject duplicate id (append-only invariant)."""
        if not isinstance(entry, RatchetEntry):
            raise TypeError(f"entry must be a RatchetEntry (got {type(entry).__name__})")
        if any(e.id == entry.id for e in self._entries):
            raise ValueError(
                f"Ratchet entry with id {entry.id!r} already exists; "
                "ratchet is append-only — create a new entry with a higher id instead."
            )
        self._entries.append(entry)
        if persist:
            self.save()

    def save(self) -> None:
        """Persist all entries to JSONL (one per line, sorted by id)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        sorted_entries = sorted(self._entries, key=lambda e: e.id)
        with self._path.open("w", encoding="utf-8") as f:
            for e in sorted_entries:
                f.write(e.to_json() + "\n")

    @staticmethod
    def load(path: str | Path) -> "RatchetLedger":
        """Load entries from a JSONL file. Missing file → empty ledger."""
        p = Path(path)
        if not p.is_file():
            return RatchetLedger(p)
        entries: list[RatchetEntry] = []
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(RatchetEntry.from_json(line))
        return RatchetLedger(p, entries=entries)

    def integrity_check(self) -> dict[str, Any]:
        """Return a dict describing ledger integrity (sorted by id, no duplicates)."""
        ids = [e.id for e in self._entries]
        return {
            "count": len(ids),
            "unique_ids": len(set(ids)) == len(ids),
            "sorted": ids == sorted(ids),
        }