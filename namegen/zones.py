"""Onomastic zone resolver — maps style refs to sets of ISO country codes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

ZONES_PATH = Path(__file__).resolve().parent.parent / "onomastic_zones.json"


class OnomasticResolver:
    """Resolves onomastic zone references to sets of country codes."""

    def __init__(self, zones_path: Path | str | None = None):
        path = Path(zones_path) if zones_path else ZONES_PATH
        with open(path, "r", encoding="utf-8") as f:
            self._data = json.load(f)

        self._atomic = self._data.get("atomic_tags", {})
        self._composites = self._data.get("composite_tags", {})

    def resolve(self, ref: str) -> Optional[set[str]]:
        """Resolve a ref like 'style.french' or 'macro.slavic' to a set of ISO codes.

        Supported ref formats:
          - style.<id>       -> atomic style countries
          - overlay.<id>     -> atomic overlay countries
          - script.<id>      -> atomic script countries
          - macro.<id>       -> composite macro (with set ops)
          - <id>             -> probe style, then overlay, then macro
        """
        # Try direct category.id format
        if "." in ref:
            category, tag_id = ref.split(".", 1)
            return self._resolve_qualified(category, tag_id)

        # Unqualified: probe in order
        for category in ("style", "overlay", "script"):
            if tag_id := self._find_in_atomic(category, ref):
                return self._get_atomic_countries(category, tag_id)

        # Try composites
        for category in self._composites:
            if ref in self._composites[category]:
                return self._resolve_composite(category, ref)

        return None

    def _resolve_qualified(self, category: str, tag_id: str) -> Optional[set[str]]:
        """Resolve a fully qualified ref."""
        # Atomic tags
        if category in self._atomic and tag_id in self._atomic[category]:
            return self._get_atomic_countries(category, tag_id)

        # Composite tags
        if category in self._composites and tag_id in self._composites[category]:
            return self._resolve_composite(category, tag_id)

        return None

    def _find_in_atomic(self, category: str, tag_id: str) -> Optional[str]:
        """Find a tag_id in an atomic category, return the key if found."""
        if category in self._atomic and tag_id in self._atomic[category]:
            return tag_id
        return None

    def _get_atomic_countries(self, category: str, tag_id: str) -> set[str]:
        """Get country codes from an atomic tag."""
        entry = self._atomic[category][tag_id]
        return set(entry.get("countries", []))

    def _resolve_composite(self, category: str, tag_id: str) -> set[str]:
        """Resolve a composite tag using set operations."""
        entry = self._composites[category][tag_id]
        defn = entry.get("definition", {})
        return self._apply_definition(defn)

    def _apply_definition(self, defn: dict) -> set[str]:
        """Apply a set-operation definition to produce country codes."""
        op = defn.get("op", "union")
        tags = defn.get("tags", [])

        # Resolve each referenced tag
        tag_sets = []
        for tag_ref in tags:
            resolved = self.resolve(tag_ref)
            if resolved is not None:
                tag_sets.append(resolved)

        # Apply operation
        if not tag_sets:
            result: set[str] = set()
        elif op == "union":
            result = set()
            for s in tag_sets:
                result |= s
        elif op == "intersect":
            result = tag_sets[0].copy()
            for s in tag_sets[1:]:
                result &= s
        elif op == "diff":
            result = tag_sets[0].copy()
            for s in tag_sets[1:]:
                result -= s
        else:
            result = set()

        # Apply add/remove modifiers
        for code in defn.get("add_countries", []):
            result.add(code)
        for code in defn.get("remove_countries", []):
            result.discard(code)

        return result

    def list_all_refs(self) -> dict[str, list[str]]:
        """List all available refs grouped by category."""
        result: dict[str, list[str]] = {}

        for category in self._atomic:
            refs = [f"{category}.{tag_id}" for tag_id in self._atomic[category]]
            if refs:
                result[category] = sorted(refs)

        for category in self._composites:
            refs = [f"{category}.{tag_id}" for tag_id in self._composites[category]]
            if refs:
                result[category] = sorted(refs)

        return result

    def get_label(self, ref: str) -> Optional[str]:
        """Get the human-readable label for a ref."""
        if "." in ref:
            category, tag_id = ref.split(".", 1)
            if category in self._atomic and tag_id in self._atomic[category]:
                return self._atomic[category][tag_id].get("label")
            if category in self._composites and tag_id in self._composites[category]:
                return self._composites[category][tag_id].get("label")
        return None
