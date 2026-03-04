"""Import forebears name data from checkpoint JSONL."""

from __future__ import annotations

import json
from pathlib import Path

from namegen.db import NameDB
from namegen.country_map import name_to_iso

# Batch size for inserts
BATCH_SIZE = 10_000


def import_forebears(db: NameDB, data_dir: Path):
    """Import names from forebears_checkpoint/results.jsonl."""
    jsonl_path = data_dir / "forebears_checkpoint" / "results.jsonl"
    if not jsonl_path.exists():
        print(f"[forebears] SKIP: {jsonl_path} not found")
        return

    print(f"[forebears] Loading {jsonl_path.name} (this may take a few minutes)...")

    # Track unmapped countries
    unmapped: dict[str, int] = {}
    imported = 0
    skipped = 0
    batch: list[tuple] = []

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue

            name = entry.get("name", "").strip()
            name_type = entry.get("type", "")
            countries = entry.get("countries", [])
            alt_forms = entry.get("alt_forms", [])

            if not name or name_type not in ("surname", "forename"):
                skipped += 1
                continue

            # Map to top-1 country only (first with a valid ISO code)
            iso = None
            for country_name in countries:
                iso = name_to_iso(country_name)
                if iso is not None:
                    break
                unmapped[country_name] = unmapped.get(country_name, 0) + 1

            if iso:
                batch.append((name, name_type, iso, None, None, "forebears"))

                # Also import alt_forms under the same country
                for alt in alt_forms:
                    alt_name = alt if isinstance(alt, str) else alt.get("name", "")
                    if alt_name:
                        batch.append((alt_name, name_type, iso, None, None, "forebears"))

            # Flush batch
            if len(batch) >= BATCH_SIZE:
                db.conn.executemany(
                    "INSERT INTO names (name, name_type, country_iso, gender, rank, source) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    batch,
                )
                imported += len(batch)
                batch.clear()

            if line_num % 200_000 == 0:
                db.conn.commit()
                print(f"  ... {line_num:,} lines processed, {imported:,} rows inserted")

    # Flush remaining
    if batch:
        db.conn.executemany(
            "INSERT INTO names (name, name_type, country_iso, gender, rank, source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            batch,
        )
        imported += len(batch)

    db.conn.commit()
    print(f"[forebears] Imported {imported:,} name-country rows ({skipped:,} skipped)")

    if unmapped:
        top_unmapped = sorted(unmapped.items(), key=lambda x: -x[1])[:10]
        print(f"  Unmapped countries (top 10): {top_unmapped}")
