#!/usr/bin/env python3
"""json_pretty: Pretty-print JSON from a file or standard input."""
import argparse
import json
import sys

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pretty-print JSON with configurable indentation and key sorting."
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Path to a JSON file. If omitted, read from standard input."
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indent width for pretty printing (default: 2). Use 0 for compact output."
    )
    parser.add_argument(
        "--sort-keys",
        action="store_true",
        help="Sort object keys alphabetically."
    )
    args = parser.parse_args()

    # Read input data
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                data = f.read()
        except OSError as e:
            print(f"Error reading file '{args.file}': {e}", file=sys.stderr)
            sys.exit(1)
    else:
        data = sys.stdin.read()

    # Parse JSON
    try:
        obj = json.loads(data)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine formatting options
    if args.indent == 0:
        # Compact output: no whitespace
        indent = None
        separators = (",", ":")
    else:
        indent = args.indent
        separators = None  # Use default separators for pretty printing

    # Serialize JSON
    try:
        output = json.dumps(obj, indent=indent, sort_keys=args.sort_keys, separators=separators)
    except (TypeError, ValueError) as e:
        print(f"Error serializing JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Write to stdout
    sys.stdout.write(output)
    if not output.endswith("\n"):
        sys.stdout.write("\n")
    sys.exit(0)

if __name__ == "__main__":
    main()