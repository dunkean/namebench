"""Import GeoNames place data from allCountries.zip."""

from __future__ import annotations

import zipfile
from pathlib import Path

from namegen.db import NameDB

# GeoNames TSV columns (allCountries.txt)
# 0: geonameid, 1: name, 2: asciiname, 3: alternatenames,
# 4: latitude, 5: longitude, 6: feature_class, 7: feature_code,
# 8: country_code, 9: cc2, 10-13: admin codes,
# 14: population, 15: elevation, 16: dem, 17: timezone, 18: modification_date

# Feature classes to import:
# P = populated places, T = mountains/hills, H = water bodies, A = administrative
FEATURE_CLASSES = {"P", "T", "H", "A"}

BATCH_SIZE = 50_000


def import_geonames(db: NameDB, data_dir: Path):
    """Import place names from allCountries.zip."""
    zip_path = data_dir / "allCountries.zip"
    if not zip_path.exists():
        print(f"[geonames] SKIP: {zip_path} not found")
        return

    print(f"[geonames] Streaming {zip_path.name} (this will take several minutes)...")

    batch: list[tuple] = []
    imported = 0
    skipped = 0

    with zipfile.ZipFile(zip_path) as zf:
        with zf.open("allCountries.txt") as f:
            for line_num, raw_line in enumerate(f, 1):
                try:
                    line = raw_line.decode("utf-8")
                except UnicodeDecodeError:
                    skipped += 1
                    continue

                parts = line.rstrip("\n").split("\t")
                if len(parts) < 19:
                    skipped += 1
                    continue

                feature_class = parts[6]
                if feature_class not in FEATURE_CLASSES:
                    skipped += 1
                    continue

                geoname_id = int(parts[0])
                name = parts[1].strip()
                country_iso = parts[8].strip()
                feature_code = parts[7]

                try:
                    population = int(parts[14]) if parts[14] else 0
                except ValueError:
                    population = 0

                if not name or not country_iso:
                    skipped += 1
                    continue

                batch.append((
                    geoname_id,
                    name,
                    country_iso,
                    feature_class,
                    feature_code,
                    population,
                ))

                if len(batch) >= BATCH_SIZE:
                    db.conn.executemany(
                        "INSERT OR IGNORE INTO places "
                        "(geoname_id, name, country_iso, feature_class, feature_code, population) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        batch,
                    )
                    imported += len(batch)
                    batch.clear()

                if line_num % 2_000_000 == 0:
                    db.conn.commit()
                    print(f"  ... {line_num:,} lines, {imported:,} places imported")

    # Flush remaining
    if batch:
        db.conn.executemany(
            "INSERT OR IGNORE INTO places "
            "(geoname_id, name, country_iso, feature_class, feature_code, population) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            batch,
        )
        imported += len(batch)

    db.conn.commit()
    print(f"[geonames] Imported {imported:,} places ({skipped:,} skipped)")
