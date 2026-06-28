"""ProgramBench smallest-CLI fixture (M053 S01, D014).

A self-contained CLI target — a JSON pretty-printer with --indent and
--sort-keys flags. Used as an external validator: the LLM must regenerate
this CLI from a brief spec, and parity tests verify behavioural parity.

Why this fixture:
- Real ProgramBench is 200 tasks × ~50 files × ~8600 LOC. We need a
  local proxy that exercises the same shape (CLI + tests + parity check)
  without the dataset pull.
- json_pretty is small (~30 LOC) but covers: arg parsing, file I/O,
  deterministic output, error handling, multiple flags.
- Parity tests are auto-generated from a fixture spec, matching
  ProgramBench's "behavioural parity" evaluation model.

This file is the TARGET (reference implementation). The parity tests
in tests/test_json_pretty_parity.py validate that an LLM-generated
candidate matches this target's behaviour.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _format_value(value: object, indent: int, sort_keys: bool, _depth: int = 0) -> str:
    """Format a JSON-compatible value with indent + sort_keys."""
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = sorted(value.items()) if sort_keys else value.items()
        pad = " " * (indent * (_depth + 1))
        inner = ",\n".join(
            f'{pad}{json.dumps(k)}: {_format_value(v, indent, sort_keys, _depth + 1)}'
            for k, v in items
        )
        closing_pad = " " * (indent * _depth) if _depth > 0 else ""
        return f"{{\n{inner}\n{closing_pad}}}"
    if isinstance(value, list):
        if not value:
            return "[]"
        pad = " " * (indent * (_depth + 1))
        inner = ",\n".join(
            f"{pad}{_format_value(v, indent, sort_keys, _depth + 1)}" for v in value
        )
        closing_pad = " " * (indent * _depth) if _depth > 0 else ""
        return f"[\n{inner}\n{closing_pad}]"
    return json.dumps(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="json_pretty",
        description="Pretty-print JSON from a file or stdin.",
    )
    parser.add_argument("path", nargs="?", default=None, help="JSON file (default: stdin)")
    parser.add_argument("--indent", type=int, default=2, help="Indent width (default 2)")
    parser.add_argument("--sort-keys", action="store_true", help="Sort object keys alphabetically")
    args = parser.parse_args(argv)

    if args.path is None or args.path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(args.path).read_text(encoding="utf-8")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON: {e}", file=sys.stderr)
        return 1

    if args.indent == 0:
        # Compact: use json.dumps with sort_keys.
        print(json.dumps(data, sort_keys=args.sort_keys, separators=(",", ":")), end="")
    else:
        print(_format_value(data, args.indent, args.sort_keys))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
