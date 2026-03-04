# RPG Name Generator

A unified name generation system for world-building that produces person names (forenames, surnames) and place names based on onomastic styles -- real-world cultural zones, historical periods, and fantasy/sci-fi archetypes.

## Setup

### Requirements

- Python 3.12+
- Dependencies: `flask`, `pycountry`, `anyascii`

```bash
pip install -r requirements.txt
pip install pycountry anyascii
```

### Download Data Sources

Before building the database, download the required data sources into the project root:

| Source | Target Path | How to Get |
|--------|-------------|------------|
| Forebears | `forebears_names.json` | Run `scripts/scrape_forebears.py` (scrapes forebears.io) |
| name-dataset | `philipperemy__name-dataset/` | `git clone https://github.com/philipperemy/name-dataset` and rename |
| GeoNames | `allCountries.zip` | Download from [GeoNames](https://download.geonames.org/export/dump/allCountries.zip) (398 MB) |
| Snake4life fantasy-names | `Snake4life__fantasy-names/` | `git clone https://github.com/Snake4life/fantasy-names` and rename |
| Curated lists | `defaultDictionaries.json` | Already included in the repo |

### Build the Database

The SQLite database must be built before first use. This imports all data sources into `data/names.db` (~927 MB):

```bash
python namegen.py --build
```

## CLI Usage

```
python namegen.py <style> <type> <count> [options]
```

### Positional Arguments

| Argument | Description | Values |
|----------|-------------|--------|
| `style` | Name style | `french`, `elf`, `demons`, `japanese`, `cyberpunk`, etc. |
| `type` | Name type | `forename`, `surname`, `fullname`, `place` |
| `count` | Number of names | Any positive integer |

### Options

| Flag | Short | Description |
|------|-------|-------------|
| `--gender M/F` | `-g` | Filter by gender (M or F) |
| `--json` | `-j` | Output as JSON array |
| `--romanize` | `-r` | Transliterate non-Latin characters to ASCII |
| `--bulk` | `-b` | Force bulk streaming mode (auto-enabled for count >= 1000) |
| `--unique` | `-u` | No duplicate names (capped at pool size) |

### Admin Commands

```bash
python namegen.py --build    # Build/rebuild the SQLite database
python namegen.py --list     # List all available styles
python namegen.py --stats    # Show database row counts
```

### Examples

```bash
# Basic generation
python namegen.py french forename 5
python namegen.py elf surname 10
python namegen.py demons forename 3
python namegen.py japanese forename 5 --gender F

# Full names (forename + surname)
python namegen.py french fullname 5
python namegen.py elf fullname 10

# Place names
python namegen.py mongol place 5

# Transliteration
python namegen.py arabic forename 5 --romanize
python namegen.py japanese forename 5 --romanize

# JSON output
python namegen.py french forename 10 --json

# Bulk generation (streaming, fast)
python namegen.py french forename 100000
python namegen.py elf surname 1000000
python namegen.py japanese forename 50000 --gender F --unique

# Pipe to file
python namegen.py arabic place 500000 --romanize > places.txt
```

### Bulk Mode

For counts >= 1000, bulk mode activates automatically. It pre-loads name pools into memory and samples from Python, making per-name cost near-zero after the initial load.

- **100 names**: ~0.2s
- **100,000 names**: ~0.4s

Use `--unique` to guarantee no duplicates (output is capped at the available pool size). Use `--bulk` to force bulk mode for smaller counts.

## Python API

```python
from namegen import generate, generate_bulk, list_styles

# Standard generation (returns list)
names = generate("french", "forename", 10)
names = generate("elf", "surname", 5, gender="M")
names = generate("japanese", "forename", 3, gender="F", romanize=True)

# Bulk generation (returns iterator, streams one name at a time)
for name in generate_bulk("french", "forename", 100000):
    print(name)

# Bulk with unique names
for name in generate_bulk("japanese", "forename", 50000, gender="F", unique=True):
    print(name)

# List all available styles
styles = list_styles()
for category, names in styles.items():
    print(f"{category}: {len(names)} styles")
```

### API Reference

#### `generate(style, name_type, count, gender, romanize)`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `style` | str | required | Style name |
| `name_type` | str | `"forename"` | `forename`, `surname`, `fullname`, `place` |
| `count` | int | `1` | Number of names |
| `gender` | str/None | `None` | `"M"`, `"F"`, or `None` |
| `romanize` | bool | `False` | Transliterate non-Latin scripts |

Returns: `list[str]`

#### `generate_bulk(style, name_type, count, gender, romanize, unique)`

Same parameters as `generate()`, plus:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `unique` | bool | `False` | No duplicates (capped at pool size) |

Returns: `Iterator[str]` (streaming, never holds all names in memory)

#### `list_styles()`

Returns: `dict[str, list[str]]` -- styles grouped by category

## Web App

A Flask web UI for interactive name generation.

### Running

```bash
cd webapp
python app.py
```

Opens at `http://127.0.0.1:5000`.

### API Endpoints

#### `GET /`
Serves the web UI.

#### `GET /api/styles`
Returns the full style catalog as JSON, grouped by category.

#### `POST /api/generate`
Generate names. Accepts JSON body:

```json
{
  "requests": [
    {
      "style": "french",
      "type": "forename",
      "count": 10,
      "gender": "F",
      "romanize": false
    }
  ]
}
```

Returns:

```json
{
  "results": [
    {
      "style": "french",
      "type": "forename",
      "count": 10,
      "gender": "F",
      "romanize": false,
      "names": ["Marie", "Sophie", ...]
    }
  ]
}
```

Count is capped at 100 per request via the web API.

## Available Styles

### Strategy Types

| Strategy | Use Case | Examples |
|----------|----------|---------|
| **DB Lookup** | Real-world cultural names from 12.8M name database | `french`, `japanese`, `arabic`, `russian` |
| **Fantasy** | Ported JS generators (731 generators across 36 categories) | `elf`, `dwarf`, `cyberpunk`, `klingon` |
| **Curated** | Hand-curated mythological/historical lists | `demons`, `angels`, `egyptian_gods`, `emperors` |
| **Markov** | Procedural generation trained on DB data | Used as fallback in hybrid mode |
| **Hybrid** | DB lookup with Markov fallback | Combines real data with procedural variety |

### Onomastic Styles (Real-World)

`french`, `italian`, `spanish`, `portuguese`, `german`, `dutch`, `english`, `scandinavian`, `hungarian`, `finnish`, `greek`, `russian`, `ukrainian`, `polish`, `czech`, `romanian`, `arabic`, `persian`, `turkish`, `japanese`, `korean`, `chinese`, `mandarin`, `cantonese`, `vietnamese`, `thai`, `hindi`, `bengali`, `tamil`, `swahili`, `yoruba`, `brazilian`, `mexican`, `latin`, `roman`, `viking`, `celtic`, `byzantine`, `ottoman`, `mongol`, `slavic`, `germanic`, `romance`, `nordic`, `balkan`

### Curated Lists

`demons`, `angels`, `egyptian_gods`, `planets`, `greek_cities`, `emperors`, `states`

### Fantasy

Run `python namegen.py --list` to see all 731 fantasy generators organized by franchise (D&D, Elder Scrolls, Star Wars, Warhammer, etc.).

## Project Structure

```
namegen/
  __init__.py          # Public exports: generate, generate_bulk, list_styles
  api.py               # generate() and generate_bulk() implementation
  db.py                # NameDB -- SQLite schema and access layer
  styles.py            # StyleRegistry -- resolves style names to strategies
  zones.py             # OnomasticResolver -- parses onomastic_zones.json
  country_map.py       # Country name/code mapping via pycountry
  strategies/
    db_lookup.py       # RandomDBLookup -- real-world names from SQLite
    fantasy.py         # FantasyGenerator -- ported Snake4life JS generators
    curated.py         # CuratedListStrategy -- mythological/historical lists
    markov.py          # MarkovChainGenerator -- procedural generation
    hybrid.py          # HybridStrategy -- DB + Markov fallback
  importers/
    import_forebears.py
    import_philipperemy.py
    import_geonames.py
    import_fantasy.py
    import_curated.py
webapp/
  app.py               # Flask web app
  templates/index.html  # Web UI
  static/app.js        # Frontend JS
  static/style.css     # Styles
scripts/
  scrape_forebears.py  # Forebears.io scraper
  scrape_github.py     # GitHub dataset downloader
namegen.py             # CLI entry point
```
