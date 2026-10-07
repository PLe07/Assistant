# Avancement — Tableau de bord

Reprise après coupure : lire ce fichier et `DECISIONS.md`, puis reprendre à la première phase non cochée.
Chaque phase se termine par `./check.sh` vert, l'intégrité identique, un commit.

| Phase | État | Commit |
|---|---|---|
| P0 — environnement, empreinte, découverte, échantillons, squelette, check.sh | ✅ | « Tableau de bord P0 » |
| P1 — sondes en lecture seule | ⏳ | |
| P2 — registre et adaptateurs | ⏳ | |
| P3 — analyses | ⏳ | |
| P4 — alertes, sourdine, rapport de la semaine | ⏳ | |
| P5 — page web | ⏳ | |
| P6 — barre des menus, instantané iCloud, CLI | ⏳ | |
| P7 — faux écosystème complet | ⏳ | |
| P8 — installation | ⏳ | |
| P9 — 30 min réelles, performance | ⏳ | |
| P10 — revue hostile en deux passes | ⏳ | |

## P0 — 2026-10-07

- Empreinte « avant » prise **avant toute autre ligne du projet** : `integrite/empreinte.py` (bibliothèque standard
  seule) puis `integrite/etat_avant.json` — dépôt hôte hors `tableau-de-bord/` : 730 fichiers de code et de
  réglages (assistant, Corvées, Nettoyeur, Trieur, Bouclier, Quotidien), HEAD de départ `8c7ba63`, `git status` vide.
- Reconnaissance des autres modules (D-07) : Corvées, Nettoyeur, Trieur et tri Gmail tournent sous le superviseur de
  l'assistant ; Bouclier et Quotidien sont des LaunchAgents ; Ambiance n'est pas dans ce dépôt ; n8n est dans Docker.
- Échantillons réels **copiés puis anonymisés** (`outils/capturer_echantillons.py`, D-06) :
  `tests/fixtures/reelles/conteneur/` (journal de l'assistant : 520 lignes, dont les erreurs et avertissements
  anciens ; schémas exacts de `etat.db` et `trieur.db`).
- Socle : `config.py` (réglages validés, port 47615, jeton 600), `systeme.py` (liste blanche : 18 commandes permises
  et 35 interdites testées), `caviardage.py`, `db.py` (notre base, 600, WAL, base abîmée mise de côté, disque plein,
  agrégats 48 h / 90 jours), `module.py` (le modèle commun), `sondes/sqlite_copie.py` (copie cohérente des bases
  des autres).
- `check.sh` : intégrité (début), ruff, ruff format, mypy, pytest par groupes, couverture ≥ 90 %, intégrité (fin) ;
  `--complet` ajoute le faux écosystème et la performance.

Preuve (`./check.sh`) :

```
▶ intégrité des autres projets (début)
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
All checks passed!
Success: no issues found in 8 source files
94 passed in 8.95s
11 passed in 11.27s   (lecture seule : 30 lectures pendant les écritures, 0 « database is locked »)
12 passed in 3.07s    (empreinte)
TOTAL                              743      8    99%
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
CHECK OK
```
