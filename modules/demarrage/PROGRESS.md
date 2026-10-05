# Avancement — Nettoyeur de démarrage

Reprise après coupure : lire ce fichier et `DECISIONS.md`, puis reprendre à « Prochaine étape ».
Porte unique : `modules/demarrage/check.sh` (dans le conteneur : `PYTHON=<venv>/bin/python modules/demarrage/check.sh`).

| Phase | Statut | Preuve |
|---|---|---|
| P0 Reconnaissance, squelette, check.sh | ✅ | ci-dessous |
| P1 Modèle, plists, collecteurs S1-S4 + S6, signatures | ✅ | 118 tests, couverture 98 % |
| P2 Faux Mac + vérité terrain | ✅ | 36 éléments plantés, tous trouvés |
| P3 Collecteurs S5, S7-S10, modes dégradés | ✅ | 156 tests, couverture 98,4 % |
| P4 Mesure (session, croisière, énergie, veille, zsh) | ✅ | secondes de processeur exactes sur le faux Mac ; 16 ms par relevé |
| P5 Scores, verdicts, connaissances, gains | ✅ | faux Mac n° 1 : 100 % ; 2e faux Mac : 5/5 graines à 100 % |
| P6 Actions réversibles + sécurité | ✅ | 12 tests d'actions, 18 tests de sécurité |
| P7 Rapport HTML, CLI, notifications, surveillance | ✅ | 311 tests ; rapport vérifié en clair, sombre et sur mobile |
| P8 Bout en bout, performance | ✅ conteneur · ⏳ Mac | démon réel 10 min : 0,17 % de processeur, 22,8 Mo |
| P9 Installation | ⏳ Mac | lancé par le superviseur de l'Assistant (D-03) |
| P10 Revue hostile | ✅ | 6 défauts trouvés et corrigés, chacun avec son test |
| P11 Diagnostic réel sur le Mac | ⏳ Mac | ACTIONS_HUMAINES § 5 |

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

## P4 — Mesure (✅)

- `mesure/echantillonneur.py` : analyse de ps (temps cumulé `time`, `etime`, chemins avec espaces), relevé par
  élément (D-20), modes session (5 s pendant 5 min), croisière, mesure ponctuelle, disque plein signalé une fois.
- `mesure/energie.py` (top lu par la droite, 2e relevé), `mesure/veille.py` (pmset, « on behalf of »),
  `mesure/rattachement.py` (D-21), `mesure/session.py` (boottime, last, journal, calme ; D-19),
  `mesure/zsh.py` (médiane de 5, zprof isolé ; D-22).
- `db.py` : relevés, mesures par élément, sessions, agrégats après 60 jours, historique zsh.
- Sur le faux Mac n° 1, les secondes de processeur des 5 premières minutes de chaque élément planté sont exactes
  (écart < 0,1 s), y compris les processus fils. Le temps jusqu'au calme est égal à celui recalculé à partir des
  processus simulés eux-mêmes.
- Avec le vrai zsh du conteneur, zprof trouve la fonction lente, et le `.zshrc` n'est pas modifié.
- Coût réel d'un relevé (vrai ps de cette machine) :

```
$ pytest -s tests/demarrage/perf/test_echantillonneur.py
   relevé : 16.2 ms de processeur, 0.35 s pour 20 ; pic mémoire Python 0.12 Mo ; moyenne projetée sur 24 h : 0.015 %
```

(La mesure du démon pendant 10 minutes sur le vrai Mac, avec launchctl, pmset et top, est en P8.)

```
$ PYTHON=…/venv/bin/python modules/demarrage/check.sh
▶ ruff check ✅  ▶ ruff format ✅  ▶ mypy ✅
▶ pytest + couverture ≥ 85 %   172 passed · Total coverage: 98.7 %   ✅
▶ faux Mac   16 passed   ✅   ▶ sécurité   9 passed   ✅   ▶ performance   2 passed   ✅
CHECK OK
```

## P5 — Scores, verdicts, connaissances, gains (✅)

- `analyse/scores.py` : métriques depuis la base, score d'impact pondéré + bonus veille/boucle, utilité (D-26).
- `analyse/verdicts.py` : 8 règles dans l'ordre de la config, chacune testée seule (cas positifs et négatifs),
  garde-fous Apple / inconnu, action selon la source (D-23 à D-25).
- `analyse/connaissances.json` : 82 entrées en français (tous les logiciels demandés au §5), rangées du plus
  précis au plus général (D-27) ; `analyse/connaissances.py`.
- `analyse/gains.py`, `analyse/__init__.py` (classement, résumé, éditeur affiché, impact estimé).
- Juge du §9.2 (`tests/demarrage/faux_mac/juge.py`) : scan à la connexion, 5 min d'ouverture de session,
  30 min de croisière, analyse, puis comparaison à la vérité terrain. Critères : 100 % des éléments plantés avec
  le bon verdict et la bonne action, 0 Apple avec une action, 0 inconnu autre que « vérifier », les 3 plus lourds
  en tête, pas de plantage sur un plist corrompu.

Faux Mac n° 1 (éléments non Apple ; les 18 éléments Apple sont tous 🍎 sans action) :

```
   ✅ com.docker.socket                        inutile   desactiver    impact  97.0
   ✅ com.adobe.AdobeCreativeCloud             inutile   instructions  impact  85.6
   ✅ com.sauvegarde.express.agent             inutile   desactiver    impact  65.1
   ✅ com.radioboucle.helper                   inutile   desactiver    impact  32.9
   ✅ us.zoom.xos                              utile     reglages      impact  20.8
   ✅ com.notesrapides.agent                   utile     desactiver    impact   4.9
   ✅ com.assistant.superviseur                utile     aucune        impact   2.7
   ✅ com.google.keystone.agent                inutile   desactiver    impact   2.4
   ✅ com.spotify.webhelper                    orphelin  quarantaine   impact   2.3
   ✅ com.mystere.agent                        inconnu   verifier      impact   1.2
   ✅ com.apple.mise-a-jour                    inconnu   verifier      impact   1.1
   ✅ com.exemple.desinstalle.agent            orphelin  quarantaine   impact   0.0
   ✅ com.exemple.casse                        inconnu   verifier      impact   0.0
   ✅ com.exemple.Étiquette avec espaces       utile     aucune        impact   0.0
   ✅ com.exemple.doublon                      utile     desactiver    impact   0.0
   ✅ com.exemple.doublon                      utile     instructions  impact   0.0
   ✅ com.exemple.vpn.daemon                   utile     instructions  impact   0.0
   ✅ us.zoom.ZoomDaemon                       utile     aucune        impact   0.0
   ✅ Ancienne App                             orphelin  reglages      impact   0.0
   ✅ com.exemple.vpn.tunnel                   utile     instructions  impact   0.0
   ✅ com.exemple.vpn.daemon                   utile     instructions  impact   0.0
   ✅ com.ancien.helper                        orphelin  instructions  impact   0.0
   ✅ cron : sauvegarde.sh                     inconnu   verifier      impact   0.0
   ✅ cron : absent                            orphelin  instructions  impact   0.0
   graine 3 : 53/53 verdicts justes (17 plantés, 36 Apple)
   graine 17 : 54/54 verdicts justes (17 plantés, 37 Apple)
   graine 42 : 50/50 verdicts justes (17 plantés, 33 Apple)
   graine 1789 : 50/50 verdicts justes (18 plantés, 32 Apple)
   graine 20261005 : 44/44 verdicts justes (20 plantés, 24 Apple)
6 passed in 1.42s
```

Le seul écart rencontré pendant le réglage : un daemon embarqué déjà inactif recevait encore des
« instructions ». L'action d'un élément inactif passe maintenant avant celle de sa source.
Le 2e faux Mac (aléatoire, 5 graines) a été écrit après ce réglage et a réussi du premier coup.

```
$ PYTHON=…/venv/bin/python modules/demarrage/check.sh
▶ ruff check ✅  ▶ ruff format ✅  ▶ mypy ✅
▶ pytest + couverture ≥ 85 %   220 passed · Total coverage: 98.66%   ✅
▶ faux Mac (+ 2e faux Mac, 5 graines)   22 passed   ✅   ▶ sécurité   9 passed   ✅   ▶ performance   2 passed   ✅
CHECK OK
```

## P6 — Actions réversibles et sécurité (✅)

- `actions/desactiver.py` : plan en lecture seule (`est_lecture`), `--confirmer` pour agir, vérification après,
  journal (D-28).
- `actions/restaurer.py` : défait exactement l'action notée, idempotent (D-29).
- `actions/quarantaine.py` : déplacement + manifeste + empreinte, retour refusé si écrasement ou modification
  (D-30).
- `actions/journal.py` (avant, après, commandes, détails, annulée), `actions/instructions.py` (le seul fichier où
  « sudo » existe, en texte).
- Faux Mac : un launchd et un System Events simulés qui se souviennent (`faux_mac/launchd_simule.py`).
- Prouvé par les tests :
  - désactiver → arrêté et désactivé → restaurer → rechargé et réactivé ;
  - deuxième désactivation : « rien à faire » ;
  - réactivé à la main : restaurer le note sans rien refaire ;
  - quarantaine aller-retour, octet pour octet ;
  - échec partiel noté puis défait ;
  - élément d'ouverture retiré puis remis ; sans autorisation : le chemin des Réglages.
- Sécurité (§9.4), sur le faux Mac n° 1 et sur un faux Mac aléatoire :
  - simulation de desactiver + restaurer sur chaque élément : 0 commande de modification, 0 fichier touché ;
  - 🍎 : toujours refusé, même avec `--confirmer` ;
  - global : instructions seules ;
  - inconnu : « vérifier » seulement ;
  - sur le vrai `Mac`, `subprocess.run` intercepté : la simulation ne lance que de la lecture, et Apple et les
    éléments globaux rien du tout ;
  - aucune commande `sudo` lancée, et la fouille du code est toujours vide.

```
$ PYTHON=…/venv/bin/python modules/demarrage/check.sh
▶ ruff check ✅  ▶ ruff format ✅  ▶ mypy ✅
▶ pytest + couverture ≥ 85 %   232 passed · Total coverage: 98.60%   ✅
▶ faux Mac (+ 2e faux Mac, 5 graines)   22 passed   ✅   ▶ sécurité   18 passed   ✅   ▶ performance   2 passed   ✅
CHECK OK
```

## P7 — Rapport, CLI, notifications, surveillance (✅)

- `rapport.py` : résumé (« N éléments se lancent tout seuls… te coûtent vraiment… »), gain si tu coupes 💤/👻,
  courbe des ouvertures de session (D-32), classement en fiches (éditeur, type, rôle, mesures, dernière ouverture
  de l'app, verdict, commandes pour agir et annuler), macOS replié, bonus zsh, état des collecteurs.
  Démonstration : `modules/demarrage/demo/rapport_demo.html` (faux Mac n° 1).
- `cli.py` : scan, mesurer, rapport, desactiver, restaurer, historique, surveiller, doctor ; identifiant complet,
  début d'identifiant ou label.
- `notifier.py` (D-34), `daemon.py` + `module.py` (D-35), `travail.py` (opérations partagées) ;
  `python assistant.py etat` affiche la ligne 🧹.
- Défauts trouvés en regardant le rendu, puis corrigés :
  - la médiane des sessions comptait les sessions non observées (D-33) ;
  - les graduations de la courbe étaient rognées et mélangeaient secondes et minutes ;
  - un long chemin faisait déborder la page sur mobile ;
  - une marge était écrasée dans les fiches ;
  - zsh en erreur était chronométré comme un succès ;
  - un test avait une assertion molle (`or True`) : elle est remplacée par une vraie vérification.
- En mode dégradé (ce conteneur Linux : ni launchctl, ni sfltool…), scan, mesurer, rapport et doctor tournent
  sans planter, et doctor dit ce qui manque.

```
$ PYTHON=…/venv/bin/python modules/demarrage/check.sh
▶ ruff check ✅  ▶ ruff format ✅  ▶ mypy ✅
▶ pytest + couverture ≥ 85 %   259 passed · Total coverage: 98.09%   ✅
▶ faux Mac (+ 2e faux Mac, 5 graines)   30 passed   ✅   ▶ sécurité   18 passed   ✅   ▶ performance   2 passed   ✅
CHECK OK
```

## P8 — Bout en bout et performance (✅ conteneur · ⏳ Mac)

- `tests/demarrage/e2e_mac/test_bout_en_bout_mac.py`, à lancer sur le Mac (ACTIONS_HUMAINES § 2). Il :
  - crée `com.assistant.nettoyeur.test.charge` (environ 25 % d'un cœur sous nice, avec un caffeinate fils, arrêt
    tout seul en 4 min) et `…test.orphelin` (programme inexistant, jamais chargé) ;
  - fait un scan, puis un scan avec le cache, et vérifie les temps (< 15 s, puis < 5 s) ;
  - lance `mesurer --minutes 3`, puis vérifie : l'agent de charge en tête et « empêche la veille », l'orphelin 👻 ;
  - lance `desactiver --confirmer` (vérifie : arrêté et désactivé), puis `restaurer` (vérifie : réactivé et
    rechargé) ;
  - nettoie dans un `finally` (bootout, enable, plists effacés, PID tués) ;
  - cherche automatiquement les traces : fichiers, launchd, désactivations, processus.
- Défauts trouvés en le préparant, puis corrigés :
  - les enveloppes `nice`, `env`… masquaient le vrai programme (D-36) ;
  - un ⚠️ ne pouvait pas être arrêté, même sur ta commande (D-37) ;
  - un label de test était pris pour « c'est moi » (D-38).
- `tests/demarrage/e2e_mac/mesure_demon.py` : le vrai démon N secondes, processus fils compris (D-39).
- `tests/demarrage/perf/test_scan.py` : gros faux Mac, codesign à 80 ms ; scan à froid puis avec le cache.

```
relevé : 16.6 ms de processeur, 0.36 s pour 20 ; pic mémoire Python 0.13 Mo ; moyenne projetée sur 24 h : 0.015 %
1070 éléments · 1er scan 2.2 s (170 codesign à 80 ms, en parallèle) · avec le cache 0.4 s
{'duree_s': 601, 'cpu_s': 1.01, 'cpu_moyen_pct': 0.168, 'ram_max_mo': 22.8}
✅ dans les budgets
```

## P9 — Installation (⏳ Mac)

La surveillance est le module `demarrage` de l'Assistant (D-03). `demarrage surveiller on`, puis le superviseur
(`com.assistant.superviseur`, RunAtLoad + KeepAlive + ThrottleInterval, installé par `python service.py installer`)
la lance et la relance. Vérifié dans le conteneur :
- `daemon.boucle` sous un faux contexte du superviseur : battement écrit, état « vivant » ;
- un tour en panne ne fait pas tomber le module ;
- une base illisible en route est rouverte.
Sur le Mac (ACTIONS_HUMAINES § 3) : `launchctl print gui/$(id -u)/com.assistant.superviseur`, `kill -9` du module,
puis relance dans la minute, et `doctor`.

## P10 — Revue hostile (✅)

Relecture « pour le casser ». Six défauts réels ont été trouvés et corrigés, chacun avec son test
(`unitaires/test_revue_hostile.py`), détail dans D-40 :
- un antivirus jamais ouvert pouvait passer 💤 ;
- un disque externe débranché pouvait être pris pour un orphelin ;
- `~` dans un chemin n'était pas déplié ;
- un `launchctl` muet faisait tout déclarer « pas chargé » ;
- le démon semblait mort pendant le suivi de l'ouverture de session ;
- un `caffeinate` du test réel pouvait survivre au nettoyage.
Deux vérifications ont maintenant leur test :
- le changement d'heure du 25 octobre ;
- un élément Apple lourd reste 🍎, sans action.
Ajout : `demarrage top`, le top 10 en Markdown sans chemin personnel (D-41).

```
▶ ruff check
All checks passed!
  ✅ ruff check
▶ ruff format
118 files already formatted
  ✅ ruff format
▶ mypy
Success: no issues found in 50 source files
  ✅ mypy
▶ pytest + couverture ≥ 85 %
Required test coverage of 85.0% reached. Total coverage: 97.99%
272 passed in 13.30s
  ✅ pytest + couverture ≥ 85 %
▶ faux Mac (+ 2e faux Mac, 5 graines)
30 passed in 2.28s
  ✅ faux Mac (+ 2e faux Mac, 5 graines)
▶ sécurité
18 passed in 2.13s
  ✅ sécurité
▶ performance
3 passed in 4.90s
  ✅ performance
CHECK OK
```

## P11 — Diagnostic réel (⏳ Mac)

Les commandes sont dans ACTIONS_HUMAINES § 5 : `scan`, `mesurer --minutes 10`, `rapport`, `top`. La sortie de `top`
ira dans RAPPORT_FINAL.md § 5.

## Prochaine étape

Sur le Mac : ACTIONS_HUMAINES § 1 à § 3 et § 5. Ensuite, RAPPORT_FINAL.md § 4 et § 5 seront complétés avec les
vraies sorties.
