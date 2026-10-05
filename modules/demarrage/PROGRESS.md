# Avancement — Nettoyeur de démarrage

Reprise après coupure : lire ce fichier et `DECISIONS.md`, puis reprendre à « Prochaine étape ».
Porte unique : `modules/demarrage/check.sh` (dans le conteneur : `PYTHON=<venv>/bin/python modules/demarrage/check.sh`).

| Phase | Statut | Preuve |
|---|---|---|
| P0 Reconnaissance, squelette, check.sh | ✅ | ci-dessous |
| P1 Modèle, plists, collecteurs S1-S4 + S6, signatures | ⏳ | |
| P2 Faux Mac + vérité terrain | ⏳ | |
| P3 Collecteurs S5, S7-S10, modes dégradés | ⏳ | |
| P4 Mesure (session, croisière, énergie, veille, zsh) | ⏳ | |
| P5 Scores, verdicts, connaissances, gains | ⏳ | |
| P6 Actions réversibles + sécurité | ⏳ | |
| P7 Rapport HTML, CLI, notifications, surveillance | ⏳ | |
| P8 Bout en bout, performance | ⏳ | |
| P9 Installation | ⏳ | |
| P10 Revue hostile | ⏳ | |
| P11 Diagnostic réel sur le Mac | ⏳ | |

## P0 — Reconnaissance (✅)

- Environnement de construction : conteneur Linux x86_64, Python 3.11, zsh présent ; aucune des commandes macOS
  (`launchctl`, `sfltool`, `codesign`, `mdls`, `pmset`, `systemextensionsctl`, `sw_vers`). Mac cible : Apple
  Silicon, macOS 26, venv Python 3.14 (D-01). `demarrage doctor` fera l'inventaire réel sur le Mac.
- Projet de l'assistant trouvé : ce dépôt (tri Gmail `modules/mails`, Détecteur de corvées `modules/corvees`).
  Intégration en module `modules/demarrage` : D-02, D-03.
- Squelette : `modules/demarrage/` (collecteurs/, mesure/, analyse/, actions/), `tests/demarrage/` (unitaires,
  faux_mac, securite, perf, e2e, fixtures), `demarrage.py`, `python assistant.py demarrage …`,
  `reglages.json → modules.demarrage` (éteint par défaut).
- `systeme.py` : la seule porte vers le Mac (D-04), refuse `sudo`/`su`/`doas` avant de lancer quoi que ce soit.
- Fixtures : 27 sorties reconstruites + 8 plists pièges dans `tests/demarrage/fixtures/formats/` (D-05) ;
  `capturer.py` + `anonymat.py` pour capturer les vraies sorties sur le Mac, anonymisées, jamais versionnées.
- Sécurité dès P0 : fouille automatique du code (pas de `sudo` hors liste, pas de shell, `subprocess` seulement
  dans `systeme.py`).

```
$ PYTHON=…/venv/bin/python modules/demarrage/check.sh
▶ ruff check   ✅   ▶ ruff format   ✅   ▶ mypy   ✅
▶ pytest + couverture ≥ 85 %   55 passed · Total coverage: 100.00%   ✅
▶ faux Mac   6 passed   ✅   ▶ sécurité   9 passed   ✅   ▶ performance   1 passed   ✅
CHECK OK
```

## Prochaine étape

P1 : `modele.py` (la fiche d'un élément), lecture robuste des plists, collecteurs S1-S4 et S6, signatures
(`codesign`, `mdls`, cache par chemin + date de modification), base SQLite.
