"""Import curated name lists from defaultDictionaries.json."""

from __future__ import annotations

import json
from pathlib import Path

from namegen.db import NameDB


def import_curated(db: NameDB, data_dir: Path):
    """Import curated mythological/historical name lists."""
    path = data_dir / "defaultDictionaries.json"
    if not path.exists():
        print(f"[curated] SKIP: {path} not found")
        return

    print(f"[curated] Loading {path.name}...")

    with open(path, "r", encoding="utf-8") as f:
        lists = json.load(f)

    # Clear existing curated data
    db.conn.execute("DELETE FROM curated_lists")

    total = 0
    for entry in lists:
        list_id = entry["_id"]
        values = entry.get("values", [])
        rows = [(list_id, name) for name in values]
        db.conn.executemany(
            "INSERT INTO curated_lists (list_id, name) VALUES (?, ?)",
            rows,
        )
        total += len(values)
        print(f"  {list_id}: {len(values)} names")

    db.conn.commit()
    print(f"[curated] Imported {total:,} names across {len(lists)} lists")
