# Avancement de Voix

Chaque phase se termine par `./check.sh` vert, l'intégrité des autres projets identique, un commit, et la preuve
collée ici (sortie réelle).

| Phase | État |
|---|---|
| P0 — environnement, empreinte, squelettes, check.sh | ✅ |
| P1 — compréhension et corpus de phrases | ⏳ |
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
