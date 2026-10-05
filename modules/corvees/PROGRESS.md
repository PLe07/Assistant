# Avancement — Détecteur de corvées répétées

Reprise après coupure : lire ce fichier et `DECISIONS.md`, puis reprendre à « Prochaine étape ».
Porte unique : `modules/corvees/check.sh` (dans le conteneur : `PYTHON=<venv>/bin/python modules/corvees/check.sh`).

| Phase | Statut | Preuve |
|---|---|---|
| P0 Reconnaissance, squelette, check.sh | ✅ | ci-dessous |
| P1 Données, config, vie privée | ✅ | 112 tests, couverture 99 % |
| P2 Normalisation + simulateur de vie | ✅ | 6 tests du simulateur |

## P0 — Reconnaissance (✅)

- Environnement de construction : conteneur Linux x86_64, Python 3.11.15, git ; pas de zsh ni de shellcheck
  (voir D-04). Mac cible : Apple Silicon, venv Python 3.14.
- Projet de l'assistant trouvé : ce dépôt (module de tri Gmail `modules/mails`). Intégration : D-01 à D-09.
- Squelette : `modules/corvees/` (capteurs/, detection/), `tests/corvees/` (unitaires, simulation, e2e, vie_privee,
  perf), `pyproject.toml` (outils), `requirements-dev.txt`, `corvees.py`.

```
$ modules/corvees/check.sh
▶ ruff check            ✅   ▶ ruff format   ✅   ▶ mypy   ✅
▶ pytest + couverture ≥ 85 %   4 passed · Total coverage: 100.00%   ✅
▶ simulation   ✅   ▶ performance   ✅
CHECK OK
```

## P1 — Données, configuration, vie privée (✅)

- `config.py` : toutes les valeurs par défaut et tous les seuils ; reglages.json → modules.corvees, fusion en
  profondeur ; une valeur de mauvais type est remplacée et signalée.
- `privacy.py` : caviardage (e-mails, téléphones FR, IBAN avec contrôle mod 97, cartes avec Luhn, clés sk-/sk-ant-/
  ghp_/AKIA…, JWT, Bearer, hexadécimal ≥ 32, base64 ≥ 40, mots de passe en ligne de commande, paramètres d'URL,
  identifiants dans les URL, clés privées) ; exclusions (applis par nom/bundle/accents, domaines, dossiers,
  titres de fenêtres sensibles) ; empreinte HMAC salée ; sel 32 octets en 600.
- `db.py` : seul chemin d'écriture = `Base.ajouter()` qui passe par le Gardien ; base en 600 ; purge → agrégats ;
  base corrompue → mise de côté + reconstruite ; disque plein → `DisquePlein`.
- `normalize.py` : heure de Paris (changements d'heure testés), motifs de noms, lieux, URL, commandes, tokens.

```
$ modules/corvees/check.sh
✅ ruff check · ✅ ruff format · ✅ mypy (9 fichiers)
112 passed · Total coverage: 99.15%
CHECK OK
```

## P2 — Simulateur de vie (✅)

`tests/corvees/simulation/generateur.py` : 28 jours (à partir d'un lundi), ~440 événements par jour de bruit
réaliste (26 applis pondérées, ~60 sites avec des chemins variables, fichiers téléchargés/rangés/renommés,
commandes, copier-coller, titres de fenêtres, inactivité), produits par la vraie normalisation.
10 corvées plantées (jeu A) avec leur vérité terrain (motifs + nombre requis), 4 pièges : Spotify seul chaque
matin, une corvée refusée (Mail → Excel), applis et sites exclus (1Password, Messages, Boursorama, impots.gouv),
7 faux secrets (mot de passe MySQL, clé sk-ant, IBAN, e-mail, téléphone, jeton GitHub, PASSWORD=).
Le 2e jeu de corvées sera écrit seulement après le réglage (P3).

```
$ modules/corvees/check.sh
✅ ruff · ✅ format · ✅ mypy · 112 passed (99.15 %) · simulation 6 passed · CHECK OK
$ densité de performance : generer(1, jours=30, densite=30) → 213 561 événements
```

**Prochaine étape :** P3 — détecteurs D1 à D5, scoring, mémoire des décisions ; itérer jusqu'aux critères §9.1.
