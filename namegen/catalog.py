"""Catalog — loads catalog.json, populates dynamic entries, validates name_type."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from namegen.db import NameDB
from namegen.zones import OnomasticResolver

CATALOG_PATH = Path(__file__).resolve().parent / "catalog.json"


@dataclass
class CatalogEntry:
    id: str                 # e.g. "fantasy.elfs", "macro.arabic", "FR"
    label: str              # display label
    supported_types: list[str] = field(default_factory=list)
    count: int = 0          # number of names/places available


@dataclass
class CatalogGroup:
    id: str
    label: str
    abbreviation: str | None
    provider: str
    entries: list[CatalogEntry] = field(default_factory=list)


class Catalog:
    """Master catalog: loads JSON config, populates dynamic entries from DB."""

    def __init__(self, db: NameDB, zones: OnomasticResolver):
        self._db = db
        self._zones = zones

        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            self._raw = json.load(f)

        self._abbreviations: dict[str, str] = self._raw.get("abbreviations", {})
        self._exclude_categories: set[str] = set(self._raw.get("exclude_categories", []))

        # domain_id -> list[CatalogGroup]
        self._domains: dict[str, list[CatalogGroup]] = {}
        # domain labels
        self._domain_labels: dict[str, str] = {}
        # flat entry index: entry_id -> CatalogEntry
        self._entry_index: dict[str, CatalogEntry] = {}

        self._build()

    def _build(self):
        for domain_id, domain_cfg in self._raw.get("domains", {}).items():
            self._domain_labels[domain_id] = domain_cfg.get("label", domain_id)
            groups: list[CatalogGroup] = []

            for gcfg in domain_cfg.get("groups", []):
                group = CatalogGroup(
                    id=gcfg["id"],
                    label=gcfg.get("label", gcfg["id"]),
                    abbreviation=gcfg.get("abbreviation"),
                    provider=gcfg.get("provider", ""),
                )

                populate = gcfg.get("populate")
                category_filter = gcfg.get("category_filter")
                static_entries = gcfg.get("entries")

                if populate == "from_db_names":
                    group.entries = self._populate_country_entries(table="names")
                elif populate == "from_db_places":
                    group.entries = self._populate_country_entries(table="places")
                elif category_filter:
                    group.entries = self._populate_fantasy_entries(
                        category_filter, domain_id
                    )
                elif static_entries:
                    group.entries = self._build_static_entries(
                        static_entries, group.provider, domain_id
                    )

                # Index all entries (merge supported_types if ID already exists)
                for entry in group.entries:
                    existing = self._entry_index.get(entry.id)
                    if existing is not None:
                        merged = list(dict.fromkeys(
                            existing.supported_types + entry.supported_types
                        ))
                        existing.supported_types = merged
                    else:
                        self._entry_index[entry.id] = entry

                if group.entries:
                    groups.append(group)

            self._domains[domain_id] = groups

    # ── Populators ────────────────────────────────────────────────

    def _populate_country_entries(self, table: str) -> list[CatalogEntry]:
        """Build entries from distinct country codes in a DB table."""
        if table == "names":
            sql = "SELECT country_iso, COUNT(*) AS cnt FROM names GROUP BY country_iso ORDER BY country_iso"
            supported = ["forename", "surname", "fullname"]
        else:
            sql = "SELECT country_iso, COUNT(*) AS cnt FROM places GROUP BY country_iso ORDER BY country_iso"
            supported = ["place"]

        rows = self._db.conn.execute(sql).fetchall()
        entries: list[CatalogEntry] = []

        for row in rows:
            iso = row["country_iso"]
            label = self._country_label(iso)
            entries.append(CatalogEntry(
                id=iso, label=label, supported_types=supported, count=row["cnt"],
            ))

        entries.sort(key=lambda e: e.label)
        return entries

    @staticmethod
    def _country_label(iso: str) -> str:
        """ISO code to country name via pycountry."""
        try:
            import pycountry
            c = pycountry.countries.get(alpha_2=iso)
            if c:
                return c.name
        except Exception:
            pass
        return iso

    def _populate_fantasy_entries(
        self, category_filter: list[str], domain_id: str
    ) -> list[CatalogEntry]:
        """Build entries from fantasy_meta for given categories."""
        entries: list[CatalogEntry] = []
        is_place_domain = domain_id == "places"

        for cat in category_filter:
            if cat in self._exclude_categories:
                continue
            style_keys = self._db.list_fantasy_styles_by_category(cat)
            for sk in style_keys:
                if is_place_domain:
                    supported = ["place"]
                else:
                    supported = self._infer_fantasy_supported_types(sk)

                # Label: strip category prefix, humanize
                if "." in sk:
                    gen_name = sk.split(".", 1)[1]
                else:
                    gen_name = sk
                label = gen_name.replace("_", " ").title()

                entries.append(CatalogEntry(
                    id=sk, label=label, supported_types=supported
                ))

        entries.sort(key=lambda e: e.label)
        return entries

    def _infer_fantasy_supported_types(self, style_key: str) -> list[str]:
        """Determine supported types from the fantasy pattern."""
        meta = self._db.get_fantasy_meta(style_key)
        if not meta:
            return ["surname"]

        pattern = meta["pattern"]
        if self._is_forename_capable(pattern):
            return ["forename", "surname", "fullname"]
        return ["surname"]

    @staticmethod
    def _is_forename_capable(pattern: dict) -> bool:
        """Check if a fantasy pattern can produce forename + surname."""
        variants = pattern.get("variants", [])
        has_space = any(
            v.get("space") and v.get("space_pos", -1) > 0
            for v in variants
        )
        return has_space or pattern.get("has_type_param", False)

    def _build_static_entries(
        self, raw_entries: list[dict], provider: str, domain_id: str
    ) -> list[CatalogEntry]:
        """Build entries from static JSON entries list."""
        entries: list[CatalogEntry] = []
        is_place_domain = domain_id == "places"

        # Pre-fetch curated counts if needed
        curated_counts: dict[str, int] = {}
        if provider == "curated":
            curated_counts = self._curated_counts()

        # Pre-fetch onomastic counts if needed
        onomastic_counts: dict[str, int] = {}
        if provider in ("onomastic", "onomastic_place"):
            table = "places" if is_place_domain else "names"
            onomastic_counts = self._onomastic_counts(
                [e["id"] for e in raw_entries], table
            )

        for e in raw_entries:
            if is_place_domain:
                supported = ["place"]
            else:
                if provider == "curated":
                    supported = ["forename"]
                elif provider in ("onomastic", "onomastic_place"):
                    supported = ["forename", "surname", "fullname"]
                else:
                    supported = ["forename", "surname", "fullname"]

            count = curated_counts.get(e["id"], 0) or onomastic_counts.get(e["id"], 0)
            entries.append(CatalogEntry(
                id=e["id"], label=e["label"], supported_types=supported,
                count=count,
            ))

        return entries

    def _curated_counts(self) -> dict[str, int]:
        """Count entries per curated list_id."""
        rows = self._db.conn.execute(
            "SELECT list_id, COUNT(*) AS cnt FROM curated_lists GROUP BY list_id"
        ).fetchall()
        return {r["list_id"]: r["cnt"] for r in rows}

    def _onomastic_counts(self, entry_ids: list[str], table: str) -> dict[str, int]:
        """Count DB rows for onomastic zone entries by resolving to country codes."""
        result: dict[str, int] = {}
        for eid in entry_ids:
            codes = self._zones.resolve(eid)
            if not codes:
                continue
            placeholders = ",".join("?" for _ in codes)
            sql = f"SELECT COUNT(*) AS cnt FROM {table} WHERE country_iso IN ({placeholders})"
            row = self._db.conn.execute(sql, sorted(codes)).fetchone()
            result[eid] = row["cnt"] if row else 0
        return result

    # ── Public API ────────────────────────────────────────────────

    def get_entry(self, style_id: str) -> CatalogEntry | None:
        """Look up an entry by its ID."""
        return self._entry_index.get(style_id)

    def validate_type(self, style_id: str, name_type: str) -> bool:
        """Check if a style supports a given name_type."""
        entry = self._entry_index.get(style_id)
        if entry is None:
            return True  # unknown entries pass through (backward compat)
        return name_type in entry.supported_types

    def expand_abbreviation(self, style: str) -> str | None:
        """Expand abbreviated prefixes: 'dnd.drow_elfs' -> 'dungeon_and_dragons.drow_elfs'."""
        if "." in style:
            prefix, rest = style.split(".", 1)
            full = self._abbreviations.get(prefix)
            if full:
                return f"{full}.{rest}"
        return None

    def to_webapp_json(self) -> dict:
        """Return catalog as JSON-serializable dict for the webapp."""
        domains = []
        for domain_id in self._raw.get("domains", {}):
            groups_data = []
            for group in self._domains.get(domain_id, []):
                entries_data = [
                    {
                        "id": e.id,
                        "label": e.label,
                        "supported_types": e.supported_types,
                        "count": e.count,
                    }
                    for e in group.entries
                ]
                groups_data.append({
                    "id": group.id,
                    "label": group.label,
                    "abbreviation": group.abbreviation,
                    "entries": entries_data,
                })
            domains.append({
                "id": domain_id,
                "label": self._domain_labels.get(domain_id, domain_id),
                "groups": groups_data,
            })
        return {"domains": domains}
