# Data sources

The bundled demo reads `namegen/data/demo.json`, a hand-authored sample. It is not a scrape or an extract of the world database. Its cache is separate from `data/names.db`.

Large source data and generated databases are excluded from Git.

| Source | Expected path at the checkout root |
| --- | --- |
| Forebears | `forebears_checkpoint/results.jsonl` |
| name-dataset | `philipperemy__name-dataset/` |
| GeoNames | `allCountries.zip` |
| Snake4life fantasy-names | `Snake4life__fantasy-names/` |
| Curated lists | `defaultDictionaries.json` (included) |

The current Forebears importer reads the JSONL checkpoint. `forebears_names.json` is a compiled local artifact, not its build input.

## Rebuild into a new file

Acquire the required source data, then run from the checkout root:

```powershell
$env:NAMEBENCH_DB_PATH="$PWD/data/names-rebuilt.db"
.venv\Scripts\python.exe -m namegen --build
.venv\Scripts\python.exe -m namegen --stats
.venv\Scripts\python.exe -m namegen demo --database data/names-rebuilt.db
```

The build refuses an existing output database. Several importers append rows, so repeat imports must use a new file. Missing sources are reported and skipped; such a build will be partial.

Install `.[scrape]` only to run the collection scripts. Normal demo use does not invoke them. Source datasets retain their own provenance and redistribution terms; the repository does not bundle them. Original-language names and diacritics are data, not untranslated interface text.
