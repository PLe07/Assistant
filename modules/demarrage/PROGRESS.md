# Avancement — Nettoyeur de démarrage

Reprise après coupure : lire ce fichier et `DECISIONS.md`, puis reprendre à « Prochaine étape ».
Porte unique : `modules/demarrage/check.sh` (dans le conteneur : `PYTHON=<venv>/bin/python modules/demarrage/check.sh`).

| Phase | Statut | Preuve |
|---|---|---|
| P0 Reconnaissance, squelette, check.sh | ✅ | ci-dessous |
| P1 Modèle, plists, collecteurs S1-S4 + S6, signatures | ✅ | 118 tests, couverture 98 % |
| P2 Faux Mac + vérité terrain | ✅ | 36 éléments plantés, tous trouvés |
| P3 Collecteurs S5, S7-S10, modes dégradés | ✅ | 156 tests, couverture 98,4 % |
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

## P2 — Faux Mac et vérité terrain (✅)

`tests/demarrage/faux_mac/construire.py` construit une racine « / » simulée :
- 18 éléments Apple (S3), dont Spotlight très gourmand à l'ouverture de session (il doit rester 🍎) ;
- les cas du §9.2 :
  - lourd processeur (Adobe CC, global) ;
  - lourd mémoire (Docker, via un processus fils de 1,5 Go) ;
  - empêche la veille ;
  - KeepAlive en boucle (412 lancements, code 1) ;
  - 2 orphelins (programme disparu ; app désinstallée selon AssociatedBundleIdentifiers) ;
  - Google Updater d'un Chrome pas ouvert depuis 90 jours (plist binaire) ;
  - utile et léger ;
  - inconnu non signé ;
  - faux « com.apple » non signé ;
  - plist corrompu ;
  - accents et espaces ;
  - doublon S1/S2 ;
  - « c'est moi » ;
  - daemon global ;
  - daemon embarqué inactif ;
- les sorties de commandes. Celles qui suivent l'horloge simulée (`ps`, `top`, `pmset`) donnent le temps
  processeur cumulé exact de chaque processus, selon son profil de charge.

Chaque élément planté porte son attendu (verdict, action, empêche la veille, un des 3 plus lourds). Le scan le
trouve avec les bons attributs : `tests/demarrage/faux_mac/test_inventaire.py`. Les verdicts seront jugés en P5.

En chemin, un défaut corrigé : une app d'aide rangée dans `~/Library` (GoogleSoftwareUpdateAgent.app) était prise
pour l'app parente. Sa date de dernière ouverture ne dit rien de ton usage : elle est maintenant notée « app
d'aide », et seule une app rangée avec les apps compte comme parente.

```
$ PYTHON=…/venv/bin/python modules/demarrage/check.sh
▶ ruff check ✅  ▶ ruff format ✅  ▶ mypy ✅
▶ pytest + couverture ≥ 85 %   118 passed · Total coverage: 97.99%   ✅
▶ faux Mac   12 passed   ✅   ▶ sécurité ✅   ▶ performance ✅
CHECK OK
```

## P3 — Collecteurs S5, S7 à S10, modes dégradés (✅)

- S5 `ouverture_session.py` : `sfltool dumpbtm` (fiches + état des agents connus) → System Events (10 s,
  autorisation refusée détectée) → déduction (apps lancées par launchd dans les 2 min). D-16.
- S7 `extensions.py` (tabulations ou espaces), S8 `helpers.py` (lancé par quel daemon ? sinon `sans_plist`),
  S9 `planifie.py` (crontab, raccourcis @reboot…, ligne jamais gardée), S10 `shell.py` (causes de lenteur sans le
  texte des lignes). D-17, D-18.
- Faux Mac n° 1 complété : 2 apps d'ouverture (dont une désinstallée), 1 extension, 2 assistants (dont un sans
  daemon), 2 tâches cron (dont une au programme disparu). Le scan les trouve tous ; S5 « dégradé » avec la raison.
- Défaut du faux Mac corrigé : une réponse au même préfixe remplace maintenant l'ancienne.

```
$ PYTHON=…/venv/bin/python modules/demarrage/check.sh
▶ ruff check ✅  ▶ ruff format ✅  ▶ mypy ✅
▶ pytest + couverture ≥ 85 %   134 passed · Total coverage: 98.39%   ✅
▶ faux Mac   12 passed   ✅   ▶ sécurité   9 passed   ✅   ▶ performance   1 passed   ✅
CHECK OK
```

## Prochaine étape

P4 : la mesure. Analyse de ps/top/pmset, échantillonneur (session toutes les 5 s pendant 5 min, croisière toutes
les 2 min, énergie toutes les 10 min), temps d'ouverture de session et « temps jusqu'au calme », rattachement
processus → élément, chronométrage de zsh (+ zprof isolé).
