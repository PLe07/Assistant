# Avancement — Trieur unifié

| Phase | Statut | Preuve |
|---|---|---|
| P0 Reconnaissance, squelette, check.sh | ✅ | ci-dessous |
| P1 Corpus + vérité terrain | ⏳ | |
| P2 Extraction | ⏳ | |
| P3 Classement, champs, nommage | ⏳ | |
| P4 File, doublons, déplacement sûr, annulation, apprentissage | ⏳ | |
| P5 Coffre à garanties, Rappels, rétractation, pages HTML | ⏳ | |
| P6 Couche IA | ⏳ | |
| P7 Entrées, action rapide, raccourcis | ⏳ | |
| P8 Démon, notifications, doctor, CLI | ⏳ | |
| P9 Bout en bout réel, performance | ⏳ | |
| P10 Installation réelle | ⏳ | |
| P11 Revue hostile | ⏳ | |

## P0 — Reconnaissance (✅)

Voir DECISIONS.md D-01 à D-12. Squelette `modules/trieur/`, `tests/trieur/`, `trieur.py`, `check.sh`.

Les suites `corpus`, `securite` et `perf` n'ont pour l'instant qu'un test de squelette (pytest refuse une suite
vide) ; elles sont remplies en P1, P6 et P9.

```
$ PYTHON=…/venv/bin/python modules/trieur/check.sh
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
Required test coverage of 85.0% reached. Total coverage: 91.14%
  ✅ pytest + couverture ≥ 85 %
  ✅ corpus (principal + 2e corpus inédit)
  ✅ sécurité et vie privée
  ✅ performance
CHECK OK
```
