"""Command line entry point: ``envfile-diff`` or ``python -m envfile_diff``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import EnvParseError, diff_env, parse_env, render


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="envfile-diff",
        description="Diff two .env files by key. Values are masked unless asked for.",
    )
    parser.add_argument("old", type=Path, metavar="OLD")
    parser.add_argument("new", type=Path, metavar="NEW")
    parser.add_argument("--show-values", action="store_true", help="print the values too")
    parser.add_argument("--include-unchanged", action="store_true", help="also list equal keys")
    parser.add_argument("--json", action="store_true", help="print JSON")
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="exit 1 when the files differ, for use in CI",
    )
    args = parser.parse_args(argv)

    missing = [str(path) for path in (args.old, args.new) if not path.is_file()]
    if missing:
        print(f"no such file: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        old = parse_env(args.old.read_text(encoding="utf-8"))
        new = parse_env(args.new.read_text(encoding="utf-8"))
    except EnvParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    diff = diff_env(old, new)
    if args.json:
        payload = {
            "added": sorted(diff.added),
            "removed": sorted(diff.removed),
            "changed": sorted(diff.changed),
            "unchanged": sorted(diff.unchanged),
        }
        if args.show_values:
            payload = {
                "added": diff.added,
                "removed": diff.removed,
                "changed": {key: list(pair) for key, pair in diff.changed.items()},
                "unchanged": diff.unchanged,
            }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        text = render(
            diff,
            show_values=args.show_values,
            include_unchanged=args.include_unchanged,
        )
        if text:
            print(text)
        print(
            f"{len(diff.added)} added, {len(diff.removed)} removed, {len(diff.changed)} changed",
            file=sys.stderr,
        )
    if args.exit_code and not diff.is_empty:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
