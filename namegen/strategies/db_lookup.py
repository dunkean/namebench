"""Random database lookup strategy."""

from __future__ import annotations

import random
from typing import Iterator, Optional

from namegen.db import NameDB

# Countries where short names (1-2 chars) are common and valid
_SHORT_NAME_COUNTRIES = {
    "JP", "CN", "TW", "HK", "MO", "KR", "KP",  # CJK
    "VN", "TH", "LA", "KH", "MM",                # Southeast Asian
}

_BULK_BATCH = 10_000


class RandomDBLookup:
    """Pick random names from the SQLite database."""

    def __init__(self, db: NameDB, country_codes: list[str]):
        self.db = db
        self.country_codes = country_codes
        # Disable min-length filter when any CJK/SEA country is in the set
        self._min_length = 1 if set(country_codes) & _SHORT_NAME_COUNTRIES else 3
        self._pools: dict[tuple[str, Optional[str]], list[str]] = {}

    def _get_pool(self, name_type: str, gender: Optional[str] = None) -> list[str]:
        key = (name_type, gender)
        if key not in self._pools:
            if name_type == "place":
                self._pools[key] = self.db.all_places_pool(self.country_codes)
            else:
                self._pools[key] = self.db.all_names_pool(
                    self.country_codes, name_type, gender,
                    min_length=self._min_length,
                )
        return self._pools[key]

    def generate(
        self,
        name_type: str,
        count: int,
        gender: Optional[str] = None,
    ) -> list[str]:
        if count >= 1000:
            # Use pool path for large requests
            pool = self._get_pool(name_type, gender)
            if pool:
                if count <= len(pool):
                    return random.sample(pool, count)
                return random.choices(pool, k=count)
        if name_type == "place":
            return self.db.random_places(self.country_codes, count)
        return self.db.random_names(
            self.country_codes, name_type, count, gender,
            min_length=self._min_length,
        )

    def generate_bulk(
        self,
        name_type: str,
        count: int,
        gender: Optional[str] = None,
        unique: bool = False,
    ) -> Iterator[str]:
        pool = self._get_pool(name_type, gender)
        if not pool:
            return

        if unique:
            cap = min(count, len(pool))
            for name in random.sample(pool, cap):
                yield name
        else:
            remaining = count
            while remaining > 0:
                batch = min(remaining, _BULK_BATCH)
                for name in random.choices(pool, k=batch):
                    yield name
                remaining -= batch
