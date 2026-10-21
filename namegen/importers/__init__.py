"""Data importers for building the SQLite name database."""

from namegen.importers.import_forebears import import_forebears
from namegen.importers.import_philipperemy import import_philipperemy
from namegen.importers.import_geonames import import_geonames
from namegen.importers.import_fantasy import import_fantasy
from namegen.importers.import_curated import import_curated


def build_all(db_path=None, data_dir=None):
    """Run all importers to build the complete database."""
    from pathlib import Path
    import os
    from namegen.db import NameDB, DB_PATH

    db_path = Path(db_path or os.environ.get("NAMEBENCH_DB_PATH") or DB_PATH).expanduser().resolve()
    if db_path.exists():
        raise FileExistsError(
            f"Refusing to rebuild an existing database: {db_path}. "
            "Set NAMEBENCH_DB_PATH to a new file."
        )
    data_dir = Path(data_dir) if data_dir else db_path.parent.parent

    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = NameDB(db_path)
    db.init_schema()

    print("=== Building name database ===")
    print(f"DB: {db_path}")
    print(f"Data dir: {data_dir}")
    print()

    import_curated(db, data_dir)
    import_fantasy(db, data_dir)
    import_forebears(db, data_dir)
    import_philipperemy(db, data_dir)
    import_geonames(db, data_dir)

    print()
    print("=== Database stats ===")
    for table, count in db.stats().items():
        print(f"  {table}: {count:,} rows")

    db.close()
    print("\nDone!")
