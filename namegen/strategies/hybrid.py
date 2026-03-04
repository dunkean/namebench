"""Hybrid strategy — mix of database lookup and Markov generation."""

from __future__ import annotations

import random
from typing import Optional

from namegen.db import NameDB
from namegen.strategies.db_lookup import RandomDBLookup
from namegen.strategies.markov import MarkovChainGenerator


class HybridStrategy:
    """Mix database picks with Markov-generated names.

    Default split: 60% DB, 40% Markov.
    """

    def __init__(
        self,
        db: NameDB,
        country_codes: list[str],
        db_ratio: float = 0.6,
    ):
        self.db_lookup = RandomDBLookup(db, country_codes)
        self.markov = MarkovChainGenerator(db, country_codes)
        self.db_ratio = db_ratio

    def generate(
        self,
        name_type: str,
        count: int,
        gender: Optional[str] = None,
    ) -> list[str]:
        db_count = int(count * self.db_ratio)
        markov_count = count - db_count

        results = []

        if db_count > 0:
            results.extend(
                self.db_lookup.generate(name_type, db_count, gender)
            )

        if markov_count > 0:
            results.extend(
                self.markov.generate(name_type, markov_count, gender)
            )

        random.shuffle(results)
        return results[:count]
