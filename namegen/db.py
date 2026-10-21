"""SQLite schema and NameDB access layer."""

from __future__ import annotations

import os
import json
import random
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "names.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS names (
    name       TEXT    NOT NULL,
    name_type  TEXT    NOT NULL,  -- 'forename' or 'surname'
    country_iso TEXT   NOT NULL,  -- ISO 3166-1 alpha-2
    gender     TEXT,              -- 'M', 'F', or NULL
    rank       INTEGER,          -- popularity rank (lower = more popular)
    source     TEXT    NOT NULL   -- 'forebears', 'philipperemy'
);

CREATE TABLE IF NOT EXISTS places (
    geoname_id    INTEGER PRIMARY KEY,
    name          TEXT    NOT NULL,
    country_iso   TEXT    NOT NULL,
    feature_class TEXT,           -- P, T, H, A, etc.
    feature_code  TEXT,
    population    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fantasy_arrays (
    style_key  TEXT NOT NULL,     -- e.g. 'fantasy.elfs'
    array_name TEXT NOT NULL,     -- e.g. 'nm1', 'nm2'
    values_json TEXT NOT NULL     -- JSON array of strings
);

CREATE TABLE IF NOT EXISTS fantasy_meta (
    style_key  TEXT PRIMARY KEY,
    pattern    TEXT NOT NULL,     -- generation pattern as JSON
    category   TEXT,
    label      TEXT
);

CREATE TABLE IF NOT EXISTS curated_lists (
    list_id TEXT NOT NULL,        -- e.g. 'demons', 'angels'
    name    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_names_country_type
    ON names(country_iso, name_type);
CREATE INDEX IF NOT EXISTS idx_names_country_type_gender
    ON names(country_iso, name_type, gender);
CREATE INDEX IF NOT EXISTS idx_places_country_class
    ON places(country_iso, feature_class);
CREATE INDEX IF NOT EXISTS idx_fantasy_arrays_key
    ON fantasy_arrays(style_key);
CREATE INDEX IF NOT EXISTS idx_curated_list_id
    ON curated_lists(list_id);
"""


class NameDB:
    """Unified access to all name data stored in SQLite."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path or os.environ.get("NOMNOM_DB_PATH") or DB_PATH).expanduser().resolve()
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def init_schema(self):
        """Create tables and indexes."""
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Name queries ──────────────────────────────────────────────

    def random_names(
        self,
        country_codes: list[str],
        name_type: str,
        count: int,
        gender: Optional[str] = None,
        min_length: int = 3,
    ) -> list[str]:
        """Pick random names from DB for given countries and type.

        Prefers names that have a popularity rank (from philipperemy) since
        ranked names are culturally representative of their country. Falls
        back to unranked names (forebears) only when the ranked pool is
        too small for the requested count.

        Args:
            min_length: Minimum name length filter. Set to 1 for CJK styles
                where short names (1-2 chars) are valid.
        """
        placeholders = ",".join("?" for _ in country_codes)
        params: list = list(country_codes)

        where = f"country_iso IN ({placeholders}) AND name_type = ?"
        params.append(name_type)

        if gender:
            where += " AND gender = ?"
            params.append(gender)

        # First: pick from ranked names only (higher cultural accuracy)
        len_filter = " AND length(name) >= 3" if min_length >= 3 else ""
        sql = f"SELECT DISTINCT name FROM names WHERE {where} AND rank IS NOT NULL{len_filter} ORDER BY RANDOM() LIMIT ?"
        rows = self.conn.execute(sql, params + [count]).fetchall()

        if len(rows) < count:
            # Not enough ranked names — fill remainder from unranked pool
            got = {r["name"] for r in rows}
            sql2 = f"SELECT DISTINCT name FROM names WHERE {where} AND rank IS NULL{len_filter} ORDER BY RANDOM() LIMIT ?"
            extra = self.conn.execute(sql2, params + [count - len(rows)]).fetchall()
            rows.extend(r for r in extra if r["name"] not in got)

        return [r["name"] for r in rows]

    def all_names_for_training(
        self,
        country_codes: list[str],
        name_type: str,
        gender: Optional[str] = None,
        limit: int = 10000,
    ) -> list[str]:
        """Get names for Markov training."""
        placeholders = ",".join("?" for _ in country_codes)
        params: list = list(country_codes)

        where = f"country_iso IN ({placeholders}) AND name_type = ?"
        params.append(name_type)

        if gender:
            where += " AND gender = ?"
            params.append(gender)

        sql = f"SELECT DISTINCT name FROM names WHERE {where} ORDER BY rank ASC NULLS LAST LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        return [r["name"] for r in rows]

    # ── Place queries ─────────────────────────────────────────────

    def random_places(
        self,
        country_codes: list[str],
        count: int,
        feature_class: Optional[str] = "P",
    ) -> list[str]:
        """Pick random place names."""
        placeholders = ",".join("?" for _ in country_codes)
        params: list = list(country_codes)

        where = f"country_iso IN ({placeholders})"
        if feature_class:
            where += " AND feature_class = ?"
            params.append(feature_class)

        sql = f"SELECT name FROM places WHERE {where} ORDER BY RANDOM() LIMIT ?"
        params.append(count)

        rows = self.conn.execute(sql, params).fetchall()
        return [r["name"] for r in rows]

    # ── Fantasy queries ───────────────────────────────────────────

    def get_fantasy_arrays(self, style_key: str) -> dict[str, list[str]]:
        """Load all arrays for a fantasy generator style."""
        rows = self.conn.execute(
            "SELECT array_name, values_json FROM fantasy_arrays WHERE style_key = ?",
            (style_key,),
        ).fetchall()
        return {r["array_name"]: json.loads(r["values_json"]) for r in rows}

    def get_fantasy_meta(self, style_key: str) -> Optional[dict]:
        """Load generation pattern metadata for a fantasy style."""
        row = self.conn.execute(
            "SELECT pattern, category, label FROM fantasy_meta WHERE style_key = ?",
            (style_key,),
        ).fetchone()
        if row:
            return {
                "pattern": json.loads(row["pattern"]),
                "category": row["category"],
                "label": row["label"],
            }
        return None

    def list_fantasy_styles(self) -> list[str]:
        """List all available fantasy style keys."""
        rows = self.conn.execute(
            "SELECT DISTINCT style_key FROM fantasy_meta ORDER BY style_key"
        ).fetchall()
        return [r["style_key"] for r in rows]

    def list_fantasy_styles_by_category(self, category: str) -> list[str]:
        """List fantasy style keys for a given category."""
        rows = self.conn.execute(
            "SELECT style_key FROM fantasy_meta WHERE category = ? ORDER BY style_key",
            (category,),
        ).fetchall()
        return [r["style_key"] for r in rows]

    # ── Curated queries ───────────────────────────────────────────

    def get_curated_list(self, list_id: str) -> list[str]:
        """Get all names in a curated list."""
        rows = self.conn.execute(
            "SELECT name FROM curated_lists WHERE list_id = ?",
            (list_id,),
        ).fetchall()
        return [r["name"] for r in rows]

    def list_curated_ids(self) -> list[str]:
        """List all curated list IDs."""
        rows = self.conn.execute(
            "SELECT DISTINCT list_id FROM curated_lists ORDER BY list_id"
        ).fetchall()
        return [r["list_id"] for r in rows]

    # ── Bulk pool loading ─────────────────────────────────────────

    def enable_bulk_pragmas(self):
        """Tune SQLite for bulk reads: larger cache, mmap, in-memory temp."""
        self.conn.execute("PRAGMA cache_size = -65536")   # 64 MB
        self.conn.execute("PRAGMA mmap_size = 536870912")  # 512 MB
        self.conn.execute("PRAGMA temp_store = MEMORY")

    def all_names_pool(
        self,
        country_codes: list[str],
        name_type: str,
        gender: Optional[str] = None,
        min_length: int = 3,
    ) -> list[str]:
        """Load full distinct name pool for Python-side sampling (no ORDER BY RANDOM)."""
        placeholders = ",".join("?" for _ in country_codes)
        params: list = list(country_codes)

        where = f"country_iso IN ({placeholders}) AND name_type = ?"
        params.append(name_type)

        if gender:
            where += " AND gender = ?"
            params.append(gender)

        len_filter = " AND length(name) >= 3" if min_length >= 3 else ""
        sql = f"SELECT DISTINCT name FROM names WHERE {where}{len_filter}"
        rows = self.conn.execute(sql, params).fetchall()
        return [r["name"] for r in rows]

    def all_places_pool(
        self,
        country_codes: list[str],
        feature_class: Optional[str] = "P",
    ) -> list[str]:
        """Load full place name pool for Python-side sampling."""
        placeholders = ",".join("?" for _ in country_codes)
        params: list = list(country_codes)

        where = f"country_iso IN ({placeholders})"
        if feature_class:
            where += " AND feature_class = ?"
            params.append(feature_class)

        sql = f"SELECT name FROM places WHERE {where}"
        rows = self.conn.execute(sql, params).fetchall()
        return [r["name"] for r in rows]

    # ── Stats ─────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return row counts for each table."""
        tables = ["names", "places", "fantasy_arrays", "fantasy_meta", "curated_lists"]
        result = {}
        for t in tables:
            try:
                row = self.conn.execute(f"SELECT COUNT(*) as c FROM {t}").fetchone()
                result[t] = row["c"]
            except sqlite3.OperationalError:
                result[t] = 0
        return result
