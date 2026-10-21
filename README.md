# Nomnom

Des noms à grignoter pour vos mondes imaginaires. Petit projet provisoire de prénoms, patronymes et toponymes : pays, cultures, listes et générateurs fantasy.

![Démo locale](docs/images/demo.png)


## Une démo qui démarre sans les gigas

Python 3.11+ (3.12 recommandé). Sous Windows : double-cliquer sur **`demo.cmd`**. Le premier lancement crée `.venv` et installe le projet ; ouvrir **http://127.0.0.1:5001** et garder le terminal ouvert.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m namegen demo
```

Sous Linux/macOS : utiliser `.venv/bin/python`. La petite base est construite depuis un échantillon écrit à la main, embarqué dans le paquet, puis conservée dans `~/.nomnom/demo-v1.db`. Aucun scraping ni téléchargement de données n'est nécessaire. Tester France/GB/Japon, elfes, lieux et export JSON/CSV/TXT. Tous les styles du moteur ne sont pas présents dans cet échantillon.

## Base mondiale locale

La base complète est **séparée** de la démo et ignorée par Git. Si `data/names.db` existe :

```powershell
.venv\Scripts\python.exe -m namegen demo --database data/names.db
.venv\Scripts\python.exe -m namegen french fullname 5 --json
.venv\Scripts\python.exe -m namegen mongol place 5
.venv\Scripts\python.exe -m namegen sw.wookiees forename 5
.venv\Scripts\python.exe -m namegen french surname 100000 --bulk
```

`NOMNOM_DB_PATH` permet de sélectionner la base pour le CLI et l'API Python. Pour interroger la petite démo depuis le CLI : définir cette variable sur `~/.nomnom/demo-v1.db` après son premier lancement. `--stats` décrit la base sélectionnée, `--list` les styles du moteur.

L'instantané local vérifié le 21 octobre 2026 contient 8 634 303 entrées de noms, 10 170 527 lieux, 731 générateurs fantasy et 1 421 entrées sélectionnées, pour 1,21 Go. Ce ne sont pas des nombres de noms uniques. Le clone Git contient le code et la démo, **pas** cette base.

Voir [les données et leur reconstruction](docs/data.md) avant de reconstruire une base complète. Le build refuse une base existante et exige un nouveau fichier de sortie.

## Python et codes personnalisés

```python
from namegen import generate, generate_bulk
names = generate("french", "fullname", 5)
for name in generate_bulk("elf", "surname", 100000):
    pass
```

`namegen/onomastic_zones.json` définit cultures, superpositions et opérations d'ensembles. `namegen/catalog.json` définit groupes et abréviations : pays ISO (`FR`, `JP`), cultures (`french`), fantasy (`elf`, `sw.wookiees`), listes (`demons`). Les dictionnaires sélectionnés restent dans `defaultDictionaries.json`.

## Contrat et limites

- Types : `forename`, `surname`, `fullname`, `place` ; genre `M`, `F` ou absent ; romanisation facultative.
- HTTP : `GET /api/catalog`, `GET /api/styles`, `POST /api/generate` avec `{"requests":[{"style":"FR","type":"fullname","count":5}]}`. Maximum 20 lignes de 100 noms ; entrées invalides : HTTP 400. Les erreurs par style sont dans chaque résultat.
- Un petit pool peut rendre moins de noms que demandé ; `returned_count` précise le résultat HTTP. Le bulk peut répéter ; `--unique` est plafonné au pool disponible.
- Les styles historiques sélectionnent surtout des pays actuels : aucune authenticité historique garantie. Les corpus mondiaux peuvent contenir du bruit.
- Le hasard SQLite n'est pas reproductible par une graine Python. Aucun contrat de replay déterministe à ce stade.
- Markov et hybride sont des stratégies expérimentales présentes dans le code, non sélectionnées par le résolveur public actuel.
- Serveur local de démonstration, sans debug ni reloader. Aucun lien avec Cousinade ou un moteur de cartes.

## Vérifier

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m build
npm ci
# Démo lancée sur 5001, Edge disponible sous Windows.
npm run test:browser
```

`STUDIO_BROWSER` choisit un autre exécutable Chromium/Edge et `NOMNOM_URL` une autre URL. Captures : `output/screenshots/` (ignoré).

L'historique Git du générateur d'origine est conservé. Les grandes données locales restent à leur place. Voir [l'origine du projet](PROVENANCE.md).
