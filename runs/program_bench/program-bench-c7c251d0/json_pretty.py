#!/usr/bin/env python3
"""json_pretty - pretty-print JSON from a file or stdin."""
import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(
        prog='json_pretty',
        description='Pretty-print JSON from a file or stdin.'
    )
    parser.add_argument(
        'file',
        nargs='?',
        help='Path to JSON file (default: read from stdin).'
    )
    parser.add_argument(
        '--indent',
        type=int,
        default=2,
        help='Indent width (default: 2, use 0 for compact output).'
    )
    parser.add_argument(
        '--sort-keys',
        action='store_true',
        help='Sort object keys alphabetically (off by default).'
    )
    args = parser.parse_args()

    try:
        if args.file:
            with open(args.file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = json.load(sys.stdin)
    except FileNotFoundError as e:
        print(f"json_pretty: error: file not found: {e.filename}", file=sys.stderr)
        sys.exit(1)
    except IsADirectoryError as e:
        print(f"json_pretty: error: is a directory: {e.filename}", file=sys.stderr)
        sys.exit(1)
    except PermissionError as e:
        print(f"json_pretty: error: permission denied: {e.filename}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"json_pretty: error: invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"json_pretty: error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.indent == 0:
        output = json.dumps(data, separators=(',', ':'), sort_keys=args.sort_keys)
    else:
        output = json.dumps(data, indent=args.indent, sort_keys=args.sort_keys)

    print(output)


if __name__ == '__main__':
    main()