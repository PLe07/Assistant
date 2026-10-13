# Avancement de Voix

Chaque phase se termine par `./check.sh` vert, l'intégrité des autres projets identique, un commit, et la preuve
collée ici (sortie réelle).

| Phase | État |
|---|---|
| P0 — environnement, empreinte, squelettes, check.sh | ✅ |
| P1 — compréhension et corpus de phrases | ✅ réglage ; ⚠️ anti-triche 86–89 % < 95 % (D-13) |
| P2 — actions, annulation, confirmation, modules, sécurité | ⏳ |
| P3 — moteur audio et corpus audio | ⏳ |
| P4 — app Swift | ⏳ |
| P5 — mot d'éveil et suspension pendant les appels | ⏳ |
| P6 — banc d'essai complet, choix du moteur | ⏳ |
| P7 — routines, concentration, aide-mémoire, réglages, doctor, verifier | ⏳ |
| P8 — tests réels sans risque, ressources, robustesse | ⏳ |
| P9 — installation (build unique, 2 LaunchAgents, kill/relance) | ⏳ |
| P10 — revue hostile en deux passes | ⏳ |

## P0 — environnement, empreinte, squelettes, check.sh ✅

- Empreinte « avant » prise **avant toute autre ligne de code** (`integrite/etat_avant.json`) : le dépôt de
  l'assistant hors `voix/` (853 fichiers, arbre git, statut), LaunchAgents, Application Support des autres modules,
  `~/.zshrc`, `~/.zprofile`, `crontab -l`, `shortcuts list`, `docker ps -a`, export des raccourcis clavier du système.
  Sur ton Mac, `install.sh` prend la sienne avant de rien poser (`integrite/mac/`, jamais sur GitHub).
- Raccourci : lecture de l'export `com.apple.symbolichotkeys` et choix du premier candidat libre (D-08), testé sur des
  exports XML et binaires (valeurs d'usine, raccourcis désactivés ou déplacés, entrées étranges, export illisible).
- Squelettes : paquet Python `voix` (réglages bornés, choix automatiques séparés de tes réglages), paquet Swift
  (Core vérifié ici sous Linux avec Swift 6.2.4, XCTest et sans XCTest ; app macOS), `check.sh`.

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 853 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 6 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ swift build -c release
controles-core : 2 réussi(s), 0 échec(s)
  ✅ swift : contrôles du Core (sans XCTest)
	 Executed 2 tests, with 0 failures (0 unexpected) in 0.102 (0.102) seconds
  ✅ swift test (XCTest)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
25 passed in 0.40s
  ✅ socle (unitaires)
15 passed in 3.88s
  ✅ gardien d'intégrité
TOTAL                348      6    98%
  ✅ couverture ≥ 90 % sur voix/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 853 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 6 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```

## P1 — compréhension et corpus de phrases ✅ réglage ; ⚠️ anti-triche sous le seuil

- 69 intentions dans la liste blanche (4 sensibles, confirmées à la voix), normalisation (nombres en lettres,
  politesse, oral, négation), grammaire de phrases entières, catalogue (apps, sites, dossiers, alias, raccourcis,
  routines, playlists) avec ressemblance écrite et phonétique, ambiguïtés « Notes ou Notion ? », refus par choix.
- Seconde lecture (D-11) : phrases remises dans l'ordre, questions par mots, sacs de mots stricts, garde-fous.
- Corpus : jeu 1 généré (2 224 ordres, 332 hors catalogue) + 7 jeux écrits à la main (2 614 ordres, 285 hors
  catalogue). Après réglage, tous les jeux :

```
jeu 1 : 2224 phrases : intention exacte 100.0 %, paramètres exacts 100.0 % ; hors catalogue 332/332 « pas compris » (0 action, 0 refus ou négation) ; sensibles confirmées 85/85
jeu 2 : 327 phrases : intention exacte 100.0 %, paramètres exacts 100.0 % ; hors catalogue 50/50 « pas compris » (0 action, 0 refus ou négation) ; sensibles confirmées 8/8
jeu 3 : 465 phrases : intention exacte 100.0 %, paramètres exacts 100.0 % ; hors catalogue 56/56 « pas compris » (0 action, 0 refus ou négation) ; sensibles confirmées 16/16
jeu 4 : 405 phrases : intention exacte 99.0 %, paramètres exacts 100.0 % ; hors catalogue 58/59 « pas compris » (0 action, 1 refus ou négation) ; sensibles confirmées 14/14
jeu 5 : 408 phrases : intention exacte 99.5 %, paramètres exacts 100.0 % ; hors catalogue 60/60 « pas compris » (0 action, 0 refus ou négation) ; sensibles confirmées 15/15
jeu 6 : 371 phrases : intention exacte 100.0 %, paramètres exacts 100.0 % ; hors catalogue 60/60 « pas compris » (0 action, 0 refus ou négation) ; sensibles confirmées 12/12
jeu 7 : 416 phrases : intention exacte 99.0 %, paramètres exacts 99.8 % ; hors catalogue 60/60 « pas compris » (0 action, 0 refus ou négation) ; sensibles confirmées 12/12
jeu 8 : 413 phrases : intention exacte 98.3 %, paramètres exacts 100.0 % ; hors catalogue 60/60 « pas compris » (0 action, 0 refus ou négation) ; sensibles confirmées 11/11
```

- **Mesure anti-triche (premiers passages, sortie réelle, non retouchée)** — le seuil de 95 % n'est **pas** atteint sur
  des ordres jamais vus ; le détail et la décision sont dans D-13 :

```
jeu 2 (13/10, avant la généralisation)  : 327 ordres, intention exacte 70.6 %
jeu 3 (13/10 20:15 UTC)                 : 463 phrases : intention exacte 91.8 %, paramètres exacts 99.3 % ; hors catalogue 56/58 « pas compris » (2 action) ; sensibles confirmées 15/16
jeu 4 (hostile, 13/10 20:22 UTC)        : 405 phrases : intention exacte 65.7 %, paramètres exacts 98.5 % ; hors catalogue 58/59 « pas compris » (1 action) ; sensibles confirmées 9/14
jeu 5 (hostile, 13/10 21:32 UTC)        : 408 phrases : intention exacte 89.7 %, paramètres exacts 99.5 % ; hors catalogue 59/60 « pas compris » (1 action, 0 refus ou négation) ; sensibles confirmées 14/15
jeu 6 (représentatif, 13/10 21:37 UTC)  : 371 phrases : intention exacte 98.1 %, paramètres exacts 100.0 % ; hors catalogue 59/60 « pas compris » (1 action, 0 refus ou négation) ; sensibles confirmées 12/12
  dont ordres jamais vus                : 158 neufs ; ratés au 1er passage parmi eux : 7 -> 95.6 %
jeu 7 (416 jamais vus, 13/10 21:43 UTC) : 416 phrases : intention exacte 89.2 %, paramètres exacts 99.5 % ; hors catalogue 58/60 « pas compris » (2 action, 0 refus ou négation) ; sensibles confirmées 11/12
jeu 8 (413 jamais vus, 13/10 21:51 UTC) : 413 phrases : intention exacte 86.4 %, paramètres exacts 98.9 % ; hors catalogue 56/60 « pas compris » (4 action, 0 refus ou négation) ; sensibles confirmées 11/11
```

- `./check.sh` :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 853 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 6 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ swift build -c release
controles-core : 2 réussi(s), 0 échec(s)
  ✅ swift : contrôles du Core (sans XCTest)
	 Executed 2 tests, with 0 failures (0 unexpected) in 0.002 (0.002) seconds
  ✅ swift test (XCTest)
All checks passed!
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
25 passed in 0.16s
  ✅ socle (unitaires)
214 passed in 38.39s
  ✅ compréhension : grammaire et corpus de phrases (§9.1)
  ✅ actions, annulation, confirmation (§9.3)
  ✅ sécurité : injection, recherche automatisée (§9.3)
  ✅ intégration : moteur, socket, démon
15 passed in 3.78s
  ✅ gardien d'intégrité
TOTAL                         1883     23    99%
  ✅ couverture ≥ 90 % sur voix/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 853 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 6 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```
