# Avancement — Nettoyeur de démarrage

Reprise après coupure : lire ce fichier et `DECISIONS.md`, puis reprendre à « Prochaine étape ».
Porte unique : `modules/demarrage/check.sh` (dans le conteneur : `PYTHON=<venv>/bin/python modules/demarrage/check.sh`).

| Phase | Statut | Preuve |
|---|---|---|
| P0 Reconnaissance, squelette, check.sh | ✅ | ci-dessous |
| P1 Modèle, plists, collecteurs S1-S4 + S6, signatures | ✅ | 118 tests, couverture 98 % |
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

## P1 — Modèle, collecteurs S1-S4 et S6 (✅)

- `modele.py` : la fiche normalisée du §3 (id stable = empreinte source + label), l'inventaire, les collecteurs.
- `collecteurs/plists.py` : plists XML/binaires/cassés/vides, ProgramArguments vide, KeepAlive en dictionnaire,
  BundleProgram, WorkingDirectory, interpréteurs (D-12), liens symboliques suivis sous la racine.
- S1 `agents_utilisateur.py`, S2 `agents_globaux.py`, S3 `apple.py`, S4 `apps_embarquees.py`, S6 `launchd_etat.py`
  (list, print gui, print-disabled ancien et récent, print system si lisible, print d'un service).
- `signatures.py` : codesign (Apple, Developer ID, App Store, ad hoc, non signé, invalide), cache par chemin +
  date + taille, appels en parallèle ; mdls.
- `scan.py` : chaque collecteur isolé (panne → « indisponible » ou « dégradé »), doublons, « c'est moi », app
  parente, app désinstallée ou déplacée, relances KeepAlive.
- `db.py` : SQLite 600, base corrompue mise de côté puis reconstruite, disque plein → DisquePlein.

```
$ PYTHON=…/venv/bin/python modules/demarrage/check.sh
▶ ruff check ✅  ▶ ruff format ✅  ▶ mypy ✅
▶ pytest + couverture ≥ 85 %   118 passed · Total coverage: 98.15%   ✅
▶ faux Mac ✅  ▶ sécurité ✅  ▶ performance ✅
CHECK OK
```

## Prochaine étape

P2 : `tests/demarrage/faux_mac/construire.py` : un faux Mac complet (≥ 15 éléments Apple, les cas plantés du §9.2,
les cas tordus) avec ses sorties de commandes et sa vérité terrain ; test du scan contre cette vérité.
