# Avancement — Détecteur de corvées répétées

Reprise après coupure : lire ce fichier et `DECISIONS.md`, puis reprendre à « Prochaine étape ».
Porte unique : `modules/corvees/check.sh` (dans le conteneur : `PYTHON=<venv>/bin/python modules/corvees/check.sh`).

| Phase | Statut | Preuve |
|---|---|---|
| P0 Reconnaissance, squelette, check.sh | ✅ | ci-dessous |

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

**Prochaine étape :** P1 — modèle de données, configuration, vie privée (tests d'abord).
