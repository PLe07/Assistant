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
| P8 Bout en bout, performance | ✅ bout en bout sur le Mac · ✅ budgets (de justesse, allégé ensuite : D-46) · ⏳ vérification finale | Mac : 1 passed ; scan 3,0 s puis 2,1 s ; démon 0,27 %, 39,9 Mo |
| P9 Installation | ✅ sur le Mac : allumée, relancée 7 s après un `kill -9` | lancée par le superviseur (D-03) |
| P10 Revue hostile | ✅ | 6 défauts trouvés et corrigés, chacun avec son test |
| P11 Diagnostic réel sur le Mac | ✅ 3 passages | défauts réels corrigés, chacun testé (D-42 à D-47) ; top 10 réel ci-dessous |

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

## P11 — Diagnostic réel (1er passage le 5 octobre : 7 défauts trouvés et corrigés · ⏳ 2e passage)

Premier passage sur ton Mac (ACTIONS_HUMAINES § 1, § 2 et § 5). Sorties réelles, sans chemin ni nom :

```
🩺 Nettoyeur de démarrage
   ✅ macOS 27.0.1 · arm64 · Python 3.14.4
   ✅ launchctl, ps, top, pmset, codesign, mdls, sfltool, osascript, systemextensionsctl, crontab, sysctl, last,
      log, zsh (toutes présentes)

pytest tests/demarrage/e2e_mac
🔎 933 éléments trouvés en 5.0 s (911 de macOS).
   scan : 5.1 s, puis 1.7 s avec le cache codesign                        ✅ (< 15 s, < 5 s)
✅ 36 relevés. … en tête : [l'agent de test] (impact 66) ['empêche la veille']   ✅
   orphelin de test : 👻, quarantaine                                       ✅
   desactiver --confirmer : « Commandes passées, mais launchd ne le montre pas encore désactivé. »
   assert not charge(CHARGE) → encore chargé                               ❌ → D-43
1 failed in 190.36s

mesure_demon.py 600
{'duree_s': 602, 'cpu_s': 12.46, 'cpu_moyen_pct': 2.071, 'ram_max_mo': 308.0}
❌ hors budget (CPU < 0.3 %, RAM < 40.0 Mo)                                → D-42

demarrage scan
🔎 931 éléments trouvés en 3.3 s (911 de macOS).   💤 4 · 👻 1 · ⚠️ 4 · ✅ 11
demarrage mesurer --minutes 10
✅ 117 relevés.
```

Après le test, le scan ne trouve plus les deux éléments de test (933 → 931) : le nettoyage du `finally` a bien
eu lieu. En revanche, la recherche automatique des traces n'a pas tourné, car le test s'est arrêté avant. Le 2e
passage la refera.

`demarrage top` (avant les corrections) :

| # | Élément | Éditeur | Impact | Coût mesuré | Verdict | Désactiver | Restaurer |
|---|---|---|---|---|---|---|---|
| 1 | Spotify | Spotify | 42 | 5,1 % d'un cœur · 968 Mo | ✅ Utile, à garder | `demarrage desactiver b8e39d87 --confirmer` | `demarrage restaurer b8e39d87 --confirmer` |
| 2 | L'Assistant (c'est moi) | inconnu | 12 | 1,5 % d'un cœur · 144 Mo | ✅ Utile, à garder | — | — |
| 3 | L'Assistant (c'est moi) | inconnu | 8 | 1,3 % d'un cœur · 45 Mo | ✅ Utile, à garder | — | — |
| 4 | Google Updater (Keystone) | Google LLC | 3 (estimé) | — | 👻 Orphelin (reste d'une app désinstallée) | `demarrage desactiver cf0af4b1 --confirmer` | `demarrage restaurer cf0af4b1 --confirmer` |
| 5 | Google Updater (Keystone) | inconnu | 3 (estimé) | — | ⚠️ Inconnu, à vérifier | `demarrage desactiver ebf8a226 --confirmer` | `demarrage restaurer ebf8a226 --confirmer` |
| 6 | Google Updater (Keystone) | inconnu | 3 (estimé) | — | ⚠️ Inconnu, à vérifier | `demarrage desactiver 14140c57 --confirmer` | `demarrage restaurer 14140c57 --confirmer` |
| 7 | Mise à jour de Zoom | Zoom Video Communications, Inc. | 3 (estimé) | — | 💤 Inutile au démarrage | à taper soi-même : `demarrage desactiver d14a1655` les affiche | idem |
| 8 | Mise à jour de Zoom | Zoom Video Communications, Inc. | 3 (estimé) | — | 💤 Inutile au démarrage | à taper soi-même : `demarrage desactiver e77d2aff` les affiche | idem |
| 9 | Mise à jour de Zoom | Zoom Video Communications, Inc. | 3 (estimé) | — | 💤 Inutile au démarrage | à taper soi-même : `demarrage desactiver efb58e77` les affiche | idem |
| 10 | Mise à jour de Zoom | Zoom Video Communications, Inc. | 3 (estimé) | — | 💤 Inutile au démarrage | à taper soi-même : `demarrage desactiver 48502476` les affiche | idem |

Les défauts, leurs corrections et leurs tests :

| Vu sur ton Mac | Cause | Correction | Test |
|---|---|---|---|
| Démon : 2,07 % de processeur, 308 Mo | `log show --last boot` : tout le journal depuis le démarrage | journal lu sur 7 min au plus ; coût de chaque commande noté et affiché (D-42) | `test_session`, `test_systeme`, `test_demon` |
| `desactiver` : encore chargé juste après | launchd rend la main avant la fin de l'arrêt (code 36 possible) | `disable` puis `bootout`, attente jusqu'à 10 s, message précis, `print-disabled` lu avec tolérance (D-43) | `test_launchd_qui_arrete_avec_retard` (codes 0 et 36), `test_desactives_format_inattendu` |
| L'agent de test nommé « L'Assistant (c'est moi) » | motif `com\.assistant\.` de la base | motif sans les éléments de test, entrée « assistant » réservée à l'Assistant (D-44) | `test_diagnostic_reel` |
| 4 × « Mise à jour de Zoom », 2 × « L'Assistant », 3 × « Google Updater » | noms identiques | « · label », ou « · d'où il vient » (D-44) | `test_diagnostic_reel` |
| Spotify (968 Mo, 5 % d'un cœur) ✅ « ouvert il y a moins d'un jour » | une app ouverte à la connexion paraît toujours utilisée | règle `pas_au_demarrage` ; utilité « inconnue » pour une app ouverte à la connexion (D-45) | `test_diagnostic_reel` |
| 2 fichiers Google « pas de Label » classés 5e et 6e (impact 3 estimé) | estimation de la base pour un fichier qui ne lance rien | impact 0 et raison claire ; `plutil -p` proposé pour le reconnaître (D-45) | `test_diagnostic_reel` |
| « environ 0 Mo de mémoire libérée, 0,0 s » | phrase écrite même sans rien de mesuré | seulement ce qui est mesuré, sinon « pas de gain mesuré pour l'instant » (D-45) | `test_diagnostic_reel` |

Le faux Mac n° 1 et le 2e faux Mac (5 graines) restent à 100 %.

### 2e passage (5 octobre au soir), avec D-42 à D-45

```
pytest tests/demarrage/e2e_mac
🔎 934 éléments trouvés en 2.9 s (911 de macOS).
   scan : 3.0 s, puis 2.1 s avec le cache codesign                         ✅
   en tête : com.assistant.nettoyeur.test.charge (impact 65) ['empêche la veille']   ✅ (plus « L'Assistant »)
   desactiver --confirmer : ✅ C'est fait.                                   ✅ (D-43)
   restaurer --confirmer  : ✅ C'est restauré : launchctl enable … ; launchctl bootstrap …
1 passed in 190.26s                                                        ✅ traces : aucune

mesure_demon.py 600
{'duree_s': 602, 'cpu_s': 1.65, 'cpu_moyen_pct': 0.274, 'ram_max_mo': 39.9}
   dont Python lui-même ≈ 0.79 s ; top 1 fois 0.31 s ; log 1 fois 0.27 s (7 min de journal) ; ps 6 fois 0.22 s ;
   pmset 5 fois 0.03 s ; launchctl list 5 fois 0.02 s ; last 0.01 s
✅ dans les budgets                                                         (de justesse : 39,9 / 40 Mo → D-46)

surveiller on ; service.py redemarrer ; kill -9 ; 70 s
   🧹 Démarrage : surveille · 0 ouverture(s) mesurée(s)   (avant et après le kill : non probant → D-46)
```

`demarrage top` (avec D-44 et D-45, sur les mesures du 1er passage) :

| # | Élément | Éditeur | Impact | Coût mesuré | Verdict | Désactiver | Restaurer |
|---|---|---|---|---|---|---|---|
| 1 | Spotify · com.spotify.client.startuphelper | Spotify | 42 | 5,1 % d'un cœur · 968 Mo | 💤 Inutile au démarrage | `demarrage desactiver b8e39d87 --confirmer` | `demarrage restaurer b8e39d87 --confirmer` |
| 2 | L'Assistant (c'est moi) · com.assistant.superviseur | inconnu | 12 | 1,5 % d'un cœur · 144 Mo | ✅ Utile, à garder | — | — |
| 3 | L'Assistant (c'est moi) · com.assistant.icone | inconnu | 8 | 1,3 % d'un cœur · 45 Mo | ✅ Utile, à garder | — | — |
| 4 | Google Updater (Keystone) · com.google.GoogleUpdater.wake | Google LLC | 3 (estimé) | — | 👻 Orphelin (reste d'une app désinstallée) | `demarrage desactiver cf0af4b1 --confirmer` | `demarrage restaurer cf0af4b1 --confirmer` |
| 5 | Mise à jour de Zoom · /Library/LaunchDaemons (système, administrateur) | Zoom Video Communications, Inc. | 3 (estimé) | — | 💤 Inutile au démarrage | à taper soi-même : `demarrage desactiver efb58e77` les affiche | idem |
| 6 | Mise à jour de Zoom · /Library/PrivilegedHelperTools (administrateur) | Zoom Video Communications, Inc. | 3 (estimé) | — | 💤 Inutile au démarrage | à taper soi-même : `demarrage desactiver 48502476` les affiche | idem |
| 7 | Mise à jour de Zoom · us.zoom.updater | Zoom Video Communications, Inc. | 3 (estimé) | — | 💤 Inutile au démarrage | à taper soi-même : `demarrage desactiver e77d2aff` les affiche | idem |
| 8 | Mise à jour de Zoom · us.zoom.updater.login.check | Zoom Video Communications, Inc. | 3 (estimé) | — | 💤 Inutile au démarrage | à taper soi-même : `demarrage desactiver d14a1655` les affiche | idem |
| 9 | com.jarvis.agent | inconnu | 1 | 0,2 % d'un cœur · 9 Mo | ⚠️ Inconnu, à vérifier | `demarrage desactiver 511c9b36 --confirmer` | `demarrage restaurer 511c9b36 --confirmer` |
| 10 | com.apphousekitchen.aldente-pro.helper · /Library/LaunchDaemons (système, administrateur) | AppHouseKitchen GmbH | 1 | 0,1 % d'un cœur · 5 Mo | ✅ Utile, à garder | à taper soi-même : `demarrage desactiver e7fee7ff` les affiche | idem |

`Si tu coupes les 6 éléments 💤 et 👻 : environ 968 Mo de mémoire libérée.`

Vu pendant le test (base temporaire) : `com.anthropic.claudefordesktop.ShipIt`, impact 45, ⚠️ « éditeur inconnu ».
C'est la mise à jour de l'app Claude qui s'installait à ce moment-là : passagère, elle n'apparaît pas dans le top
de ta vraie base. Elle est ⚠️ parce que sa signature n'a pas pu être lue pendant qu'elle tournait.

Les deux fichiers Google « sans Label » sont `com.google.keystone.agent.plist` et `com.google.keystone.xpcservice.plist`
dans ton dossier LaunchAgents. Ils ne lancent rien, et leur impact est maintenant 0.

Corrigé après ce passage (D-46), et testé :

| Constat | Correction | Test |
|---|---|---|
| 39,9 Mo pour 40, sans scan pendant la mesure ; un scan sur place ajoutait environ 17 Mo, jamais rendus | scan quotidien dans un processus fils ; démon allégé de 5 Mo d'imports | `test_scan_a_part` (fils réel, repli sur place, imports absents) ; conteneur : 18,1 Mo scan compris |
| Relance après `kill` non prouvée par la ligne d'état | âge du battement dans `assistant.py etat` et `doctor` | `test_cli::test_doctor` |

### 3e passage (avec D-46)

```
mesure_demon.py 600
{'duree_s': 602, 'cpu_s': 2.25, 'cpu_moyen_pct': 0.374, 'scan_cpu_s': 0.34, 'cpu_regime_pct': 0.317, 'ram_max_mo': 37.8}
   dont Python lui-même ≈ 0.98 s ; python (scan quotidien, fils) 0.34 s ; top 0.32 s ; log 0.28 s ;
   ps (6 fois) 0.26 s ; pmset 0.03 s ; launchctl list 0.01 s ; last 0.01 s ; sysctl 0.01 s
   plus grosse commande : 62.3 Mo
❌ hors budget (CPU < 0.3 %, RAM < 40.0 Mo)           → mémoire ✅ 37,8 Mo scan compris ; processeur → D-47

kill -9 ; 70 s
   🧹 Démarrage : surveille (battement il y a 7 s)     ✅ relancé par le superviseur
```

Corrigé après ce passage (D-47), et testé :
- `top` toutes les 30 min, et pas au lancement ;
- pas de `last` ni de journal quand le démon est relancé en pleine session ;
- un seul inventaire en mémoire ;
- `mesure_demon.py` sépare le régime du ponctuel (lancement, scan) et vise la moyenne du jour, sans cacher la
  fenêtre brute.

Tests : `test_demon::test_lancement_leger`, `test_scan_a_part::test_moyenne_du_jour_separe_le_ponctuel_du_regime`.
Dans le conteneur (400 s) : fenêtre brute 0,194 %, régime 0,008 %, moyenne du jour 0,01 %, 18,2 Mo.

## Prochaine étape

Sur ton Mac : la mesure finale (ACTIONS_HUMAINES § 9), puis le message final.
