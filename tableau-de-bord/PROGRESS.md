# Avancement — Tableau de bord

Reprise après coupure : lire ce fichier et `DECISIONS.md`, puis reprendre à la première phase non cochée.
Chaque phase se termine par `./check.sh` vert, l'intégrité identique, un commit.

| Phase | État | Commit |
|---|---|---|
| P0 — environnement, empreinte, découverte, échantillons, squelette, check.sh | ✅ | « Tableau de bord P0 » |
| P1 — sondes en lecture seule | ✅ | « Tableau de bord P1 » |
| P2 — registre et adaptateurs | ✅ | « Tableau de bord P2 » |
| P3 — analyses | ✅ | « Tableau de bord P3 » |
| P4 — alertes, sourdine, rapport de la semaine | ✅ | « Tableau de bord P4 » |
| P5 — page web | ✅ | « Tableau de bord P5 » |
| P6 — barre des menus, instantané iCloud, CLI | ⏳ | |
| P7 — faux écosystème complet | ⏳ | |
| P8 — installation | ⏳ | |
| P9 — 30 min réelles, performance | ⏳ | |
| P10 — revue hostile en deux passes | ⏳ | |

## P0 — 2026-10-07

- Empreinte « avant » prise **avant toute autre ligne du projet** : `integrite/empreinte.py` (bibliothèque standard
  seule) puis `integrite/etat_avant.json` — dépôt hôte hors `tableau-de-bord/` : 730 fichiers de code et de
  réglages (assistant, Corvées, Nettoyeur, Trieur, Bouclier, Quotidien), HEAD de départ `8c7ba63`, `git status` vide.
- Reconnaissance des autres modules (D-07) : Corvées, Nettoyeur, Trieur et tri Gmail tournent sous le superviseur de
  l'assistant ; Bouclier et Quotidien sont des LaunchAgents ; Ambiance n'est pas dans ce dépôt ; n8n est dans Docker.
- Échantillons réels **copiés puis anonymisés** (`outils/capturer_echantillons.py`, D-06) :
  `tests/fixtures/reelles/conteneur/` (journal de l'assistant : 520 lignes, dont les erreurs et avertissements
  anciens ; schémas exacts de `etat.db` et `trieur.db`).
- Socle : `config.py` (réglages validés, port 47615, jeton 600), `systeme.py` (liste blanche : 18 commandes permises
  et 35 interdites testées), `caviardage.py`, `db.py` (notre base, 600, WAL, base abîmée mise de côté, disque plein,
  agrégats 48 h / 90 jours), `module.py` (le modèle commun), `sondes/sqlite_copie.py` (copie cohérente des bases
  des autres).
- `check.sh` : intégrité (début), ruff, ruff format, mypy, pytest par groupes, couverture ≥ 90 %, intégrité (fin) ;
  `--complet` ajoute le faux écosystème et la performance.

Preuve (`./check.sh`) :

```
▶ intégrité des autres projets (début)
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
All checks passed!
Success: no issues found in 8 source files
94 passed in 8.95s
11 passed in 11.27s   (lecture seule : 30 lectures pendant les écritures, 0 « database is locked »)
12 passed in 3.07s    (empreinte)
TOTAL                              743      8    99%
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
CHECK OK
```

## P1 — 2026-10-07

- `sondes/launchd.py` : `launchctl list` (un appel par tour) et `launchctl print` (seulement si le label a changé ou
  toutes les 10 min), lus au format de macOS (échantillons `tests/fixtures/launchd/`), tolérants.
- `sondes/processus.py` : psutil, processeur par différence de temps processeur (aucune attente active), mémoire et
  âge de l'arbre de processus ; fils du superviseur de l'assistant (`python -m modules.<nom>`) ; charge du Mac.
- `sondes/logs.py` : lecture par la fin, curseur dans notre base (redémarrage sans double compte), rotation
  (fin de l'ancien fichier lue sous son nouveau nom), troncature, réécriture sous le même numéro (empreinte de tête),
  lignes incomplètes laissées pour le tour suivant, 256 Ko au premier passage ; formats de l'assistant, de Bouclier,
  de Quotidien et des sorties d'erreur brutes (piles d'appels rattachées, jamais recomptées) ; erreurs par tranches
  de 5 min, dernières erreurs caviardées.
- `sondes/files_attente.py` (âge = première fois vu, pages du Trieur et fichiers temporaires ignorés, fantômes
  iCloud comptés à part, jamais téléchargés), `sondes/docker_n8n.py` (Docker éteint, `docker stats --no-stream` au
  plus toutes les 10 min, `healthz` en local seulement, sans mandataire), `sondes/tailles.py` (stat seulement, borné).
- Preuves de lecture seule (`tests/lecture_seule/`) : un **crochet d'audit Python** voit chaque ouverture,
  connexion SQLite, suppression, renommage, changement de droits ou de date chez le faux module pendant le passage de
  toutes les sondes → 0 interdit (et un test prouve que l'espion verrait une écriture) ; empreintes et dates
  identiques ; vrai `lsof` pendant les lectures en boucle → aucun fichier du module resté ouvert.

Preuve (`./check.sh`) :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
All checks passed!
Success: no issues found in 14 source files
113 passed in 11.01s   (unitaires)
14 passed in 13.03s    (lecture seule)
12 passed in 2.92s     (empreinte)
TOTAL                              1315     32    98%
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
CHECK OK
```

## P2 — 2026-10-07

- `decouverte.py` : plists lus avec plistlib (programme, journaux, KeepAlive, périodique), dossier du projet déduit
  du programme, assistant retrouvé par son superviseur ou son tri Gmail, conteneurs n8n.
- `registre.py` : `modules.toml` généré (8 modules connus + chaque `com.<session>.*` inconnu), puis seulement
  complété à la fin ; lecture tolérante (bloc faux ignoré avec un message) ; `modules.example.toml` commenté.
- `adaptateurs/` : `contexte.py` (lectures partagées une fois par tour : `launchctl list`, journal de l'assistant,
  `etat.db`, fils du superviseur, `docker ps`), `base.py` (générique, étapes isolées), `supervise.py` (D-07),
  `assistant.py`, `corvees.py`, `nettoyeur.py`, `trieur.py`, `bouclier.py`, `quotidien.py`, `ambiance.py`, `n8n.py`.
- Schémas recopiés **à l'identique** du code des modules : `tests/fixtures/deduites/*.schema.sql` ; schémas réels
  capturés : `tests/fixtures/reelles/conteneur/`. Un faux Mac (`tests/fabrique.py`) les assemble.
- Tests (41) : écosystème sain lu correctement module par module ; journal partagé réparti ; relances vues par
  launchd et par le journal du superviseur ; éteint/en pause ≠ panne ; désinstallé en cours de route ; Docker éteint ;
  launchd muet ; **11 formats inattendus** (table absente, colonne renommée, valeur non numérique, base abîmée ou
  absente, réglages illisibles ou interdits en lecture) → « inconnu », 0 exception ; registre (génération, ajout à la
  fin sans toucher au reste, fichier cassé, aller-retour TOML).

Preuve (`./check.sh`) :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
All checks passed!
Success: no issues found in 31 source files
113 passed (unitaires) · 14 passed (lecture seule) · 41 passed (adaptateurs) · 12 passed (empreinte)
TOTAL                               2453     91    96%
INTÉGRITÉ OK : identique à etat_avant.json (…)
CHECK OK
```

## P3 — 2026-10-08

- `planif.py` : le temps qui passe vraiment. Échéances locales par `mktime` (changement d'heure compris), veilles
  notées (écart entre horloge murale et horloge monotone > 45 s, ou trou entre deux tours), **temps éveillé** entre
  deux instants, échéancier des tâches du démon.
- `analyse/attentes.py` : quotidienne (tenue avec jusqu'à 30 min d'avance, manquée après la tolérance, **reportée au
  réveil** si le Mac dormait), périodique **en temps éveillé** (une nuit de veille n'est pas un retard), réglages lus
  chez le module (heure changée, attente éteinte → « inactive »), historique des échéances pour les graphiques.
- `analyse/sante.py` : pastille et phrase simple, et les problèmes avec leur message calme et leur message de
  résolution : arrêté, boucle de plantages (seule exception permise la nuit si elle consomme), figé, échec d'un
  passage, attente manquée, file bloquée, pic d'erreurs (≥ 3 × la moyenne de 7 jours et ≥ 10/h), budget 80 % /
  100 %, données > 500 Mo ou + 50 %/semaine, processeur élevé longtemps, n8n, code changé. launchd muet → 🟡
  « état inconnu », jamais une alerte ; éteint → ⚪.
- `analyse/credits.py` (estimé par module, projection fin de mois, mois précédent, équivalent API de l'assistant) et
  `analyse/credits_reels.py` (option éteinte par défaut, clé dans le trousseau, une requête par heure au plus).
- `analyse/ressources.py` : processeur, mémoire, énergie estimée, en une phrase.
- `analyse/integrite.py` : le gardien. Référence, contrôle rapide (taille, date, numéro) toutes les 30 min, relecture
  complète une fois par jour, écarts ajouté/modifié/supprimé avec date et dernier commit, « nouvelle référence »,
  commande `git diff` à lancer soi-même (rien n'est jamais restauré), **FSEvents** (watchdog) qui marque seulement le
  module dont le périmètre est touché, après 20 s de calme. git toujours avec `--no-optional-locks`.
- Tests : 136 unitaires (textes, veille vue par les deux horloges, changement d'heure du 25 octobre, attentes,
  santé de chaque problème, crédits, coût réel avec un faux serveur, ressources) et 7 du gardien, dont une
  empreinte avant/après de tout le monde imité, `.git` compris : identique.

Preuve (`./check.sh`) :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
All checks passed!
Success: no issues found in 38 source files
136 passed in 11.43s   (unitaires)
14 passed in 12.94s    (lecture seule)
41 passed in 2.09s     (adaptateurs)
19 passed in 3.55s     (empreinte + gardien)
TOTAL                               3236     80    98%
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
CHECK OK
```

## P4 — 2026-10-08

- `notifier.py` : notification du Mac par `osascript -e 'display notification …'` (seule forme permise par la liste
  blanche), texte échappé pour AppleScript et borné à 400 caractères ; hors d'un Mac, notée seulement ; un double
  en mémoire pour les tests et le faux écosystème.
- `analyse/alertes.py` : chaque problème a une clé stable et vit dans notre base (pas de doublon après un
  redémarrage). Confirmé avant d'alerter (2 tours et 90 s), une alerte, un rappel toutes les 24 h, une résolution
  après 150 s d'absence ; revenu avant : rien n'est répété. **3 notifications par jour au plus**, ce qui arrive
  ensemble part dans une seule (on attend jusqu'à 2 min ce qui va être confirmé ou réglé). **Silence de 23 h à 8 h**
  sauf boucle de plantages qui consomme. 10 min de calme après un réveil ou un redémarrage. **Sourdine** (« 1h »,
  « 30min », « 2h30 », « fin »). Familles : la boucle devenue arrêt, le budget passé de 80 à 100 % ferment l'ancien
  problème sans faux « ✅ ». Module éteint : alerte close (avec message seulement si elle avait été annoncée) ;
  module retiré du registre ou code accepté : clos sans bruit. Notificateur en panne : noté, pas de boucle.
- `analyse/rapport_semaine.py` : dimanche 20 h (réglable), rattrapé au réveil, une seule fois, jamais pour une
  semaine non observée ; ce qui a tourné (part du temps en 🟢, attentes tenues/manquées), ce qui a coincé (réglé ou
  en cours), crédits (semaine, mois, projection, tendance), intégrité ; page autonome en 600, gardée 90 jours ;
  la notification part avec les règles des alertes.
- `db.py` : colonnes ajoutées sans perte à une base existante ; agrégats journaliers par **jours entiers** (une
  heure d'un jour à cheval sur la limite était perdue : corrigé et testé). `EtatModule.depuis_dict` relit un état
  enregistré (CLI, page après redémarrage).
- Tests : 18 d'alertes, 9 du rapport et de la base.

Preuve (`./check.sh`) :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
All checks passed!
Success: no issues found in 41 source files
163 passed in 11.32s   (unitaires)
14 passed in 12.89s    (lecture seule)
41 passed in 1.96s     (adaptateurs)
19 passed in 3.29s     (empreinte + gardien)
TOTAL                                 3708     84    98%
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
CHECK OK
```

## P5 — 2026-10-08

- `vues.py` : une seule source pour la page, la CLI, l'iPhone et la barre des menus (`Source` : états publiés à
  chaque tour, base, registre, gardien, alertes) ; textes déjà caviardés ; les trois actions (nouvelle référence,
  pas normal, sourdine) et le diagnostic à la demande sont des méthodes explicites.
- `web/securite.py` : 127.0.0.1, jeton dans l'adresse (comparé en temps constant), Host exact (rebond DNS refusé),
  POST avec `X-Jeton`, corps JSON et Origin absente ou la nôtre, `Sec-Fetch-Site: cross-site` refusé ; CSP stricte
  sans `unsafe-inline` ni `unsafe-eval`, `Referrer-Policy: no-referrer`, pas de cadre, pas de cache.
- `web/serveur.py` : accueil, détail (7 / 30 jours), Crédits, Ressources, Intégrité, Journal (filtre par module),
  fragments, API JSON, SSE, fichiers statiques en liste fermée ; port 47615 ou le premier libre de 47616 à 47639,
  retenu dans les réglages ; aucun journal de requêtes (le jeton est dans l'adresse).
- `web/sse.py` (8 pages en direct au plus, battement 15 s), `web/rendu.py` + `templates/base.html`,
  `web/graphiques.py` (SVG : barres fines, courbe de 2 px, une mesure par graphique, infobulles, tableau des
  chiffres), `static/app.css` (clair et sombre, AA) et `static/app.js` (direct, actions, thème ; aucun script en
  ligne).
- Tests : 38 de sécurité (sans jeton ou faux jeton sur chaque adresse, 11 Host étrangers, Host absent, 6 Origin
  étrangères, `Sec-Fetch-Site`, `X-Jeton`, type du corps, méthodes, en-têtes partout, **vrai `lsof`** : écoute
  sur 127.0.0.1 seulement, rien de personnel dans les réponses, **aucune commande lancée sans POST** (espion),
  aucun jeton dans les journaux, chemins détournés, port pris) ; 14 de rendu (cartes, pastilles, détail, séries,
  vues, SSE, actions, vitesse < 300 ms, graphiques) ; 9 dans **Chromium sans fenêtre** (aucune erreur de console,
  contrastes AA mesurés sur chaque texte en clair et en sombre, 375 px sans défilement horizontal, clavier,
  direct, boutons avec confirmation, chargement < 300 ms).

Preuve (`./check.sh`) :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
All checks passed!
Success: no issues found in 47 source files
163 passed in 11.66s   (unitaires)
14 passed in 13.23s    (lecture seule)
41 passed in 3.77s     (adaptateurs)
19 passed in 5.07s     (empreinte + gardien)
38 passed in 21.10s    (page web : sécurité)
23 passed in 23.63s    (page web : rendu, direct, navigateur)
TOTAL                                 4420     98    98%
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
CHECK OK
```
