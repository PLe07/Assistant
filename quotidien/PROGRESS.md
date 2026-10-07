# Avancement — Quotidien

Reprise après coupure : lire ce fichier et `DECISIONS.md`, puis reprendre à la première phase non cochée.
Chaque phase se termine par `./check.sh` vert, l'intégrité identique, un commit.

| Phase | État | Commit |
|---|---|---|
| P0 — environnement, intégrité, squelette, check.sh, réseau | ✅ | « Quotidien P0 » |
| P1 — météo « habille-toi » | ⏳ | |
| P2 — base de recettes | ⏳ | |
| P3 — planificateur et courses | ⏳ | |
| P4 — vide-frigo | ⏳ | |
| P5 — anniversaires | ⏳ | |
| P6 — brief, page, Rappels, iCloud, raccourcis | ⏳ | |
| P7 — démon, planification, doctor, budget IA | ⏳ | |
| P8 — bout en bout | ⏳ | |
| P9 — installation (script + vérification sur le Mac) | ⏳ | |
| P10 — revue hostile en deux passes | ⏳ | |

## P0 — 2026-10-07

- Empreinte « avant » prise **avant toute autre ligne** : `integrite/empreinte.py` puis
  `integrite/etat_avant.json` (dépôt hôte hors `quotidien/` : 593 fichiers, dont tout `bouclier/`).
- `quotidien/` : `pyproject.toml`, `.venv` (Python 3.11 ici), `config.py` (deux fichiers à toi, validés, valeurs par
  défaut), `db.py` (SQLite en 600, base corrompue mise de côté), `journal.py` (caviardé), `caviardage.py`,
  `reseau.py` (liste blanche : `api.anthropic.com`, `api.open-meteo.com`, `geocoding-api.open-meteo.com`).
- `tests/conftest.py` : maison imitée, réseau coupé et espionné (un hôte hors liste tenté fait échouer le test).
- `check.sh` : intégrité (début), ruff, mypy, pytest par groupes, couverture ≥ 90 %, intégrité (fin).

Preuve (`./check.sh`, extrait) :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 593 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 7 élément(s) divers, listes de Rappels : indisponibles)
All checks passed!
41 passed in 0.62s
25 passed in 0.27s
TOTAL                   421     22    95%
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 593 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 7 élément(s) divers, listes de Rappels : indisponibles)
CHECK OK
```
