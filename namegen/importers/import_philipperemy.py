"""Import philipperemy name-dataset from pickle files."""

from __future__ import annotations

import gzip
import pickle
from pathlib import Path

from namegen.db import NameDB

BATCH_SIZE = 10_000


def _load_pickle(path: Path) -> dict:
    """Load a gzipped pickle file."""
    with gzip.open(path, "rb") as f:
        return pickle.load(f)


def _determine_gender(gender_probs: dict) -> str | None:
    """Determine gender from probability dict. Returns 'M', 'F', or None."""
    m = gender_probs.get("M", 0)
    f = gender_probs.get("F", 0)
    if m > 0.8:
        return "M"
    elif f > 0.8:
        return "F"
    return None


def _load_forebears_country_map(db: NameDB, name_type: str) -> dict[str, str]:
    """Load {name → country_iso} from forebears data already in DB.

    Forebears orders countries by incidence rate (per-capita frequency),
    which is the best proxy for cultural origin. We use this as ground
    truth when philipperemy disagrees (philipperemy uses raw bearer
    proportion, which is skewed by diaspora).
    """
    rows = db.conn.execute(
        "SELECT name, country_iso FROM names "
        "WHERE name_type = ? AND source = 'forebears'",
        (name_type,),
    ).fetchall()
    # If duplicates exist, first row wins (already correct from forebears)
    result: dict[str, str] = {}
    for r in rows:
        n = r["name"]
        if n not in result:
            result[n] = r["country_iso"]
    return result


def _import_names(
    db: NameDB, data: dict, name_type: str, label: str
):
    """Import a philipperemy name dict into the DB.

    Cross-references forebears data to use incidence-based country
    assignment instead of philipperemy's residency-based probability.
    """
    # Load forebears country assignments for cross-reference
    print(f"  Loading forebears country map for {label}...")
    forebears_country = _load_forebears_country_map(db, name_type)
    print(f"  {len(forebears_country):,} forebears entries loaded for cross-reference")

    batch: list[tuple] = []
    imported = 0
    corrected = 0

    for name, meta in data.items():
        if not name or not name.strip():
            continue

        name = name.strip()
        gender = _determine_gender(meta.get("gender", {}))
        ranks = meta.get("rank", {})
        countries = meta.get("country", {})

        if not countries:
            continue

        # Prefer forebears' incidence-based country over philipperemy's
        # residency-based probability (avoids diaspora misattribution)
        if name in forebears_country:
            iso = forebears_country[name]
            phil_top = max(countries, key=countries.get)
            if phil_top != iso:
                corrected += 1
        else:
            # Name only in philipperemy — use highest probability
            iso = max(countries, key=countries.get)

        rank = ranks.get(iso)
        batch.append((name, name_type, iso, gender, rank, "philipperemy"))

        if len(batch) >= BATCH_SIZE:
            db.conn.executemany(
                "INSERT INTO names (name, name_type, country_iso, gender, rank, source) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                batch,
            )
            imported += len(batch)
            batch.clear()

    if batch:
        db.conn.executemany(
            "INSERT INTO names (name, name_type, country_iso, gender, rank, source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            batch,
        )
        imported += len(batch)

    db.conn.commit()
    print(f"  {label}: {imported:,} rows ({corrected:,} country-corrected via forebears)")
    return imported


def import_philipperemy(db: NameDB, data_dir: Path):
    """Import philipperemy name-dataset pickle files."""
    v3_dir = data_dir / "philipperemy__name-dataset" / "names_dataset" / "v3"

    first_path = v3_dir / "first_names.pkl.gz"
    last_path = v3_dir / "last_names.pkl.gz"

    if not first_path.exists() and not last_path.exists():
        print(f"[philipperemy] SKIP: pickle files not found in {v3_dir}")
        return

    print("[philipperemy] Loading pickle files...")

    total = 0

    if first_path.exists():
        print(f"  Loading {first_path.name}...")
        first_names = _load_pickle(first_path)
        print(f"  {len(first_names):,} first names loaded")
        total += _import_names(db, first_names, "forename", "forenames")
        del first_names  # Free memory

    if last_path.exists():
        print(f"  Loading {last_path.name}...")
        last_names = _load_pickle(last_path)
        print(f"  {len(last_names):,} last names loaded")
        total += _import_names(db, last_names, "surname", "surnames")
        del last_names

    print(f"[philipperemy] Imported {total:,} total rows")
