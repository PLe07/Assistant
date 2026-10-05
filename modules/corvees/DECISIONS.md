# Décisions — Détecteur de corvées répétées

Chaque choix ambigu, avec les alternatives écartées et la raison. Le plus récent en bas.

## 2026-10-05 · P0 — Reconnaissance

**D-01 · S'intégrer à l'Assistant existant plutôt que créer un projet séparé.**
Le projet de l'assistant existe : c'est ce dépôt (`~/Assistant` sur le Mac), dont le premier module est le tri
Gmail (`modules/mails`). Conformément au §1 de la mission (« respecte ses conventions »), le détecteur devient le
module `modules/corvees`, lancé et relancé par le superviseur de l'Assistant (`superviseur.py`, lui-même confié à
launchd par `python service.py installer`).
*Écarté :* un projet autonome `~/Projets/detecteur-corvees` avec son propre LaunchAgent. Il aurait doublé le
superviseur, la configuration, les notifications et l'accès à Claude, et le nom du LaunchAgent demandé contient un
prénom, qui ne doit pas apparaître dans ce dépôt public.

**D-02 · Emplacements : ceux de l'Assistant.**
Données : `donnees/corvees/` (base `corvees.db` en `chmod 600`, sel HMAC, rapport, propositions). Le dossier
`donnees/` n'est jamais versionné (`.gitignore`). Journal : `logs/assistant.log`, préfixe `[corvees]`, comme tous
les modules. Réglages : `reglages.json` → `modules.corvees`.
*Écarté :* `~/Library/Application Support/DetecteurCorvees/`, `~/Library/Logs/DetecteurCorvees/` et un
`config.toml`. Ils auraient créé un deuxième endroit pour les données, les journaux et les réglages.

**D-03 · Le cerveau : Claude via l'abonnement (`core.cerveau`), pas de clé API.**
L'Assistant n'a pas de clé API Anthropic : il passe par Claude Code (`claude -p`) avec le jeton de l'abonnement
stocké dans `.env`, lu au démarrage par `core.config`. launchd n'hérite pas du shell, mais ce n'est pas un problème
puisque le `.env` est lu par le programme lui-même. Le module réutilise ce canal (plafond quotidien, pause après
panne, journal des appels). Le coût est estimé en jetons × tarif (config) et le plafond mensuel de 2 $ s'applique à
cette estimation.
*Écarté :* le SDK `anthropic` avec `ANTHROPIC_API_KEY` ou le trousseau. Cela ferait une deuxième authentification
à gérer, alors que §6 demande de « réutiliser celle de l'assistant ».

**D-04 · Construit dans un conteneur Linux, pas sur le Mac.**
Cette session tourne dans un conteneur cloud (Linux x86_64, Python 3.11.15, sans `zsh` ni `shellcheck`). Le Mac
cible : MacBook Air Apple Silicon (Homebrew dans `/opt/homebrew`), venv en Python 3.14 (vu dans les sorties de
l'utilisateur). Conséquences :
- tout l'accès natif macOS (NSWorkspace, accessibilité, NSPasteboard, inactivité) est isolé dans
  `capteurs/natif.py`, derrière des interfaces simulées dans les tests ;
- les capteurs portables (fichiers via `watchdog`, historique zsh, SQLite des navigateurs) sont testés pour de vrai
  ici ;
- ce qui exige le vrai Mac (autorisations, mesure sur place) est décrit dans `ACTIONS_HUMAINES.md`, avec une
  commande prête : `python -m modules.corvees e2e`.

**D-05 · Git : le dépôt existe déjà.**
Pas de `git init`. Les commits se font sur la branche de travail, un par phase verte.

**D-06 · Désactivé par défaut, comme les autres modules qui observent.**
`yeux`, `oreilles` et `traduction` sont éteints par défaut. Le détecteur suit la même règle : il s'allume avec
`python assistant.py activer corvees`. Le superviseur le lance alors dans les 2 secondes et le relance s'il tombe.

**D-07 · Dépendances.**
Ajoutées au fonctionnement : `watchdog` (FSEvents sur le Mac) et `jsonschema` (validation des réponses de Claude).
Outils de développement (pytest, pytest-cov, ruff, mypy) : dans `requirements-dev.txt`, jamais dans
`requirements.txt`. Tout s'installe dans le venv de l'Assistant (`.venv`).

**D-08 · La commande `corvees`.**
`python -m modules.corvees <commande>`, ou plus court `python corvees.py <commande>` à la racine, sur le modèle de
`assistant.py`. Un alias zsh `corvees` est proposé dans `ACTIONS_HUMAINES.md`, puisque le `.zshrc` ne doit pas être
modifié.

**D-09 · Tests dans le dépôt.**
`tests/corvees/` : unitaires, simulation, e2e, vie_privee, perf. La porte unique est `modules/corvees/check.sh`.
La configuration des outils (ruff, mypy, pytest, coverage) est dans `pyproject.toml` à la racine, limitée au module.
