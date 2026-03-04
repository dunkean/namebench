"""Markov chain name generator — character-level order-3."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Optional

from namegen.db import NameDB

# Sentinel tokens
START = "\x02"
END = "\x03"


class MarkovChainGenerator:
    """Generate names using character-level Markov chains."""

    def __init__(
        self,
        db: NameDB,
        country_codes: list[str],
        order: int = 3,
        training_limit: int = 10000,
    ):
        self.db = db
        self.country_codes = country_codes
        self.order = order
        self.training_limit = training_limit
        self._chains: dict[str, dict] = {}  # keyed by (name_type, gender)

    def _train(self, name_type: str, gender: Optional[str] = None) -> dict:
        """Build a Markov chain from DB names."""
        cache_key = f"{name_type}:{gender}"
        if cache_key in self._chains:
            return self._chains[cache_key]

        names = self.db.all_names_for_training(
            self.country_codes, name_type, gender, self.training_limit
        )

        chain: dict[str, list[str]] = defaultdict(list)

        for name in names:
            padded = START * self.order + name + END
            for i in range(len(padded) - self.order):
                key = padded[i : i + self.order]
                char = padded[i + self.order]
                chain[key].append(char)

        self._chains[cache_key] = dict(chain)
        return dict(chain)

    def _generate_one(self, chain: dict, max_len: int = 20) -> str:
        """Generate a single name from a trained chain."""
        current = START * self.order
        result = []

        for _ in range(max_len):
            options = chain.get(current)
            if not options:
                break
            char = random.choice(options)
            if char == END:
                break
            result.append(char)
            current = current[1:] + char

        name = "".join(result)
        # Capitalize first letter
        return name.capitalize() if name else name

    def generate(
        self,
        name_type: str,
        count: int,
        gender: Optional[str] = None,
    ) -> list[str]:
        if name_type == "place":
            # Train on place-like names from the names table, or use forename chain
            chain = self._train("forename", gender)
        else:
            chain = self._train(name_type, gender)

        if not chain:
            return []

        results = set()
        attempts = 0
        max_attempts = count * 10

        while len(results) < count and attempts < max_attempts:
            name = self._generate_one(chain)
            if len(name) >= 2:
                results.add(name)
            attempts += 1

        return list(results)[:count]
