# RPG Name Generator — World-Building Onomastics Engine

## Project Goal

Build a unified name generation system for world-building that produces person names (forenames, surnames) and place names based on **onomastic styles** — real-world cultural zones, historical periods, and fantasy/sci-fi archetypes.

### Core API Contract

```python
from namegen import generate, list_styles

generate("elf", "surname", 4)        # → 4 elvish surnames (fantasy, generated)
generate("mongol", "place", 3)        # → 3 Mongol-style place names (historical)
generate("latin", "surname", 1)       # → 1 Latin-style surname (real-world DB pick)
generate("japanese", "forename", 2, gender="F")  # → 2 Japanese female forenames
generate("cyberpunk", "forename", 5)  # → 5 sci-fi style forenames (generated)
generate("french", "fullname", 3)     # → 3 French full names (forename + surname)
generate("arabic", "forename", 2, romanize=True)  # → transliterated to Latin script
```

The system picks the best strategy per style: **random DB lookup** for real-world styles with rich data, **fantasy generation** (ported JS generators) for fantasy/sci-fi, **curated lists** for mythological/historical, **Markov chain** for procedural generation, or **hybrid** (DB + Markov).

## Data Sources

| Source | File/Dir | Content | Size |
|--------|----------|---------|------|
| Forebears scrape | `forebears_names.json` | 1.4M real surnames/forenames with top-5 countries | 122 MB |
| Forebears checkpoint | `forebears_checkpoint/` | JSONL with alt_forms, resumable scraping state | 234 MB |
| Snake4life fantasy-names | `Snake4life__fantasy-names/` | 150+ JS generators (fantasy races, games, sci-fi) | ~10 MB |
| name-dataset (philipperemy) | `philipperemy__name-dataset/` | First/last names with country, gender, rank (pickle) | 54 MB |
| GeoNames | `allCountries.zip` | All world place names (TSV, 1.77 GB uncompressed) | 398 MB |
| Default dictionaries | `defaultDictionaries.json` | Curated lists: demons, angels, Egyptian gods, planets, Greek cities, states, emperors | 16 KB |
| Onomastic zones | `onomastic_zones.json` | 70+ cultural styles, 15 historical overlays, 6 script zones, 20 macro groups, set operations | 13 KB |

## Architecture

- **Python 3.12+**, no heavy frameworks
- SQLite database at `data/names.db` (~927 MB), built via `python namegen.py --build`
- `namegen/` package with public API: `generate()` and `list_styles()`
- Lazy-initialized singletons for DB and StyleRegistry

### Package Structure

```
namegen/
├── __init__.py          # Public exports: generate, list_styles
├── api.py               # generate() and list_styles() implementation, romanization
├── db.py                # NameDB — SQLite schema and access layer
├── styles.py            # StyleRegistry — resolves style names → strategies
├── zones.py             # OnomasticResolver — parses onomastic_zones.json
├── country_map.py       # Country name/code mapping via pycountry
├── strategies/
│   ├── db_lookup.py     # RandomDBLookup — real-world names from SQLite
│   ├── fantasy.py       # FantasyGenerator — ported Snake4life JS generators
│   ├── curated.py       # CuratedListStrategy — mythological/historical lists
│   ├── markov.py        # MarkovChainGenerator — procedural generation
│   └── hybrid.py        # HybridStrategy — DB + Markov fallback
└── importers/
    ├── import_forebears.py     # Forebears JSON → SQLite
    ├── import_philipperemy.py  # name-dataset pickle → SQLite
    ├── import_geonames.py      # GeoNames TSV → SQLite
    ├── import_fantasy.py       # Snake4life JS parser → fantasy_meta table
    └── import_curated.py       # defaultDictionaries.json → curated_lists table
```

### Entry Points

- **CLI**: `python namegen.py <style> <type> <count> [--gender M/F] [--romanize] [--json]`
- **CLI admin**: `python namegen.py --build | --list | --stats`
- **Web UI**: `webapp/app.py` (Flask app with `templates/index.html`, `static/app.js`, `static/style.css`)
- **Python API**: `from namegen import generate, list_styles`

### Strategy Resolution

StyleRegistry resolves style names via chain: **curated → fantasy → onomastic aliases → onomastic zones**. Strategies:

| Strategy | Class | Use Case |
|----------|-------|----------|
| DB Lookup | `RandomDBLookup` | Real-world styles with country codes (e.g. `french`, `japanese`) |
| Fantasy | `FantasyGenerator` | Ported JS generators (e.g. `elf`, `dwarf`, `cyberpunk`) |
| Curated | `CuratedListStrategy` | Mythological/historical lists (e.g. `demons`, `angels`) |
| Markov | `MarkovChainGenerator` | Procedural generation trained on DB data |
| Hybrid | `HybridStrategy` | DB lookup with Markov fallback for variety |

### Database Schema (SQLite)

- **names** — ~12.8M rows: name, name_type, country_iso, gender, rank, source
- **places** — ~10.2M rows: geoname_id, name, country_iso, feature_class/code, population
- **fantasy_meta** — 731 generators: category, generator_name, js_source, parsed phoneme data
- **curated_lists** — 1,421 entries across 7 lists

## Key Files

- `namegen.py` — CLI entry point
- `onomastic_zones.json` — zone definitions (atomic tags, composites, overlays, set ops)
- `forebears_names.json` — main real-world name DB (import source)
- `defaultDictionaries.json` — curated mythological/historical name lists
- `scripts/scrape_forebears.py` — forebears.io scraper (3-phase: discover → scrape → compile)
- `scripts/scrape_github.py` — downloads GitHub name repos

## Conventions

- Style names are lowercase snake_case: `french`, `elf`, `steppe_mongol_xiii`, `cyberpunk`
- Name types: `forename`, `surname`, `fullname`, `place`
- Gender: `M`, `F`, or `None` (unspecified)
- All generated output is UTF-8, preserving diacritics
- `romanize=True` transliterates non-Latin scripts while preserving Latin diacritics (via `anyascii`)

## Known Gotchas

- Windows console needs UTF-8 wrapper (`sys.stdout` encoding fix in CLI)
- `pycountry` v26+ renamed Turkey → Türkiye; "Turkey" needs manual override in country_map
- `pycountry.search_fuzzy()` raises `LookupError` (not returns empty) — must wrap in try/except
- Fantasy JS parser: generators use intermediate variables (`nameLast = nm3 + nm4`) that must be resolved to get full concat chains
