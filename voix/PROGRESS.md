# Avancement de Voix

Chaque phase se termine par `./check.sh` vert, l'intégrité des autres projets identique, un commit, et la preuve
collée ici (sortie réelle).

| Phase | État |
|---|---|
| P0 — environnement, empreinte, squelettes, check.sh | ✅ |
| P1 — compréhension et corpus de phrases | ✅ réglage ; ⚠️ anti-triche 86–89 % < 95 % (D-13) |
| P2 — actions, annulation, confirmation, modules, sécurité | ✅ |
| P3 — moteur audio et corpus audio | ✅ ; ⚠️ scores Whisper à mesurer sur le Mac (D-25) |
| P4 — app Swift | ⏳ |
| P5 — mot d'éveil et suspension pendant les appels | ⏳ |
| P6 — banc d'essai complet, choix du moteur | ⏳ |
| P7 — routines, concentration, aide-mémoire, réglages, doctor, verifier | ⏳ |
| P8 — tests réels sans risque, ressources, robustesse | ⏳ |
| P9 — installation (build unique, 2 LaunchAgents, kill/relance) | ⏳ |
| P10 — revue hostile en deux passes | ⏳ |

## P0 — environnement, empreinte, squelettes, check.sh ✅

- Empreinte « avant » prise **avant toute autre ligne de code** (`integrite/etat_avant.json`) : le dépôt de
  l'assistant hors `voix/` (853 fichiers, arbre git, statut), LaunchAgents, Application Support des autres modules,
  `~/.zshrc`, `~/.zprofile`, `crontab -l`, `shortcuts list`, `docker ps -a`, export des raccourcis clavier du système.
  Sur ton Mac, `install.sh` prend la sienne avant de rien poser (`integrite/mac/`, jamais sur GitHub).
- Raccourci : lecture de l'export `com.apple.symbolichotkeys` et choix du premier candidat libre (D-08), testé sur des
  exports XML et binaires (valeurs d'usine, raccourcis désactivés ou déplacés, entrées étranges, export illisible).
- Squelettes : paquet Python `voix` (réglages bornés, choix automatiques séparés de tes réglages), paquet Swift
  (Core vérifié ici sous Linux avec Swift 6.2.4, XCTest et sans XCTest ; app macOS), `check.sh`.

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 853 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 6 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ swift build -c release
controles-core : 2 réussi(s), 0 échec(s)
  ✅ swift : contrôles du Core (sans XCTest)
	 Executed 2 tests, with 0 failures (0 unexpected) in 0.102 (0.102) seconds
  ✅ swift test (XCTest)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
25 passed in 0.40s
  ✅ socle (unitaires)
15 passed in 3.88s
  ✅ gardien d'intégrité
TOTAL                348      6    98%
  ✅ couverture ≥ 90 % sur voix/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 853 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 6 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```

## P1 — compréhension et corpus de phrases ✅ réglage ; ⚠️ anti-triche sous le seuil

- 69 intentions dans la liste blanche (4 sensibles, confirmées à la voix), normalisation (nombres en lettres,
  politesse, oral, négation), grammaire de phrases entières, catalogue (apps, sites, dossiers, alias, raccourcis,
  routines, playlists) avec ressemblance écrite et phonétique, ambiguïtés « Notes ou Notion ? », refus par choix.
- Seconde lecture (D-11) : phrases remises dans l'ordre, questions par mots, sacs de mots stricts, garde-fous.
- Corpus : jeu 1 généré (2 224 ordres, 332 hors catalogue) + 7 jeux écrits à la main (2 614 ordres, 285 hors
  catalogue). Après réglage, tous les jeux :

```
jeu 1 : 2224 phrases : intention exacte 100.0 %, paramètres exacts 100.0 % ; hors catalogue 332/332 « pas compris » (0 action, 0 refus ou négation) ; sensibles confirmées 85/85
jeu 2 : 327 phrases : intention exacte 100.0 %, paramètres exacts 100.0 % ; hors catalogue 50/50 « pas compris » (0 action, 0 refus ou négation) ; sensibles confirmées 8/8
jeu 3 : 465 phrases : intention exacte 100.0 %, paramètres exacts 100.0 % ; hors catalogue 56/56 « pas compris » (0 action, 0 refus ou négation) ; sensibles confirmées 16/16
jeu 4 : 405 phrases : intention exacte 99.0 %, paramètres exacts 100.0 % ; hors catalogue 58/59 « pas compris » (0 action, 1 refus ou négation) ; sensibles confirmées 14/14
jeu 5 : 408 phrases : intention exacte 99.5 %, paramètres exacts 100.0 % ; hors catalogue 60/60 « pas compris » (0 action, 0 refus ou négation) ; sensibles confirmées 15/15
jeu 6 : 371 phrases : intention exacte 100.0 %, paramètres exacts 100.0 % ; hors catalogue 60/60 « pas compris » (0 action, 0 refus ou négation) ; sensibles confirmées 12/12
jeu 7 : 416 phrases : intention exacte 99.0 %, paramètres exacts 99.8 % ; hors catalogue 60/60 « pas compris » (0 action, 0 refus ou négation) ; sensibles confirmées 12/12
jeu 8 : 413 phrases : intention exacte 98.3 %, paramètres exacts 100.0 % ; hors catalogue 60/60 « pas compris » (0 action, 0 refus ou négation) ; sensibles confirmées 11/11
```

- **Mesure anti-triche (premiers passages, sortie réelle, non retouchée)** — le seuil de 95 % n'est **pas** atteint sur
  des ordres jamais vus ; le détail et la décision sont dans D-13 :

```
jeu 2 (13/10, avant la généralisation)  : 327 ordres, intention exacte 70.6 %
jeu 3 (13/10 20:15 UTC)                 : 463 phrases : intention exacte 91.8 %, paramètres exacts 99.3 % ; hors catalogue 56/58 « pas compris » (2 action) ; sensibles confirmées 15/16
jeu 4 (hostile, 13/10 20:22 UTC)        : 405 phrases : intention exacte 65.7 %, paramètres exacts 98.5 % ; hors catalogue 58/59 « pas compris » (1 action) ; sensibles confirmées 9/14
jeu 5 (hostile, 13/10 21:32 UTC)        : 408 phrases : intention exacte 89.7 %, paramètres exacts 99.5 % ; hors catalogue 59/60 « pas compris » (1 action, 0 refus ou négation) ; sensibles confirmées 14/15
jeu 6 (représentatif, 13/10 21:37 UTC)  : 371 phrases : intention exacte 98.1 %, paramètres exacts 100.0 % ; hors catalogue 59/60 « pas compris » (1 action, 0 refus ou négation) ; sensibles confirmées 12/12
  dont ordres jamais vus                : 158 neufs ; ratés au 1er passage parmi eux : 7 -> 95.6 %
jeu 7 (416 jamais vus, 13/10 21:43 UTC) : 416 phrases : intention exacte 89.2 %, paramètres exacts 99.5 % ; hors catalogue 58/60 « pas compris » (2 action, 0 refus ou négation) ; sensibles confirmées 11/12
jeu 8 (413 jamais vus, 13/10 21:51 UTC) : 413 phrases : intention exacte 86.4 %, paramètres exacts 98.9 % ; hors catalogue 56/60 « pas compris » (4 action, 0 refus ou négation) ; sensibles confirmées 11/11
```

- `./check.sh` :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 853 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 6 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ swift build -c release
controles-core : 2 réussi(s), 0 échec(s)
  ✅ swift : contrôles du Core (sans XCTest)
	 Executed 2 tests, with 0 failures (0 unexpected) in 0.002 (0.002) seconds
  ✅ swift test (XCTest)
All checks passed!
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
25 passed in 0.16s
  ✅ socle (unitaires)
214 passed in 38.39s
  ✅ compréhension : grammaire et corpus de phrases (§9.1)
  ✅ actions, annulation, confirmation (§9.3)
  ✅ sécurité : injection, recherche automatisée (§9.3)
  ✅ intégration : moteur, socket, démon
15 passed in 3.78s
  ✅ gardien d'intégrité
TOTAL                         1883     23    99%
  ✅ couverture ≥ 90 % sur voix/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 853 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 6 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```


## P2 — actions, annulation, confirmation, modules, sécurité ✅

- **Actions** des 69 intentions (`voix/actions/`) : apps, fichiers et dossiers, Spotlight et « ouvre le 2 », sites et
  recherches web, son et musique, système (veille, écran, apparence, Wi-Fi, batterie, heure, date, météo), raccourcis
  Apple et concentration, minuteurs et rappels (gardés sur disque, 0600), tes modules, routines (12 étapes au plus,
  étapes de la liste seulement). Chaque intention a son action (`ACTIONS` = `INTENTIONS`, vérifié par un test).
- **Exécuteur** à liste blanche (D-16), **pont** vers l'app avec des ordres fermés (D-15), chemins et adresses filtrés
  (D-17), « Annule » exact et « Tu confirmes ? » (D-18), modules découverts sans y toucher (D-19), journal (D-20).
- **Faux Mac** pour les tests : de faux `open`, `osascript`, `networksetup`, `pmset`, `shortcuts`, `mdfind`,
  `defaults`, `say`, `tableau`, `ambiance`, `quotidien`, `bouclier` qui notent leurs arguments et simulent l'état.
  52 phrases vérifiées **argument par argument** ; les 8 jeux de phrases exécutés sur le faux Mac (un échantillon par
  intention et toutes les sensibles) : aucune erreur, chaque appel d'une forme permise, 100 % des actions sensibles
  passent par « Tu confirmes ? » **avant** le moindre appel, les phrases hors catalogue ne lancent **rien**.
- **Sécurité** : 37 phrases piégées (« ouvre ; rm -rf ~ », « cherche $(touch …) », « rappelle-moi … do shell
  script », chemins hors maison, `javascript:`, `file://`…) passent par toute la chaîne : aucun fichier témoin créé,
  aucun appel hors forme permise. Recherche automatisée dans tout le code : pas de `shell=`, pas d'`eval`, pas
  d'`os.system`, un seul endroit lance des programmes ; aucune intention de suppression, d'envoi, de paiement ou
  d'extinction.
- **Commande** : `voix comprendre "phrase"` (sans rien faire), `voix journal`, `voix oublier`. Sortie réelle (dossier
  de test, sans apps installées) :

```
$ voix comprendre "mets le volume à trente"
Compris : Régler le volume [son.regler]
  niveau : 30
$ voix comprendre "éteins le Mac"
Refus : Je ne fais pas ça, par sécurité.
$ voix comprendre "ferme tout"
Compris : Fermer toutes les apps [app.fermer_tout]
  ⚠️ action sensible : Voix demandera « Tu confirmes ? »
$ voix comprendre "la soupe de ma grand-mère"
Pas compris.
  Essaie : « verrouille l'écran » ; « état de la batterie » ; « mets la musique en pause »
```

- Corrigé en route : les suggestions proposaient des phrases qui ne marchaient pas chez toi (« lance la routine
  matin » sans routine « matin », un module absent) ; elles ne proposent plus que tes vrais alias, playlists,
  raccourcis, routines et modules installés, et un test vérifie que chaque suggestion est comprise.

- `./check.sh` (sortie réelle, lignes de résultat) :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 853 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 6 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ swift build -c release
controles-core : 2 réussi(s), 0 échec(s)
  ✅ swift : contrôles du Core (sans XCTest)
	 Executed 2 tests, with 0 failures (0 unexpected) in 0.002 (0.002) seconds
  ✅ swift test (XCTest)
All checks passed!
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
25 passed in 1.01s
  ✅ socle (unitaires)
216 passed in 41.08s
  ✅ compréhension : grammaire et corpus de phrases (§9.1)
133 passed in 38.72s
  ✅ actions, annulation, confirmation (§9.3)
45 passed in 3.90s
  ✅ sécurité : injection, recherche automatisée (§9.3)
  ✅ intégration : moteur, socket, démon
15 passed in 3.68s
  ✅ gardien d'intégrité
TOTAL                         3061    111    96%
  ✅ couverture ≥ 90 % sur voix/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 853 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 6 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```


## P3 — moteur audio et corpus audio ✅ (sauf les scores Whisper : à mesurer sur ton Mac, D-25)

- **Détection de voix** (`voix/audio/vad.py`) : Silero (modèle du paquet PyPI, empreinte vérifiée, sans torch),
  WebRTC en repli ; fin de phrase par 500 ms de silence, 8 s au plus, ou la touche relâchée ; une trame 8 dB sous ta
  voix compte comme silence (D-21) ; événement « pause » à 200 ms pour lancer la transcription en avance (D-22).
- **Filtre anti-hallucination** (`voix/audio/anti_hallucination.py`, D-23) et **Whisper** (`voix/audio/whisper_local.py`) :
  mlx sur ton Mac, une passe, français forcé, invite avec tes noms ; modèle vérifié par empreintes, libéré après
  5 min ; absent ou corrompu → Apple Speech (D-25). Testé ici avec un faux mlx (ce que Voix lui demande).
- **Moteur, socket, démon** (`voix/moteur.py`, `voix/protocole.py`, `voix/socket_serveur.py`, `voix/demon.py`, D-24) :
  écoute → fin → transcription anticipée → filtre → compréhension → réponse ; mode Apple (l'app transcrit) ; ordres
  du pont vers l'app et leurs réponses ; `voix demon`, `voix dire "phrase"`. Testé de bout en bout sur un vrai socket
  Unix avec une fausse app : audio par morceaux de 100 ms, ordre « quitter Spotify » et sa réponse, lignes invalides
  ignorées, second moteur refusé, vieux socket remplacé, fichier inattendu non touché, aucun fichier audio écrit.
- **Corpus audio** (`outils/corpus_audio.py`) : 234 phrases (204 ordres de 68 intentions sur 69, 30 hors catalogue), les 7
  voix MBROLA françaises ici (`say` et toutes ses voix françaises sur ton Mac), 3 débits à tour de rôle, sans bruit
  et café (brouhaha + tintements), clavier, rue à 20 et 10 dB ; tout en mémoire. 10 minutes sans parole (silence,
  souffle, clavier, rue, ventilateur).
- Corrigé en route (mesuré, pas supposé) : la condition « sans bruit » ajoutait un souffle à pleine échelle (bug du
  générateur) ; le brouhaha à 10 dB empêchait de trouver la fin (règle des 8 dB) ; un « non » dit vite (0,13 s de
  parole) aurait été rejeté par un seuil à 0,15 s (abaissé à 0,09 s).
- **Banc d'essai** (`outils/banc_audio.py`), `./check.sh --complet`, transcription « oracle » (texte exact : ce que
  valent la détection de fin, le filtre et la compréhension ; Whisper n'a pas pu être téléchargé ici) — sortie réelle :

```
| Condition | Ordres | Intention | Paramètres | Hors catalogue : actions | Fin manquée | Latence p50 | Latence p90 |
|---|---|---|---|---|---|---|---|
| sans bruit | 204 | 100.0 % | 100.0 % | 0 / 30 | 0 | 475 ms | 512 ms |
| 10 dB | 612 | 100.0 % | 100.0 % | 0 / 90 | 0 | 494 ms | 672 ms |
| 20 dB | 612 | 100.0 % | 100.0 % | 0 / 90 | 0 | 475 ms | 510 ms |
10 min sans parole : 0 écoute(s) déclenchée(s), 0 transcription(s), 0 hallucination(s)
2 passed, 1 skipped, 6 deselected in 81.54s (0:01:21)
```

  La latence ci-dessus ne compte pas encore Whisper : avec la transcription anticipée, Whisper ne s'ajoute que pour
  ce qui dépasse 300 ms. L'épreuve sans parole est faite avec un faux Whisper qui inventerait « ouvre Safari » à
  chaque écoute : rien ne passe, car le détecteur n'a jamais déclenché d'écoute sur ces 10 minutes. Le test
  « Whisper réel » est marqué `mac` (ignoré ici en le disant, rejoué sur ton Mac).

- `./check.sh` (sortie réelle, lignes de résultat) :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 853 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 6 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ swift build -c release
controles-core : 2 réussi(s), 0 échec(s)
  ✅ swift : contrôles du Core (sans XCTest)
	 Executed 2 tests, with 0 failures (0 unexpected) in 0.103 (0.103) seconds
  ✅ swift test (XCTest)
All checks passed!
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
77 passed in 1.38s
  ✅ socle (unitaires)
216 passed in 42.28s
  ✅ compréhension : grammaire et corpus de phrases (§9.1)
133 passed in 38.05s
  ✅ actions, annulation, confirmation (§9.3)
45 passed in 4.05s
  ✅ sécurité : injection, recherche automatisée (§9.3)
6 passed, 3 deselected in 2.08s
  ✅ corpus audio : fabrication, banc d'essai rapide (§9.2)
18 passed in 2.03s
  ✅ intégration : moteur, socket, démon
15 passed in 4.08s
  ✅ gardien d'intégrité
TOTAL                               4060    147    96%
  ✅ couverture ≥ 90 % sur voix/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 853 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 6 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```
