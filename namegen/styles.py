"""StyleRegistry — resolves style names to strategies and country codes.

Auto-builds aliases from the fantasy_meta DB table so every imported
generator is reachable without hand-coding.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from namegen.db import NameDB
from namegen.zones import OnomasticResolver
from namegen.strategies.db_lookup import RandomDBLookup
from namegen.strategies.fantasy import FantasyGenerator
from namegen.strategies.markov import MarkovChainGenerator
from namegen.strategies.hybrid import HybridStrategy
from namegen.strategies.curated import CuratedListStrategy

# ── Static alias overrides (take priority over auto-generated) ────

# Onomastic shortcuts: user-friendly name -> onomastic zone ref
ONOMASTIC_ALIASES: dict[str, str] = {
    "french": "style.french",
    "italian": "style.italian",
    "spanish": "style.spanish_europe",
    "portuguese": "style.portuguese_europe",
    "german": "style.german_de_at",
    "dutch": "style.dutch_flemish",
    "english": "style.english_uk",
    "scandinavian": "style.scandinavian",
    "hungarian": "style.hungarian",
    "finnish": "style.finnish_estonian",
    "greek": "style.greek",
    "russian": "style.russian",
    "ukrainian": "style.ukrainian",
    "polish": "style.polish",
    "czech": "style.czech_slovak",
    "romanian": "style.romanian_moldovan",
    "arabic": "macro.arabic",
    "persian": "style.persian",
    "turkish": "style.turkish",
    "japanese": "style.japanese",
    "korean": "style.korean",
    "chinese": "style.mandarin",
    "mandarin": "style.mandarin",
    "cantonese": "style.cantonese",
    "vietnamese": "style.vietnamese",
    "thai": "style.indochina_thai_lao_khmer_burmese",
    "hindi": "style.hindi",
    "bengali": "style.bengali",
    "tamil": "style.tamil",
    "swahili": "style.swahili",
    "yoruba": "style.yoruba",
    "brazilian": "style.portuguese_brazil",
    "mexican": "style.spanish_americas",
    "latin": "overlay.roman_latin_ancient",
    "roman": "overlay.roman_latin_ancient",
    "viking": "overlay.viking_age",
    "celtic": "overlay.celtic_ancient",
    "byzantine": "overlay.byzantine",
    "ottoman": "overlay.ottoman",
    "mongol": "overlay.steppe_mongol_xiii",
    "slavic": "macro.slavic",
    "germanic": "macro.germanic",
    "romance": "macro.romance",
    "nordic": "macro.nordic_scandinavia",
    "balkan": "macro.balkan",
}

# Curated list shortcuts: user-friendly name -> curated list_id
CURATED_ALIASES: dict[str, str] = {
    "demons": "demons",
    "demon_names": "demons",
    "angels": "angels",
    "angel_names": "angels",
    "egyptian_gods": "egyptdeities",
    "egypt_gods": "egyptdeities",
    "planets": "planets",
    "greek_cities": "greekcities",
    "emperors": "emperors",
    "roman_emperors": "emperors",
    "states": "states",
}

# Category-level priority for short aliases when names collide.
# Lower = higher priority.  "fantasy" generic generators win bare names
# like "elf"; franchise-specific ones require the prefix.
_CATEGORY_PRIORITY = {
    "fantasy": 0,
    "dungeon_and_dragons": 1,
    "pathfinder": 2,
    "lord_of_the_rings": 3,
    "elder_scrolls": 4,
    "warhammer": 5,
    "warhammer_40k": 6,
    "star_wars": 7,
    "star_wars_the_old_republic": 8,
    "star_trek": 9,
    "halo": 10,
    "mass_effect": 11,
    "game_of_thrones": 12,
    "world_of_warcraft": 13,
    "final_fantasy": 14,
    "guild_wars": 15,
    "dragon_age": 16,
    "the_witcher": 17,
    "inheritance_cycle": 18,
    "legend_of_zelda": 19,
    "doctor_who": 20,
    "harry_potter": 21,
    "destiny": 22,
    "diablo": 23,
    "dragon_ball": 24,
    "pop_culture": 25,
    "real": 26,
    "places": 27,
    "towns_and_cities": 28,
    "pets": 29,
    "miscellaneous": 30,
    "descriptions": 90,
    "armour": 91,
    "weapons": 92,
}


def _singularize(name: str) -> str | None:
    """Naive singularization: only strip plural from the LAST segment.

    e.g. 'stormlight_archives' -> 'stormlight_archive'
         'elfs' -> 'elf'
         'fairies' -> 'fairy' (not used in our data, but just in case)
    """
    # Split on underscore, singularize last part only
    parts = name.split("_")
    last = parts[-1]

    if last.endswith("ies") and len(last) > 4:
        singular = last[:-3] + "y"
    elif last in ("dwarves", "elves", "halves", "wolves", "knives", "lives", "wives"):
        singular = last[:-3] + "f"  # only well-known -ves -> -f words
    elif last.endswith("s") and not last.endswith("ss") and len(last) > 2:
        singular = last[:-1]
    else:
        return None

    if singular == last:
        return None
    parts[-1] = singular
    return "_".join(parts)


def _normalize_alias(name: str) -> str:
    """Normalize a generator name for alias matching.

    Strips trailing 's' plurals and converts underscores to various forms.
    """
    return name.lower().replace("_", " ").strip()


def _build_fantasy_aliases(style_keys: list[str]) -> dict[str, str]:
    """Auto-generate short aliases from every fantasy style key.

    For each `category.gen_name` key, creates aliases:
      - gen_name                    (if unique across categories, or highest-priority cat wins)
      - singular(gen_name)          (same rule)
      - category.gen_name           (always unique — already the key itself)
      - category_gen_name           (underscore join, always created)
      - category gen_name           (space join, for fuzzy matching)

    Collision rule: when multiple categories have the same gen_name (e.g. dwarfs),
    the category with the lowest _CATEGORY_PRIORITY wins the bare alias.
    Others are only reachable via their full key.
    """
    # Group generators by bare name
    by_name: dict[str, list[tuple[int, str]]] = defaultdict(list)
    # key = bare gen name, value = [(priority, full_style_key), ...]

    for key in style_keys:
        if "." not in key:
            continue
        cat, gen = key.split(".", 1)
        prio = _CATEGORY_PRIORITY.get(cat, 50)
        by_name[gen].append((prio, key))

    aliases: dict[str, str] = {}

    for gen_name, entries in by_name.items():
        entries.sort()  # sort by priority

        # Every entry gets its full key as an alias (identity — handled by direct lookup)
        # and underscore/space join forms
        for _, full_key in entries:
            cat, gen = full_key.split(".", 1)
            # category_gen form (e.g. star_wars_wookiees)
            cat_gen = f"{cat}_{gen}"
            if cat_gen not in aliases:
                aliases[cat_gen] = full_key
            # space form (e.g. "star wars wookiees")
            space_form = f"{cat} {gen}".replace("_", " ")
            if space_form not in aliases:
                aliases[space_form] = full_key

        # Bare name goes to highest-priority category
        winner_key = entries[0][1]
        if gen_name not in aliases:
            aliases[gen_name] = winner_key

        # Singular form of bare name
        singular = _singularize(gen_name)
        if singular and singular not in aliases:
            aliases[singular] = winner_key

        # Underscore-stripped forms (e.g. "cat_people_nekojins" -> "cat people nekojins")
        if "_" in gen_name:
            space_name = gen_name.replace("_", " ")
            if space_name not in aliases:
                aliases[space_name] = winner_key
            # Also try without trailing s
            if singular and "_" in gen_name:
                sing_space = singular.replace("_", " ")
                if sing_space not in aliases:
                    aliases[sing_space] = winner_key

    return aliases


@dataclass
class StyleSpec:
    """Resolved style specification."""

    name: str
    category: str  # 'curated', 'fantasy', 'onomastic'
    country_codes: list[str] = field(default_factory=list)
    strategy_key: str = ""  # curated list_id or fantasy style_key or zone ref
    supported_types: list[str] = field(default_factory=list)


class StyleRegistry:
    """Resolves style names to strategies.

    Resolution chain (first match wins):
    1. Curated aliases  (demons, angels, planets, ...)
    2. Direct fantasy key  (star_wars.wookiees)
    3. Onomastic aliases  (french, mongol, viking, ...)
    4. Direct onomastic ref  (style.french, overlay.viking_age)
    5. Onomastic prefix probe  (try style.X, overlay.X, macro.X)
    6. Auto-generated fantasy aliases  (wookiee, klingon, elf, ...)
    """

    def __init__(self, db: NameDB, zones: OnomasticResolver, catalog=None):
        self.db = db
        self.zones = zones
        self.catalog = catalog
        self._fantasy_styles: Optional[set[str]] = None
        self._fantasy_aliases: Optional[dict[str, str]] = None
        self._fantasy_categories: Optional[dict[str, list[str]]] = None
        self._curated_id_set: Optional[set[str]] = None
        self._strategy_cache: dict[tuple, object] = {}

    def _curated_ids(self) -> set[str]:
        if self._curated_id_set is None:
            self._curated_id_set = set(self.db.list_curated_ids())
        return self._curated_id_set

    @property
    def fantasy_styles(self) -> set[str]:
        if self._fantasy_styles is None:
            self._fantasy_styles = set(self.db.list_fantasy_styles())
        return self._fantasy_styles

    @property
    def fantasy_aliases(self) -> dict[str, str]:
        if self._fantasy_aliases is None:
            self._fantasy_aliases = _build_fantasy_aliases(
                sorted(self.fantasy_styles)
            )
        return self._fantasy_aliases

    @property
    def fantasy_categories(self) -> dict[str, list[str]]:
        """Map category name -> list of generator names in that category."""
        if self._fantasy_categories is None:
            cats: dict[str, list[str]] = defaultdict(list)
            for key in sorted(self.fantasy_styles):
                if "." in key:
                    cat, gen = key.split(".", 1)
                    cats[cat].append(gen)
            self._fantasy_categories = dict(cats)
        return self._fantasy_categories

    def resolve(self, style: str) -> Optional[StyleSpec]:
        """Resolve a style name to a StyleSpec."""
        spec = self._resolve_inner(style)
        if spec is not None and spec.category == "onomastic":
            spec.supported_types = ["forename", "surname", "fullname", "place"]
        if spec is not None and self.catalog and not spec.supported_types:
            entry = self.catalog.get_entry(spec.strategy_key)
            if entry:
                spec.supported_types = entry.supported_types
        return spec

    def _resolve_inner(self, style: str) -> Optional[StyleSpec]:
        style_lower = style.lower().strip()

        # 0. Abbreviation expansion (dnd.X → dungeon_and_dragons.X)
        if self.catalog:
            expanded = self.catalog.expand_abbreviation(style_lower)
            if expanded:
                style_lower = expanded

        # 0b. Direct country ISO code (e.g. "AL", "FR", "JP")
        style_upper = style.strip().upper()
        if len(style_upper) == 2 and style_upper.isalpha():
            if self.catalog and self.catalog.get_entry(style_upper):
                return StyleSpec(
                    name=style_upper,
                    category="onomastic",
                    country_codes=[style_upper],
                    strategy_key=style_upper,
                )

        # 1. Curated aliases
        if style_lower in CURATED_ALIASES:
            list_id = CURATED_ALIASES[style_lower]
            return StyleSpec(
                name=style_lower,
                category="curated",
                strategy_key=list_id,
            )

        # 1b. Direct curated list ID (e.g. "egyptdeities", "demons")
        if style_lower in self._curated_ids():
            return StyleSpec(
                name=style_lower,
                category="curated",
                strategy_key=style_lower,
            )

        # 2. Direct fantasy key (e.g. star_wars.wookiees)
        if style_lower in self.fantasy_styles:
            return StyleSpec(
                name=style_lower,
                category="fantasy",
                strategy_key=style_lower,
            )

        # 3. Onomastic aliases (french, mongol, viking, ...)
        #    Checked before auto fantasy aliases so hand-curated onomastic
        #    mappings win over auto-generated fantasy ones (e.g. "viking"
        #    → overlay.viking_age DB lookup, not real.vikings phonetic gen).
        if style_lower in ONOMASTIC_ALIASES:
            ref = ONOMASTIC_ALIASES[style_lower]
            codes = self.zones.resolve(ref)
            if codes:
                return StyleSpec(
                    name=style_lower,
                    category="onomastic",
                    country_codes=sorted(codes),
                    strategy_key=ref,
                )

        # 4. Direct onomastic ref
        codes = self.zones.resolve(style_lower)
        if codes:
            return StyleSpec(
                name=style_lower,
                category="onomastic",
                country_codes=sorted(codes),
                strategy_key=style_lower,
            )

        # 5. Onomastic prefix probe
        for prefix in ("style", "overlay", "macro", "script"):
            ref = f"{prefix}.{style_lower}"
            codes = self.zones.resolve(ref)
            if codes:
                return StyleSpec(
                    name=style_lower,
                    category="onomastic",
                    country_codes=sorted(codes),
                    strategy_key=ref,
                )

        # 6. Auto-generated fantasy aliases (wookiee, klingon, elf, ...)
        if style_lower in self.fantasy_aliases:
            fkey = self.fantasy_aliases[style_lower]
            return StyleSpec(
                name=style_lower,
                category="fantasy",
                strategy_key=fkey,
            )

        # 6b. Try underscore ↔ space variants
        for alt in (style_lower.replace(" ", "_"), style_lower.replace("_", " ")):
            if alt != style_lower:
                if alt in self.fantasy_styles:
                    return StyleSpec(name=style_lower, category="fantasy",
                                    strategy_key=alt)
                if alt in self.fantasy_aliases:
                    return StyleSpec(name=style_lower, category="fantasy",
                                    strategy_key=self.fantasy_aliases[alt])

        return None

    def get_strategy(self, spec: StyleSpec):
        """Get (or create and cache) the appropriate strategy for a resolved style."""
        cache_key = (spec.category, spec.strategy_key, tuple(spec.country_codes))
        cached = self._strategy_cache.get(cache_key)
        if cached is not None:
            return cached

        if spec.category == "curated":
            strategy = CuratedListStrategy(self.db, spec.strategy_key)
        elif spec.category == "fantasy":
            strategy = FantasyGenerator(self.db, spec.strategy_key)
        elif spec.category == "onomastic":
            strategy = RandomDBLookup(self.db, spec.country_codes)
        else:
            return None

        self._strategy_cache[cache_key] = strategy
        return strategy

    def list_styles(self) -> dict[str, list[str]]:
        """List all available styles grouped by category."""
        result: dict[str, list[str]] = {}

        # Curated
        curated_ids = self.db.list_curated_ids()
        if curated_ids:
            result["curated"] = sorted(
                set(curated_ids) | set(CURATED_ALIASES.keys())
            )

        # Fantasy — group by sub-category for readability
        for cat in sorted(self.fantasy_categories):
            gens = self.fantasy_categories[cat]
            result[f"fantasy/{cat}"] = sorted(gens)

        # Onomastic
        onomastic_refs = self.zones.list_all_refs()
        onomastic_all = sorted(
            set(ONOMASTIC_ALIASES.keys())
            | {ref for refs in onomastic_refs.values() for ref in refs}
        )
        if onomastic_all:
            result["onomastic"] = onomastic_all

        return result
