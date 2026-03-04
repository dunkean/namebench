"""Fantasy name generator — ported from Snake4life JS generators."""

from __future__ import annotations

import random
from typing import Iterator, Optional

from namegen.db import NameDB


class FantasyGenerator:
    """Generate fantasy names using extracted phonetic arrays and patterns.

    Handles three modes:
    - flat_pick: random selection from a large name list
    - phonetic_concat: concatenate random phonemes from pools
    - type_split: different arrays for forename vs surname, male vs female
    """

    def __init__(self, db: NameDB, style_key: str):
        self.db = db
        self.style_key = style_key
        self._arrays: Optional[dict[str, list[str]]] = None
        self._meta: Optional[dict] = None

    def _load(self):
        if self._arrays is None:
            self._arrays = self.db.get_fantasy_arrays(self.style_key)
            self._meta = self.db.get_fantasy_meta(self.style_key)

    def _pick(self, arr_name: str) -> str:
        arr = self._arrays.get(arr_name, [])
        return random.choice(arr) if arr else ""

    def _generate_from_variant(self, variant: dict, extract: str = "full") -> str:
        """Generate from a variant.

        Args:
            extract: 'full' for complete name, 'first' for forename part,
                     'last' for surname part (when space_pos is set)
        """
        concat = variant["concat"]
        has_space = variant.get("space", False)
        space_pos = variant.get("space_pos", -1)

        parts = [self._pick(arr_name) for arr_name in concat]

        if has_space and space_pos > 0 and extract != "full":
            if extract == "first":
                return "".join(parts[:space_pos])
            elif extract == "last":
                return "".join(parts[space_pos:])

        if has_space and space_pos > 0:
            first = "".join(parts[:space_pos])
            last = "".join(parts[space_pos:])
            return f"{first} {last}".strip()

        return "".join(parts).strip()

    def _select_variant(
        self, name_type: str, gender: Optional[str], variants: list[dict]
    ) -> tuple[dict, str]:
        """Select appropriate variant and extraction mode.

        Returns (variant, extract_mode).
        """
        if not variants:
            return {}, "full"

        pattern = self._meta.get("pattern", {})
        has_type = pattern.get("has_type_param", False)

        # For type_split generators with space separators:
        # Each variant produces "forename surname" — extract the right part
        has_space_variants = [v for v in variants if v.get("space") and v.get("space_pos", -1) > 0]

        if has_space_variants and name_type in ("forename", "surname"):
            if name_type == "forename":
                if gender == "F":
                    # nm2 is typically the female forename list
                    female_v = [v for v in has_space_variants if "nm2" in v.get("concat", [])]
                    variant = female_v[0] if female_v else has_space_variants[0]
                else:
                    # nm1 is typically male; if no nm1-specific variant, use last
                    male_v = [v for v in has_space_variants if "nm1" in v.get("concat", [])]
                    variant = male_v[0] if male_v else has_space_variants[-1]
                return variant, "first"
            else:  # surname
                variant = random.choice(has_space_variants)
                return variant, "last"

        # Non-space variants: pick based on arrays used
        if has_type and name_type == "forename" and gender == "F":
            # Look for variant using nm2 (female list in many generators)
            female_v = [v for v in variants if "nm2" in v.get("concat", [])]
            if female_v:
                return random.choice(female_v), "full"

        return random.choice(variants), "full"

    def _generate_one(self, name_type: str, gender: Optional[str] = None) -> str:
        self._load()

        if not self._meta or not self._arrays:
            return ""

        pattern = self._meta.get("pattern", {})
        variants = pattern.get("variants", [])

        if not variants:
            # Fallback: pick from nm1
            nm1 = self._arrays.get("nm1", [])
            return random.choice(nm1) if nm1 else ""

        variant, extract = self._select_variant(name_type, gender, variants)
        if not variant:
            return ""

        return self._generate_from_variant(variant, extract)

    def generate(
        self,
        name_type: str,
        count: int,
        gender: Optional[str] = None,
    ) -> list[str]:
        self._load()

        results = set()
        attempts = 0
        max_attempts = count * 20

        while len(results) < count and attempts < max_attempts:
            name = self._generate_one(name_type, gender)
            if name and len(name) >= 2:
                # Capitalize each word
                name = " ".join(w.capitalize() for w in name.split())
                results.add(name)
            attempts += 1

        return list(results)[:count]

    def generate_bulk(
        self,
        name_type: str,
        count: int,
        gender: Optional[str] = None,
        unique: bool = False,
    ) -> Iterator[str]:
        self._load()
        seen = set() if unique else None
        yielded = 0
        max_attempts = count * 20 if unique else count * 2

        for _ in range(max_attempts):
            if yielded >= count:
                break
            name = self._generate_one(name_type, gender)
            if name and len(name) >= 2:
                name = " ".join(w.capitalize() for w in name.split())
                if unique:
                    if name in seen:
                        continue
                    seen.add(name)
                yield name
                yielded += 1
