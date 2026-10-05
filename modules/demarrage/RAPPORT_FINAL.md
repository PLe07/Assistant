# Rapport final — Nettoyeur de démarrage

Construit le 5 octobre 2026, phases P0 à P10. P11 (diagnostic de ton Mac) : 1er passage fait, 7 défauts réels
corrigés, 2e passage attendu. Chaque preuve ci-dessous est la sortie réelle d'une commande. Le détail est dans
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
| 4 | Bout en bout réussi, recherche de traces vide | ❌ 1er passage : désactivation pas encore visible dans launchd ; corrigé (D-43) · ⏳ 2e passage (ACTIONS_HUMAINES § 2) |
| 5 | Budgets de performance tenus | ✅ scan sur ton Mac (5,1 s puis 1,7 s) · ❌ démon au 1er passage (2,07 %, 308 Mo) ; cause corrigée (D-42) · ⏳ 2e passage |
| 6 | Démon installé, actif, relancé après un `kill` | ⏳ c'est le superviseur de l'Assistant qui le lance et le relance (D-03), comme pour les corvées, déjà prouvé sur ton Mac ; à confirmer (ACTIONS_HUMAINES § 3) |
| 7 | `demarrage doctor` sans erreur bloquante | ✅ dans le conteneur et sur ton Mac (macOS 27.0.1, toutes les commandes présentes) |
| 8 | README en français | ✅ [README.md](README.md) |
| 9 | ACTIONS_HUMAINES.md : seulement l'impossible sans toi | ✅ |
| 10 | Diagnostic de ton vrai Mac (top 10, verdicts, commandes) | ✅ 1er passage (§ 5), qui a révélé 7 défauts, corrigés (D-44, D-45) · ⏳ top 10 corrigé |

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

## 5. Diagnostic de ton Mac

1er passage (5 octobre), avant les corrections D-44 et D-45 : 931 éléments trouvés en 3,3 s, dont 911 de macOS
(🍎) ; 💤 4 · 👻 1 · ⚠️ 4 · ✅ 11 ; 117 relevés en 10 minutes.

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

Ce que ce passage a montré, puis ce qui a été corrigé :
- **Spotify** s'ouvre à chaque connexion et coûte à lui seul 968 Mo et 5 % d'un cœur, en permanence. Il était
  jugé ✅, parce qu'il avait l'air utilisé tous les jours… justement parce qu'il s'ouvre tout seul.
  Il passe 💤 (D-45). L'action est réversible : `demarrage desactiver b8e39d87 --confirmer`. Coupe aussi
  « Ouvrir Spotify automatiquement… » dans les paramètres de Spotify.
- **Les deux « L'Assistant (c'est moi) »** (le superviseur, 1,5 % d'un cœur et 144 Mo avec tous ses modules ;
  l'icône, 45 Mo) sont désormais distingués par leur label (D-44).
- **Google Updater** : un 👻 (son app a été désinstallée, quarantaine réversible) et deux fichiers cassés
  (« pas de Label »). Ceux-ci ne lancent rien : impact 0 désormais (D-45). D'où ils viennent : ACTIONS_HUMAINES
  § 8.
- **Les quatre « Mise à jour de Zoom »** sont dans /Library : des instructions à taper toi-même, réversibles. Ils
  sont désormais distingués par leur label (D-44).

⏳ Le top 10 corrigé : `demarrage top` (ACTIONS_HUMAINES § 5), qui reprend les mesures déjà faites.
