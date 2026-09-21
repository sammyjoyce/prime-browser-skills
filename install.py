#!/usr/bin/env python3
"""Install the skills in this repository into a Prime Agent skills directory.

Standard library only. Copies by default, or links with --link. Nothing is
installed until you drop --dry-run.

    python3 install.py --dry-run
    python3 install.py --only browser-use jev
    python3 install.py --dest /tmp/skills --link

The destination may not be the repository `skills/` directory or anything inside
it, because that would overwrite or recurse into the source.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
SOURCE = REPO / "skills"
DEFAULT_DEST = Path.home() / ".prime" / "agent" / "skills"

# Local development state that must never reach an installed copy.
SKIP_DIRS = {
    "__pycache__", ".venv", "venv", "node_modules", "artifacts", "profiles",
    "sessions", "logs", "screenshots", ".git", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", ".tox", "dist", "build",
}
SKIP_FILES = {".DS_Store", ".bu-pi.lock"}
SKIP_SUFFIXES = (".pyc", ".pyo", ".log", ".egg-info")
KEEP_ENV_FILES = {".env.example"}


def skip_entries(_directory: str, entries: list[str]) -> set[str]:
    """shutil.copytree ignore callback. Keeps .env.example, drops other .env files."""
    dropped = set()
    for name in entries:
        if name in SKIP_DIRS or name in SKIP_FILES or name.endswith(SKIP_SUFFIXES):
            dropped.add(name)
        elif (name == ".env" or name.startswith(".env.")) and name not in KEEP_ENV_FILES:
            dropped.add(name)
    return dropped


def available() -> list[str]:
    return sorted(p.name for p in SOURCE.iterdir() if p.is_dir())


def dest_problem(dest_dir: Path) -> str | None:
    """Reject a destination that would damage or recurse into the source."""
    if dest_dir == SOURCE:
        return f"--dest may not be the repository source directory {SOURCE}"
    if dest_dir.is_relative_to(SOURCE):
        return f"--dest may not be inside the repository source directory {SOURCE}"
    if SOURCE.is_relative_to(dest_dir):
        return f"--dest {dest_dir} contains the repository source directory {SOURCE}"
    return None


def install_one(name: str, dest_dir: Path, link: bool, force: bool, dry_run: bool) -> str:
    source = SOURCE / name
    dest = dest_dir / name
    action = "link" if link else "copy"
    if dest == source or source.is_relative_to(dest) or dest.is_relative_to(source):
        return f"skip {name}: refusing a destination that overlaps its own source"
    if dest.exists() or dest.is_symlink():
        if not force:
            return f"skip {name}: {dest} exists, use --force to replace"
        if not dry_run:
            if dest.is_symlink() or dest.is_file():
                dest.unlink()
            else:
                shutil.rmtree(dest)
    if dry_run:
        return f"would {action} {name} -> {dest}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    if link:
        dest.symlink_to(source, target_is_directory=True)
    else:
        shutil.copytree(source, dest, ignore=skip_entries)
    return f"{'linked' if link else 'copied'} {name} -> {dest}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", default=str(DEFAULT_DEST), help=f"target directory, default {DEFAULT_DEST}")
    parser.add_argument("--only", nargs="+", metavar="SKILL", help="install these skills only")
    parser.add_argument("--link", action="store_true", help="symlink instead of copying")
    parser.add_argument("--force", action="store_true", help="replace an existing destination")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and change nothing")
    args = parser.parse_args(argv)

    if not SOURCE.is_dir():
        print(f"error: {SOURCE} not found", file=sys.stderr)
        return 2

    names = available()
    if args.only:
        unknown = [n for n in args.only if n not in names]
        if unknown:
            print(f"error: unknown skill(s): {', '.join(unknown)}", file=sys.stderr)
            print(f"available: {', '.join(names)}", file=sys.stderr)
            return 2
        names = list(args.only)

    dest_dir = Path(args.dest).expanduser().resolve()
    problem = dest_problem(dest_dir)
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    skipped = 0
    for name in names:
        message = install_one(name, dest_dir, args.link, args.force, args.dry_run)
        if message.startswith("skip "):
            skipped += 1
        print(message)

    if not args.dry_run:
        print("\nNext: restart the Prime Agent session or Python kernel.")
        print("Then run the per-skill setup in README.md before the first browser call.")
    return 1 if skipped else 0


if __name__ == "__main__":
    raise SystemExit(main())
