# Données de Nomnom

La démo utilise `namegen/data/demo.json`, un petit échantillon écrit à la main ; il n'est pas extrait des corpus mondiaux. Sa base SQLite est distincte de `data/names.db`.

Les grandes sources locales et les produits de scraping sont exclus de Git :

| Source | Chemin attendu à la racine |
| --- | --- |
| Forebears | `forebears_checkpoint/results.jsonl` (entrée effective de l'importeur) |
| name-dataset | `philipperemy__name-dataset/` |
| GeoNames | `allCountries.zip` |
| Snake4life fantasy-names | `Snake4life__fantasy-names/` |
| Listes sélectionnées | `defaultDictionaries.json` (inclus) |

Le JSON `forebears_names.json` est un produit local de compilation ; le build actuel lit le checkpoint JSONL. Ne pas le confondre avec l'entrée réelle.

Après acquisition des sources et vérification de leurs conditions d'utilisation, depuis la racine d'un clone, créer une **nouvelle base**, sans modifier l'existante :

```powershell
$env:NOMNOM_DB_PATH="$PWD/data/names-rebuilt.db"
.venv\Scripts\python.exe -m namegen --build
.venv\Scripts\python.exe -m namegen --stats
.venv\Scripts\python.exe -m namegen demo --database data/names-rebuilt.db
```

Installer `.[scrape]` uniquement pour utiliser les scripts de collecte. Le lancement normal n'utilise pas ces scripts. Les importeurs indiquent les sources absentes ; une base construite sans toutes les sources sera partielle. Le build refuse désormais toute base existante : choisir un nouveau fichier pour éviter les doublons des importeurs.

La présence des scripts et d'une base locale ne vaut pas autorisation de redistribuer les données. Le dépôt ne distribue aucun gros corpus ; les provenances et avis des sources doivent accompagner toute distribution séparée.
