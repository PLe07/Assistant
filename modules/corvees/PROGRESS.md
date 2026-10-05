# Avancement — Détecteur de corvées répétées

Reprise après coupure : lire ce fichier et `DECISIONS.md`, puis reprendre à « Prochaine étape ».
Porte unique : `modules/corvees/check.sh` (dans le conteneur : `PYTHON=<venv>/bin/python modules/corvees/check.sh`).

| Phase | Statut | Preuve |
|---|---|---|
| P0 Reconnaissance, squelette, check.sh | ✅ | ci-dessous |
| P1 Données, config, vie privée | ✅ | 112 tests, couverture 99 % |
| P2 Normalisation + simulateur de vie | ✅ | 6 tests du simulateur |
| P3 Détecteurs, score, mémoire | ✅ | 100 % / 100 % sur 5 graines × 2 jeux ; 208 k événements en ~6 s |
| P4 Capteurs C1-C6 + inactivité | ✅ | 26 tests (vrais fichiers, vraies bases SQLite, vraie surveillance) |
| P5 Démon, planification, robustesse | ✅ | 20 tests du démon |
| P6 Couche IA, budget, propositions | ✅ | 116 tests de plus ; fuites cherchées aussi dans ce qui part chez Claude |
| P7 Rapport HTML, notifications, CLI | ✅ | 52 tests de plus ; rapport vérifié en clair, sombre et sur mobile |
| P8 Bout en bout, mesures | ✅ conteneur · ⏳ Mac | e2e réel, 3 défauts trouvés et corrigés ; CPU 0,17 %, RAM 29 Mo |
| P9 Installation, relance après kill | ✅ conteneur · ⏳ Mac | relancé par le superviseur en 7 s ; doctor sans erreur |
| P10 Revue hostile, démonstration, rapport final | ✅ | 8 défauts corrigés ; RAPPORT_FINAL.md |

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

## P1 — Données, configuration, vie privée (✅)

- `config.py` : toutes les valeurs par défaut et tous les seuils ; reglages.json → modules.corvees, fusion en
  profondeur ; une valeur de mauvais type est remplacée et signalée.
- `privacy.py` : caviardage (e-mails, téléphones FR, IBAN avec contrôle mod 97, cartes avec Luhn, clés sk-/sk-ant-/
  ghp_/AKIA…, JWT, Bearer, hexadécimal ≥ 32, base64 ≥ 40, mots de passe en ligne de commande, paramètres d'URL,
  identifiants dans les URL, clés privées) ; exclusions (applis par nom/bundle/accents, domaines, dossiers,
  titres de fenêtres sensibles) ; empreinte HMAC salée ; sel 32 octets en 600.
- `db.py` : seul chemin d'écriture = `Base.ajouter()` qui passe par le Gardien ; base en 600 ; purge → agrégats ;
  base corrompue → mise de côté + reconstruite ; disque plein → `DisquePlein`.
- `normalize.py` : heure de Paris (changements d'heure testés), motifs de noms, lieux, URL, commandes, tokens.

```
$ modules/corvees/check.sh
✅ ruff check · ✅ ruff format · ✅ mypy (9 fichiers)
112 passed · Total coverage: 99.15%
CHECK OK
```

## P2 — Simulateur de vie (✅)

`tests/corvees/simulation/generateur.py` : 28 jours (à partir d'un lundi), ~440 événements par jour de bruit
réaliste (26 applis pondérées, ~60 sites avec des chemins variables, fichiers téléchargés/rangés/renommés,
commandes, copier-coller, titres de fenêtres, inactivité), produits par la vraie normalisation.
10 corvées plantées (jeu A) avec leur vérité terrain (motifs + nombre requis), 4 pièges : Spotify seul chaque
matin, une corvée refusée (Mail → Excel), applis et sites exclus (1Password, Messages, Boursorama, impots.gouv),
7 faux secrets (mot de passe MySQL, clé sk-ant, IBAN, e-mail, téléphone, jeton GitHub, PASSWORD=).
Le 2e jeu de corvées sera écrit seulement après le réglage (P3).

```
$ modules/corvees/check.sh
✅ ruff · ✅ format · ✅ mypy · 112 passed (99.15 %) · simulation 6 passed · CHECK OK
$ densité de performance : generer(1, jours=30, densite=30) → 213 561 événements
```

## P3 — Détecteurs, score, mémoire (✅)

D1 séquences (croissance de motifs, 1 parasite, maximales, lift), D2 routines (créneau ± 45 min, hebdomadaire,
concentration), D3 fichiers (parcours reliés par empreinte, règles par racine/préfixe), D4 ponts (Poisson +
Bonferroni), D5 commandes (lignes enchaînées, suites), score (formule de l'énoncé, durées bornées, facteurs),
fusion des descriptions d'une même corvée, mémoire des refus/reports/acceptations. Réglage : D-10 à D-22.

Critères §9.1 (`tests/corvees/simulation/test_simulation.py`, graines jamais vues pendant le réglage) :

| Jeu | Graine | Rappel (top 10) | Précision (top 10) | Fausses alertes | Refusée revenue | Spotify seul en tête | Fuites |
|---|---|---|---|---|---|---|---|
| A | 101 | 100% | 100% | 0 | non ✅ | non ✅ | 0 |
| A | 202 | 100% | 100% | 0 | non ✅ | non ✅ | 0 |
| A | 303 | 100% | 100% | 0 | non ✅ | non ✅ | 0 |
| A | 404 | 100% | 100% | 0 | non ✅ | non ✅ | 0 |
| A | 505 | 100% | 100% | 0 | non ✅ | non ✅ | 0 |
| B | 101 | 100% | 100% | 0 | non ✅ | non ✅ | 0 |
| B | 202 | 100% | 100% | 0 | non ✅ | non ✅ | 0 |
| B | 303 | 100% | 100% | 0 | non ✅ | non ✅ | 0 |
| B | 404 | 100% | 100% | 0 | non ✅ | non ✅ | 0 |
| B | 505 | 100% | 100% | 0 | non ✅ | non ✅ | 0 |

Lot final jamais vu (1111, 2222, 3333, 4444, 5555) : A 5 × 100 %/100 % ; B 4 × 100 %/100 %, 1 × 90 %/90 %
(graine 3333 : la corvée hebdomadaire du vendredi manquée, 1 fausse alerte). Total : 49/50 corvées, critères tenus.

```
$ modules/corvees/check.sh
✅ ruff check · ✅ ruff format · ✅ mypy
144 passed · Total coverage: 97.43%
simulation : 16 passed (5 graines × jeu A + 5 graines × jeu B + générateur)
performance : 208 534 événements analysés en ~6 s (< 10 s)
CHECK OK
```

## P4 — Capteurs (✅)

`capteurs/` : apps (C1), fenetres (C2), fichiers (C3), shell (C4), navigateur (C5), pressepapiers (C6),
inactivite ; `natif.py` isole tout l'accès à macOS (hors couverture, remplacé par une imitation). Chaque capteur a
un statut ok / dégradé / désactivé avec la raison. Testés pour de vrai ici : surveillance des dossiers (watchdog,
inotify), mode dégradé sans watchdog (instantanés), historique zsh (format étendu, multi-lignes, octets « méta »,
réécriture), bases Chrome et Safari construites dans le test (curseur, transitions ignorées, Safari sans accès).

```
$ modules/corvees/check.sh
✅ ruff · ✅ format · ✅ mypy (27 fichiers)
170 passed · Total coverage: 98.04%
simulation 16 passed · performance 1 passed · CHECK OK
```

## P5 — Démon (✅)

`daemon.py` : `Demon` (sessions, écriture groupée, battement + santé, purge quotidienne, pause, analyse au dernier
21 h manqué si branché ou batterie > 30 %, capteurs relancés avec délai croissant, disque plein, base abîmée),
`boucle(ctx)` pour le superviseur, interface `start / stop / status / health`. `python -m modules.corvees` lance le
démon ; avec des arguments, la commande. Module ajouté (éteint) aux réglages de l'Assistant.

```
$ modules/corvees/check.sh
✅ ruff · ✅ format · ✅ mypy
190 passed · Total coverage: 98.20%
simulation 16 passed · performance 1 passed · CHECK OK
```

## P6 — Couche IA, propositions (✅)

- `ia.py` : résumé caviardé des corvées (ni date, ni empreinte, ni exemple), au plus 8 par demande, une demande
  par jour. Schéma vérifié avec jsonschema, une relance de correction, 3 essais sur panne. Pendant un quota, on
  attend la pause de l'Assistant. Budget mensuel et coût en base.
- `descriptions.py` : descriptions locales au même format, avec des scripts réels quand c'est sûr.
- `propositions.py` : `propositions/<id>/` (README, script, proposition.json). Contrôle statique : zsh/bash -n,
  shellcheck, liste de dangers. `installer` (alias, tâche launchd) avec sauvegarde, et `desinstaller`.
- `suite.py` : la suite du soir dans un fil à part.

Le juge de simulation passe aussi la suite du soir avec un « Claude perroquet », qui recopie tout ce qu'il reçoit :
aucun secret ni élément exclu ne doit apparaître dans la base, le message envoyé, les propositions ou le journal.

```
$ modules/corvees/check.sh
✅ ruff check · ✅ ruff format · ✅ mypy
306 passed, 1 deselected · Total coverage: 98.50%
simulation 16 passed (5 graines × 2 jeux + fuites, y compris le contenu envoyé à Claude)
performance 1 passed
CHECK OK
```

Non-régression de l'Assistant (après P5) : 931 ✅. Le seul ❌ venait d'une liste de modules figée dans un essai,
à laquelle il manquait « corvees » ; la fiche FICHE.md sera complétée en P10.

## P7 — Rapport, notifications, commande (✅)

- `rapport.py` : page autonome, en français, avec mode sombre. Pour chaque corvée :
  - ce qui a été observé (« Tu déplaces les fichiers « Facture_*.pdf » de ~/Downloads vers ~/Documents/Factures :
    12 fois en 4 semaines. ») ;
  - la fréquence, la dernière fois, le temps perdu et le gain ;
  - la solution, avec son script contrôlé et un bouton « Copier » ;
  - les commandes accept, reject et snooze.

  Le rendu a été vérifié dans Chromium : en clair, en sombre, et à 390 px de large sans défilement horizontal.
- `notifier.py` : une notification par jour au plus, jamais de 23 h à 8 h, aucune sans nouveauté. Elle part par
  les notifications de l'Assistant ; en mode test, elle va dans un fichier de journal.
- `cli.py` : status, rapport, accept [--installer], reject, snooze, pause, resume, analyser --maintenant, purge
  (avec confirmation), doctor, desinstaller. La commande parle au démon par la base (vider, purge, confirmation de
  pause).
- Assistant : `python assistant.py corvees …`, une ligne dans `etat`, et le module dans FICHE.md.

Le juge de simulation cherche maintenant les fuites dans tout le dossier du détecteur, rapport HTML compris.

```
$ modules/corvees/check.sh
✅ ruff check · ✅ ruff format · ✅ mypy
358 passed, 1 deselected · Total coverage: 98.80%
simulation 16 passed · performance 1 passed
CHECK OK
```

Démonstration sur un mois simulé (graine 101), sans jeton Claude dans le conteneur :

```
$ corvees analyser --maintenant
🔎 Analyse des 30 derniers jours…
   · Claude indisponible (Jeton Claude absent du .env de l'assistant.) : descriptions faites sur place
   10 corvée(s) repérée(s) en 0.3 s :
   [53iuxw] Renommer les « Capture d’écran * à *.png » · ≈ 29 min/mois
   [lvyerd] Ranger les « Facture_*.pdf » dans ~/Documents/Factures · ≈ 13 min/mois
   …
```

## P8-P9 — Bout en bout, mesures, installation (✅ dans le conteneur ; à refaire sur le Mac)

**Bout en bout réel** (`tests/corvees/e2e`). Un vrai démon, avec ses capteurs watchdog et zsh, tourne dans un bac
à sable. Il voit 5 fichiers vraiment créés puis rangés, et 5 commandes vraiment exécutées par zsh avec un HISTFILE
de test (plus un faux mot de passe). Ensuite :

```
$ corvees analyser --maintenant
🔎 Analyse des 30 derniers jours…
   · Descriptions faites sur place : Claude coupé dans les réglages (modules.corvees.ia.actif)
   2 corvée(s) repérée(s) en 0.0 s :
   [ugn5ie] Ranger les « Devis_*.pdf » dans Devis · ≈ 7 min/mois
   [diesag] Commande « cd ~/CorveesSandbox && ls -la » · ≈ 6 min/mois
(historique écrit par zsh)
1 passed, 1 skipped
```

Le test vérifie aussi :
- les 5 rangements et les 5 commandes sont en base ;
- le faux mot de passe n'apparaît nulle part dans le dossier (base, propositions, rapport) ;
- le bac à sable est effacé à la fin.

Il a trouvé 3 défauts réels, corrigés après un test qui les reproduit (D-44) :
- une commande perdue quand deux tombent dans la même seconde ;
- la sauvegarde par copie de zsh prise pour une réécriture ;
- les fichiers -wal et -shm en 644.

**Démon réel sous le superviseur, 10 minutes**, dans une copie isolée de l'Assistant avec seul « corvees »
allumé, et une activité toutes les 15 s :

```
$ python tests/corvees/perf/mesure_demon.py 600
{'pid': 605, 'duree_s': 601, 'cpu_moyen_pct': 0.166, 'ram_max_mo': 29.4, 'base_mo': 0.57}
✅ dans les budgets (CPU < 1 %, RAM < 120 Mo, base < 200 Mo)
```

**Relance après kill** (délais d'essai de l'Assistant : 5 s ; en vrai, 1 minute) :

```
avant : pid 605
relancé en 7 s : pid 1796
[superviseur] Module « corvees » tombé (code -9) : code de sortie -9 · relance dans 5 s
[superviseur] Module « corvees » lancé (pid 1796)
```

**doctor** dans cette installation (code de sortie 0) :

```
✅ Module allumé · ✅ Démon vivant · ✅ Capteur fichiers ok · ✅ Capteur shell ok
⚠️ apps, fenetres, pressepapiers, inactivite : désactivés « pas sur un Mac » (conteneur Linux)
⚠️ navigateur : aucun historique trouvé · ✅ Base 125 événements, 0,6 Mo, lisible par toi seul
✅ Dernière analyse · ✅ Claude 0,00 $ sur 2,00 $ · ⚠️ jeton absent (pas de jeton dans le conteneur)
```

**Performance** après le correctif D-45 : 208 534 événements analysés en 6,7 s (avant : 8 à 10 s sur cette
machine plus lente).

```
$ modules/corvees/check.sh
✅ ruff check · ✅ ruff format · ✅ mypy
362 passed, 1 skipped · Total coverage: 98.84%
simulation 16 passed · performance 1 passed
CHECK OK
```

**Ce qui reste sur le Mac** (ACTIONS_HUMAINES.md §3) :
- le bout en bout avec les applis (`CORVEES_E2E_MAC=1`) ;
- la mesure de 10 minutes avec les capteurs propres au Mac (appli au premier plan, presse-papiers…) ;
- le kill réel (relance en 1 minute).

## P10 — Revue hostile, démonstration, rapport final (✅)

**Revue hostile** (DECISIONS D-47 à D-52), chaque défaut d'abord reproduit par un test :
- base occupée prise pour une base abîmée ;
- messages d'erreur non caviardés ;
- notification possible en double ;
- purge pendant la suite du soir ;
- mémoire de l'analyse à 317 Mo.

La mémoire est ramenée à 124 Mo (événements compacts, motifs en tableaux serrés), puis l'analyse passe dans un
programme à part : le démon reste à 23 Mo pendant l'analyse de 208 426 événements. Les résultats sont identiques
(tableau de simulation inchangé, 6 cas comparés motif par motif).

**Démonstration** : `python -m tests.corvees.simulation.demo` →
[demo/rapport_demo.html](demo/rapport_demo.html). C'est un mois inventé, décrit sans Claude, et la page n'est
écrite que si aucun faux secret ni élément exclu n'y est retrouvé. Elle a été vérifiée en sombre et sur mobile.

**Documents** : [README.md](README.md), [ACTIONS_HUMAINES.md](ACTIONS_HUMAINES.md),
[RAPPORT_FINAL.md](RAPPORT_FINAL.md) (définition de « terminé » et preuves). Le module figure dans le README et la
FICHE de l'Assistant.

**Non-régression de l'Assistant** (les 15 suites de tous les modules, après P10) :

```
TOTAL : 932 ✅  0 ❌
```

**État : terminé.** Il reste les vérifications sur le Mac (ACTIONS_HUMAINES §3).
