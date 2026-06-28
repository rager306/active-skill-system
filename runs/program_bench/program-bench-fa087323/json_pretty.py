#!/usr/bin/env python3
"""json_pretty: Pretty-print JSON from a file or stdin."""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(
        prog='json_pretty',
        description='Pretty-print JSON from a file or stdin.',
    )
    parser.add_argument(
        'file',
        nargs='?',
        help='Path to a JSON file. If omitted, read from stdin.',
    )
    parser.add_argument(
        '--indent',
        type=int,
        default=2,
        metavar='N',
        help='Indent width (default: 2). Use 0 for compact output.',
    )
    parser.add_argument(
        '--sort-keys',
        action='store_true',
        help='Sort object keys alphabetically.',
    )

    args = parser.parse_args()

    if args.indent < 0:
        parser.error('--indent must be >= 0')

    try:
        if args.file:
            with open(args.file, 'r', encoding='utf-8') as f:
                data = f.read()
        else:
            data = sys.stdin.read()
    except OSError as e:
        print(f'json_pretty: cannot read input: {e}', file=sys.stderr)
        sys.exit(1)

    try:
        obj = json.loads(data)
    except json.JSONDecodeError as e:
        print(f'json_pretty: invalid JSON: {e}', file=sys.stderr)
        sys.exit(1)

    indent = args.indent if args.indent > 0 else None
    output = json.dumps(
        obj,
        indent=indent,
        sort_keys=args.sort_keys,
        ensure_ascii=False,
    )
    sys.stdout.write(output)
    if not output.endswith('\n'):
        sys.stdout.write('\n')


if __name__ == '__main__':
    main()