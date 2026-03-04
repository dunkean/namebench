"""Curated list strategy — random pick from hand-curated lists."""

from __future__ import annotations

import random
from typing import Iterator, Optional

from namegen.db import NameDB


class CuratedListStrategy:
    """Pick random names from a curated mythological/historical list."""

    def __init__(self, db: NameDB, list_id: str):
        self.db = db
        self.list_id = list_id
        self._cache: Optional[list[str]] = None

    def _load(self) -> list[str]:
        if self._cache is None:
            self._cache = self.db.get_curated_list(self.list_id)
        return self._cache

    def generate(
        self,
        name_type: str,
        count: int,
        gender: Optional[str] = None,
    ) -> list[str]:
        names = self._load()
        if not names:
            return []
        # Sample with replacement if count > available
        if count <= len(names):
            return random.sample(names, count)
        return [random.choice(names) for _ in range(count)]

    def generate_bulk(
        self,
        name_type: str,
        count: int,
        gender: Optional[str] = None,
        unique: bool = False,
    ) -> Iterator[str]:
        names = self._load()
        if not names:
            return

        if unique:
            cap = min(count, len(names))
            for name in random.sample(names, cap):
                yield name
        else:
            for _ in range(count):
                yield random.choice(names)
