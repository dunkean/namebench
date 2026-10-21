#!/usr/bin/env python3
"""RPG Name Generator — CLI entry point.

Usage:
    python namegen.py <style> <type> <count> [--gender M/F] [--json]
    python namegen.py --build      # Build the SQLite database from data sources
    python namegen.py --list       # List available styles
    python namegen.py --stats      # Show database statistics
"""

from __future__ import annotations

import argparse
import io
import json
import sys


def cmd_build(args):
    """Build the database from all data sources."""
    from namegen.importers import build_all
    try:
        build_all()
    except OSError as exc:
        raise SystemExit(str(exc)) from exc


def cmd_list(args):
    """List all available styles."""
    from namegen.api import list_styles

    styles = list_styles()
    for category, names in sorted(styles.items()):
        # For fantasy sub-categories, show full key (category.name) as usage hint
        if category.startswith("fantasy/"):
            cat_prefix = category.split("/", 1)[1]
            display = [f"{cat_prefix}.{n}" for n in names]
        else:
            display = list(names)

        print(f"\n[{category}] ({len(display)} styles)")
        col_width = max(len(n) for n in display) + 2
        cols = max(1, 80 // col_width)
        for i in range(0, len(display), cols):
            row = display[i : i + cols]
            print("  " + "".join(n.ljust(col_width) for n in row))


def cmd_stats(args):
    """Show database statistics."""
    from namegen.db import NameDB

    db = NameDB()
    if not db.db_path.is_file():
        raise SystemExit("Database missing. Start with `nomnom demo`.")
    stats = db.stats()
    print("Database statistics:")
    for table, count in stats.items():
        print(f"  {table}: {count:,} rows")
    db.close()


def cmd_generate(args):
    """Generate names."""
    use_bulk = args.bulk or args.count >= 1000

    if use_bulk:
        from namegen.api import generate_bulk

        try:
            gen = generate_bulk(
                style=args.style,
                name_type=args.type,
                count=args.count,
                gender=args.gender,
                romanize=args.romanize,
                unique=args.unique,
            )
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(list(gen), ensure_ascii=False, indent=2))
        else:
            for name in gen:
                print(name)
    else:
        from namegen.api import generate

        try:
            names = generate(
                style=args.style,
                name_type=args.type,
                count=args.count,
                gender=args.gender,
                romanize=args.romanize,
            )
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(names, ensure_ascii=False, indent=2))
        else:
            for name in names:
                print(name)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        from namegen.demo import main as demo_main
        demo_main(sys.argv[2:])
        return
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="RPG Name Generator — World-Building Onomastics Engine",
    )

    # Mode flags
    parser.add_argument("--build", action="store_true", help="Build the SQLite database")
    parser.add_argument("--list", action="store_true", help="List available styles")
    parser.add_argument("--stats", action="store_true", help="Show database stats")

    # Generation args
    parser.add_argument("style", nargs="?", help="Style name (e.g. elf, french, demons)")
    parser.add_argument("type", nargs="?", default="forename",
                        choices=["forename", "surname", "fullname", "place"],
                        help="Name type (default: forename)")
    parser.add_argument("count", nargs="?", type=int, default=1,
                        help="Number of names (default: 1)")
    parser.add_argument("--gender", "-g", choices=["M", "F"],
                        help="Gender filter")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output as JSON array")
    parser.add_argument("--romanize", "-r", action="store_true",
                        help="Transliterate non-Latin characters to ASCII")
    parser.add_argument("--bulk", "-b", action="store_true",
                        help="Force bulk streaming mode (auto-enabled for count >= 1000)")
    parser.add_argument("--unique", "-u", action="store_true",
                        help="No duplicate names (capped at pool size)")

    args = parser.parse_args()

    if args.build:
        cmd_build(args)
    elif args.list:
        cmd_list(args)
    elif args.stats:
        cmd_stats(args)
    elif args.style:
        cmd_generate(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
