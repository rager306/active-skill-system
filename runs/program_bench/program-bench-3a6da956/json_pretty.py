#!/usr/bin/env python3
"""json_pretty: pretty-print JSON from a file or stdin."""

import argparse
import json
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="json_pretty",
        description="Pretty-print JSON read from a file or stdin.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to a JSON file. If omitted, read from stdin.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indent width (default: 2). Use 0 for compact, whitespace-free output.",
    )
    parser.add_argument(
        "--sort-keys",
        action="store_true",
        help="Sort the keys of objects alphabetically.",
    )
    return parser


def read_input(path):
    if path is None:
        return sys.stdin.read()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        print(f"json_pretty: cannot read {path!r}: {exc}", file=sys.stderr)
        sys.exit(1)


def format_json(data, indent, sort_keys):
    if indent < 0:
        print("json_pretty: --indent must be >= 0", file=sys.stderr)
        sys.exit(1)
    if indent == 0:
        # Compact output: no whitespace at all between tokens.
        return json.dumps(data, separators=(",", ":"), sort_keys=sort_keys)
    return json.dumps(data, indent=indent, sort_keys=sort_keys)


def main(argv=None):
    args = build_parser().parse_args(argv)
    raw = read_input(args.path)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"json_pretty: invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})", file=sys.stderr)
        sys.exit(1)
    sys.stdout.write(format_json(obj, args.indent, args.sort_keys))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()