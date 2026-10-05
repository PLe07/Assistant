# Rapport final — Nettoyeur de démarrage

Construit le 5 octobre 2026, phases P0 à P11. Ton Mac a été diagnostiqué en deux passages : 9 défauts réels
trouvés et corrigés (D-42 à D-46). Il reste une vérification finale de 12 minutes (ACTIONS_HUMAINES § 9). Chaque preuve ci-dessous est la sortie réelle d'une commande. Le détail est dans
[PROGRESS.md](PROGRESS.md), les choix dans [DECISIONS.md](DECISIONS.md), ce qui te reste dans
[ACTIONS_HUMAINES.md](ACTIONS_HUMAINES.md).

Légende :
- ✅ fait et prouvé ;
- ⏳ prouvé dans l'environnement de construction (conteneur Linux, faux Mac), à confirmer sur ton Mac par les
  commandes d'ACTIONS_HUMAINES.md (5 minutes de ton temps).

## Définition de « terminé »

| | Critère | Statut |
|---|---|---|
| 1 | `./check.sh` vert | ✅ (sortie § 1) |
| 2 | Critères du faux Mac + 2e faux Mac sur 5 graines | ✅ 100 % partout (§ 2) |
| 3 | Tests de sécurité verts, recherche « sudo » vide | ✅ (§ 3) |
| 4 | Bout en bout réussi, recherche de traces vide | ✅ sur ton Mac au 2e passage (`1 passed` : désactivé, restauré, aucune trace) |
| 5 | Budgets de performance tenus | ✅ sur ton Mac : scan 3,0 s puis 2,1 s ; démon 0,274 % et 39,9 Mo, de justesse, puis allégé (D-46) · ⏳ vérification finale (ACTIONS_HUMAINES § 9) |
| 6 | Démon installé, actif, relancé après un `kill` | ✅ allumé et actif sur ton Mac · ⏳ relance : la ligne d'état n'était pas probante, elle montre maintenant l'âge du battement (D-46 ; ACTIONS_HUMAINES § 9) |
| 7 | `demarrage doctor` sans erreur bloquante | ✅ dans le conteneur et sur ton Mac (macOS 27.0.1, toutes les commandes présentes) |
| 8 | README en français | ✅ [README.md](README.md) |
| 9 | ACTIONS_HUMAINES.md : seulement l'impossible sans toi | ✅ |
| 10 | Diagnostic de ton vrai Mac (top 10, verdicts, commandes) | ✅ § 5 |

## 1. check.sh

```
$ PYTHON=…/venv/bin/python modules/demarrage/check.sh
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

## 2. Le faux Mac (le juge principal)

Le juge (`tests/demarrage/faux_mac/juge.py`) fait comme le démon, puis compare à la vérité terrain :
- scan à la connexion ;
- 5 minutes en mode « ouverture de session » ;
- 30 minutes de croisière ;
- analyse.

Critères (§9.2) :
- 100 % des éléments plantés avec le bon verdict et la bonne action ;
- 0 élément Apple avec une action ;
- 0 inconnu avec autre chose que « vérifier » ;
- les 3 plus lourds en tête ;
- aucun plantage sur un plist corrompu.

Faux Mac n° 1 : 18 éléments Apple (tous 🍎, sans action), et les éléments plantés ci-dessous, classés par impact.

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
```

Le 2e faux Mac est tiré au hasard. Il a été écrit après le réglage des règles, et a réussi du premier coup.

| Graine | Éléments plantés | Éléments Apple | Verdicts justes |
|---|---|---|---|
| 3 | 17 | 36 | 53/53 |
| 17 | 17 | 37 | 54/54 |
| 42 | 17 | 33 | 50/50 |
| 1789 | 18 | 32 | 50/50 |
| 20261005 | 20 | 24 | 44/44 |

## 3. Sécurité

Les 18 tests de sécurité sont verts (§ 1). Ce qu'ils prouvent :
- **Simulation sans `--confirmer`** de `desactiver` puis `restaurer`, sur chaque élément des deux faux Mac : 0
  commande de modification, 0 fichier touché, journal vide.
- **Le vrai `Mac`, avec `subprocess.run` intercepté** : la simulation ne lance que de la lecture. Apple et les
  éléments globaux ne lancent rien, même avec `--confirmer`.
- **🍎** : refus systématique.
- **`/Library`, daemons, extensions, cron** : des instructions seulement.
- **⚠️** : jamais supprimé ni mis en quarantaine (D-37).
- **Recherche automatique de « sudo »** : il n'apparaît que dans les deux fichiers permis, `actions/instructions.py`
  (du texte à recopier, jamais exécuté) et `systeme.py` (la liste des commandes refusées).

```
$ grep -rln sudo --include='*.py' --include='*.json' --include='*.sh' modules/demarrage demarrage.py
modules/demarrage/actions/instructions.py
modules/demarrage/systeme.py
```

## 4. Performance

```
relevé : 16.6 ms de processeur, 0.36 s pour 20 ; pic mémoire Python 0.13 Mo ; moyenne projetée sur 24 h : 0.015 %
1070 éléments · 1er scan 2.2 s (170 codesign à 80 ms, en parallèle) · avec le cache 0.4 s
```

Démon réel, 10 minutes, dans le conteneur (dont le scan de préparation et le démarrage de Python ; le processeur
des commandes lancées par le démon est compté) :

```
$ python tests/demarrage/e2e_mac/mesure_demon.py 600
{'duree_s': 601, 'cpu_s': 1.01, 'cpu_moyen_pct': 0.168, 'ram_max_mo': 22.8}
✅ dans les budgets
```

Sur ton Mac, au 1er passage (5 octobre) :

```
pytest tests/demarrage/e2e_mac    →  scan : 5.1 s, puis 1.7 s avec le cache codesign   ✅ (< 15 s, < 5 s)
mesure_demon.py 600                →  {'duree_s': 602, 'cpu_s': 12.46, 'cpu_moyen_pct': 2.071, 'ram_max_mo': 308.0}  ❌
```

Le démon dépassait : au lancement, il relisait tout le journal système depuis le démarrage du Mac
(`log show --last boot`). Il ne le lit plus que sur 7 minutes au plus (D-42). La prochaine mesure affichera aussi
le coût de chaque commande, pour vérifier.

2e passage, avec D-42 :

```
mesure_demon.py 600   →  {'duree_s': 602, 'cpu_s': 1.65, 'cpu_moyen_pct': 0.274, 'ram_max_mo': 39.9}  ✅
   dont Python ≈ 0.79 s ; top 0.31 s ; log 0.27 s ; ps (6 fois) 0.22 s ; pmset 0.03 s ; launchctl list 0.02 s
```

Les budgets tenaient, mais de justesse : 39,9 Mo pour 40, et sans scan pendant la mesure. Le scan quotidien tourne
désormais dans un processus fils, et le démon ne charge plus la pile du scan (D-46). Dans le conteneur, cela donne
18,1 Mo, scan compris. La vérification finale sur ton Mac est dans ACTIONS_HUMAINES § 9.

## 5. Diagnostic de ton Mac

931 éléments trouvés en 3,3 s, dont 911 de macOS (🍎, jamais touchés). 16 se lancent tout seuls, et 1 coûte
vraiment : **Spotify, 968 Mo de mémoire et 5 % d'un cœur, en permanence**.

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

**Si tu coupes les 6 éléments 💤 et 👻 : environ 968 Mo de mémoire libérée.**

- **Spotify** 💤 : il s'ouvre à chaque connexion. L'action est réversible : `demarrage desactiver b8e39d87
  --confirmer`. Coupe aussi « Ouvrir Spotify automatiquement… » dans ses paramètres, sinon il se remet.
- **L'Assistant** ✅ : le superviseur (144 Mo avec tous ses modules) et l'icône (45 Mo). C'est moi.
- **Google Updater** 👻 : son app a été désinstallée. Quarantaine réversible.
- **Deux fichiers Keystone cassés** (`com.google.keystone.agent` et `com.google.keystone.xpcservice`, sans Label) :
  impact 0, ils ne lancent rien.
- **Mise à jour de Zoom** 💤 ×4 : dans /Library, donc des instructions à taper toi-même (droits d'administrateur
  pour deux d'entre elles), réversibles.
- **`com.jarvis.agent`** ⚠️ : non signé, 9 Mo. Sans doute un ancien script à toi. `demarrage desactiver 511c9b36`
  (simulation) montre son fichier et son programme.
- **AlDente** ✅ : l'assistant de charge de la batterie, utile s'il te sert.

Vu une fois pendant le test : la mise à jour de l'app Claude (`ShipIt`), ⚠️ et passagère (PROGRESS P11).

Le rapport complet (courbes, mode sombre) : `cd ~/Assistant && .venv/bin/python demarrage.py rapport`.
