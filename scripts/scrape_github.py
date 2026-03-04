#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Download and extract GitHub repositories containing name datasets / generators.
No parsing, no schema, no normalization.

Usage:
    python download_name_sources.py
    python download_name_sources.py --outdir ./sources
    python download_name_sources.py --keep-zips
    python download_name_sources.py --clean
    python download_name_sources.py --repos philipperemy/name-dataset sigpwned/popular-names-by-country-dataset

Dependency:
    pip install requests
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Iterable, List, Optional

import requests


DEFAULT_REPOS = [
    "philipperemy/name-dataset",
    "sigpwned/popular-names-by-country-dataset",
    "alxgiraud/fantasygen",
    "cyberfilth/GUI-Fantasy-Name-Generator",
    "drunkfailure/dnd-name-gen",
    "Snake4life/fantasy-names",
    "bvezilic/DnD-name-generator",
]

BRANCH_CANDIDATES = ["main", "master"]


def log(*args) -> None:
    print(*args, file=sys.stderr)


def slugify_repo(repo: str) -> str:
    return repo.replace("/", "__")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download and extract GitHub repos as zip archives.")
    p.add_argument(
        "--outdir",
        default="./name_sources",
        help="Destination directory for extracted repositories",
    )
    p.add_argument(
        "--repos",
        nargs="*",
        default=None,
        help="Optional custom list of repos in owner/name format",
    )
    p.add_argument(
        "--keep-zips",
        action="store_true",
        help="Keep downloaded zip files in <outdir>/_zips",
    )
    p.add_argument(
        "--clean",
        action="store_true",
        help="Delete output directory before downloading",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="HTTP timeout in seconds",
    )
    return p.parse_args()


def candidate_zip_urls(repo: str) -> Iterable[tuple[str, str]]:
    owner, name = repo.split("/", 1)
    for branch in BRANCH_CANDIDATES:
        yield branch, f"https://github.com/{owner}/{name}/archive/refs/heads/{branch}.zip"


def download_repo_zip(session: requests.Session, repo: str, zips_dir: Path, timeout: int) -> Optional[Path]:
    zip_path = zips_dir / f"{slugify_repo(repo)}.zip"

    for branch, url in candidate_zip_urls(repo):
        log(f"[INFO] Trying {repo} ({branch})")
        try:
            with session.get(url, stream=True, timeout=timeout) as r:
                if r.status_code != 200:
                    continue
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 64):
                        if chunk:
                            f.write(chunk)
                log(f"[OK] Downloaded {repo} from {branch}")
                return zip_path
        except requests.RequestException as e:
            log(f"[WARN] {repo} ({branch}) -> {e}")

    return None


def extract_zip(zip_path: Path, extract_parent: Path, repo: str) -> Optional[Path]:
    target_dir = extract_parent / slugify_repo(repo)

    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target_dir)
    except zipfile.BadZipFile:
        log(f"[ERROR] Invalid zip: {zip_path}")
        return None

    # Flatten GitHub's single top-level folder when present
    children = [p for p in target_dir.iterdir()]
    if len(children) == 1 and children[0].is_dir():
        inner = children[0]
        for child in inner.iterdir():
            shutil.move(str(child), str(target_dir / child.name))
        inner.rmdir()

    return target_dir


def main() -> int:
    args = parse_args()

    outdir = Path(args.outdir).resolve()
    zips_dir = outdir / "_zips"
    repos = args.repos if args.repos else DEFAULT_REPOS

    if args.clean and outdir.exists():
        shutil.rmtree(outdir)

    outdir.mkdir(parents=True, exist_ok=True)
    zips_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": "download-name-sources/1.0"})

    success = 0
    failed: List[str] = []

    for repo in repos:
        if "/" not in repo:
            log(f"[WARN] Skipping invalid repo format: {repo}")
            failed.append(repo)
            continue

        zip_path = download_repo_zip(session, repo, zips_dir, args.timeout)
        if zip_path is None:
            log(f"[ERROR] Could not download {repo}")
            failed.append(repo)
            continue

        extracted = extract_zip(zip_path, outdir, repo)
        if extracted is None:
            failed.append(repo)
            continue

        if not args.keep_zips:
            try:
                zip_path.unlink()
            except OSError:
                pass

        success += 1
        log(f"[OK] Extracted to {extracted}")

    if not args.keep_zips:
        try:
            if zips_dir.exists() and not any(zips_dir.iterdir()):
                zips_dir.rmdir()
        except OSError:
            pass

    log("\nDone.")
    log(f"Successful: {success}")
    log(f"Failed: {len(failed)}")
    if failed:
        for repo in failed:
            log(f"  - {repo}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())