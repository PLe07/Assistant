# Rapport final — Tableau de bord

Le tableau de bord est construit, testé et prêt à installer. Il observe tes modules sans jamais les modifier. Ce
rapport donne, pour chaque point de la définition de « terminé » (§11), la preuve réelle (sortie collée) — ou, quand
la preuve ne peut venir que de ton Mac, la commande exacte qui la produit.

Construit dans un conteneur Linux (D-05) : pas de launchd, pas de barre des menus, pas d'iCloud ici. Tout ce qui ne
dépend pas du Mac est prouvé ici ; le reste est vérifié automatiquement par `install.sh` sur ton Mac.

## Définition de « terminé »

| Point (§11) | État | Preuve |
|---|---|---|
| Intégrité : comparaison finale avec `etat_avant.json` identique | ✅ ici et sur ton Mac (1565 fichiers, 11 LaunchAgents) | (1) et (6) |
| Lecture seule prouvée : faux écosystème vert, `lsof` propre, aucune trace | ✅ | ci-dessous (2) |
| `./check.sh --complet` vert | ✅ | ci-dessous (3) |
| Sécurité de la page validée | ✅ | 39 tests (4) |
| Performance tenue (chiffres mesurés) | ✅ ici, avec le faux écosystème | ci-dessous (5) |
| Démon actif, relancé après un kill ; barre des menus ; instantané iCloud | ✅ sur ton Mac (`install.sh`, étapes 5 à 8) | (6) |
| Premier état réel de tes modules | ✅ | (7) |
| README en français | ✅ | README.md |
| ACTIONS_HUMAINES.md minimal | ✅ | 1 étape indispensable, 2 facultatives |

## (1) Intégrité des autres projets

`integrite/verifier.sh` au début et à la fin de chaque `check.sh` (le dépôt hors `tableau-de-bord/` : HEAD, statut,
arbre suivi, SHA-256 de 730 fichiers de code et de réglages) :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
```

Aucun agent `com.<toi>.*` n'existe dans ce conteneur (0 LaunchAgent dans l'empreinte) ; sur ton Mac, `install.sh`
prend l'empreinte (LaunchAgents compris, avec leur état launchd) avant de rien poser et la compare à la fin.

## (2) Lecture seule : le faux écosystème (§9.1)

Le **vrai démon** (`python -m tableau demon`, comme par launchd) face à 7 faux modules **vrais processus** et 1 module
absent, avec un **espion d'audit Python dans le processus du démon** (toute écriture, suppression ou connexion SQLite
sous les dossiers des modules serait notée) :

```
tests/faux_ecosysteme/test_faux_ecosysteme.py .                          [100%]
1 passed in 374.09s (0:06:14)

{
  "detections_s": {
    "tdbtest-erreurs:pic_erreurs": 2.0,
    "tdbtest-budget:budget80": 2.0,
    "tdbtest-boucle:boucle": 12.0,
    "tdbtest-processeur:cpu": 32.1,
    "tdbtest-processeur:integrite": 22.1,
    "tdbtest-file:file": 62.3,
    "tdbtest-attente:attente:brief": 9.4,
    "tdbtest-budget:budget100": 58.2
  },
  "notifications": 5,
  "alertes": {
    "tdbtest-boucle:boucle": 2,
    "tdbtest-file:file": 2,
    "tdbtest-erreurs:pic_erreurs": 1,
    "tdbtest-budget:budget80": 1,
    "tdbtest-budget:budget100": 1,
    "tdbtest-attente:attente:brief": 2,
    "tdbtest-processeur:cpu": 2,
    "tdbtest-processeur:integrite": 2
  },
  "duree_s": 373,
  "espion": "vide",
  "lsof": "aucun fichier des modules",
  "verrous_vus_par_les_modules": 0
}
```

- Détection (secondes, à compter du début de chaque état ; < 120 exigé) : pic d'erreurs 2,0 s, budget 85 % 2,0 s, boucle de plantages 12,0 s, processeur élevé 32,1 s, code changé 22,1 s, file bloquée (seuil 1 min) 62,3 s, attente manquée 9,4 s, budget 102 % 58,2 s.
- Chaque alerte émise une fois ; la résolution une fois quand le module est réparé (boucle, file, attente,
  processeur, code) ; 0 alerte pour le module sain ; le module absent ⚪ sans alerte.
- Espion vide, `lsof` du démon sans aucun fichier des modules (échantillonné toutes les 20 s), aucun « database is
  locked » chez les modules (leurs bases WAL ont un délai d'attente nul), code des modules identique (SHA-256 et date)
  avant et après, plus aucun processus ni bac à sable à la fin (`finally`).
- Trois passages pour arriver au vert ; les défauts trouvés étaient dans le code, corrigés là (D-43, D-44).

## (3) `./check.sh --complet`

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
All checks passed!
Success: no issues found in 54 source files
172 passed in 13.16s                (unitaires)
16 passed in 13.41s                 (lecture seule)
44 passed in 5.54s                  (adaptateurs)
20 passed in 5.92s                  (empreinte + gardien)
39 passed in 21.86s                 (page : sécurité)
23 passed in 24.89s                 (page : rendu, navigateur)
20 passed in 20.46s                 (bout en bout)
1 passed in 374.09s (0:06:14)       (faux écosystème, §9.1)
1 passed in 1801.19s (0:30:01)      (performance 30 min, §9.5)
TOTAL                                 5325    134    97%
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 730 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
CHECK OK
```

## (4) Sécurité de la page (§9.3)

39 tests (`tests/securite/test_page.py`) : sans jeton ou faux jeton refusé sur chaque adresse ; 11 Host étrangers (dont
rebond DNS) et Host absent refusés ; Origin étrangère, `null`, `Sec-Fetch-Site: cross-site`, `X-Jeton` absent ou faux,
corps non JSON refusés sur un POST ; autres méthodes refusées ; en-têtes de protection sur toutes les réponses (CSP sans
`unsafe-inline` ni `unsafe-eval`) ; **vrai `lsof`** : écoute sur 127.0.0.1 seulement ; aucun e-mail ni chemin personnel
dans les réponses (une erreur brute en contient, la page la caviarde) ; **espion** : aucune commande d'un autre module
sans un POST explicite ; aucun jeton dans les journaux ; chemins détournés vers les fichiers statiques refusés ; port
pris → un autre, retenu. Instantané iPhone : recherche automatisée de motifs (e-mail, `/Users/`, jeton, clé, IBAN)
avant chaque écriture, testée sur 4 pièges. Navigateur (Chromium sans fenêtre) : aucune erreur de console, contrastes
AA mesurés sur chaque texte en clair et en sombre, 375 px sans défilement horizontal, navigation au clavier.

## (5) Performance (§9.5)

Le vrai démon, réglages normaux (un tour par minute), 30 minutes face au faux écosystème :

```
tests/perf/test_perf.py .                                                [100%]
1 passed in 1801.19s (0:30:01)

{
  "duree_min": 30.0,
  "cpu_pct": 0.227,
  "cpu_avec_commandes_pct": 0.326,
  "memoire_max_mo": 31.8,
  "memoire_debut_mo": 29.9,
  "memoire_fin_mo": 30.1,
  "page_mediane_ms": 3.9,
  "page_max_ms": 9.4,
  "tours": 30
}

exigé : processeur < 0,5 %, mémoire < 100 Mo et stable, page < 300 ms
```

Le processeur est celui du processus du démon ; « avec commandes » ajoute les `launchctl` qu'il lance (ici un faux
`launchctl` écrit en Python, plus lourd que le vrai). Sur ton Mac, `TDB_VRAI_LAUNCHD=1 ./check.sh --complet` refait la
mesure avec de vrais LaunchAgents de test (ACTIONS_HUMAINES §3).

## (6) Démon, relance, barre des menus, iCloud

- `install.sh` charge l'agent, affiche `launchctl print` (state, pid, runs), fait un **`kill -9`** du démon et attend
  que launchd le relance (nouveau pid), vérifie les tours et la page (avec et sans jeton), affiche `tableau etat`
  puis `tableau doctor`. Tout échec arrête l'installation avec la raison.
- Ici, sans launchd : `tests/e2e/` (démon de bout en bout sur un faux Mac vivant : 30 min sans fausse alerte, une
  panne → une alerte puis sa résolution, redémarrage sans doublon, veille de 8 h sans fausse alerte, disque plein,
  verrou d'instance, icône de la barre des menus et sa disparition sans plantage, instantané iCloud écrit en 600).

## Revue hostile (P10), deux passes

Cherché : une écriture accidentelle chez un autre module, un verrou SQLite, une fausse alerte au réveil, une alerte en
double, une fuite dans l'instantané iPhone, une faille de la page, un adaptateur fragile. Trouvé et corrigé (avec un
test chacun) :

| Trouvé | Corrigé |
|---|---|
| Un module en boucle de plantages donnait aussi « pic d'erreurs » et « attente manquée », puis un pic après sa fin | une panne, une seule alerte (D-43) |
| La file bloquée ignorait le seuil propre au module | appliqué par l'adaptateur de base (D-44) |
| Les passages d'un agent périodique comptaient comme des plantages | seulement pour les modules qui doivent tourner (D-55) |
| Sans rumps, le démon aurait planté en boucle au démarrage | il continue sans icône, le journal le dit (D-55) |
| Un registre pointant vers iCloud aurait fait lire (télécharger) un contenu | refusé partout (D-51) |
| Un arrêt pile pendant l'envoi pouvait doubler une notification | noter d'abord, envoyer ensuite (D-52) |
| Une base de 50 Mo recopiée toutes les 10 min (disque, batterie) | 50 Mo par heure au plus (D-53) |
| HEAD sur le direct, longueur de corps illisible | refusés proprement (D-54) |

Vérifié sans défaut : toutes les lectures chez les autres sont en `rb` ou par `stat`/`scandir` ; la seule connexion
SQLite hors de notre base est sur nos copies (refusée sinon) ; `launchctl`, `docker`, `git` passent par la liste
blanche (`list`/`print`, `ps`/`inspect`/`stats --no-stream`, `rev-parse`/`log`/`status` avec `--no-optional-locks`) ;
`healthz` de n8n en local sans mandataire ; aucune connexion sortante hors l'option du coût réel (éteinte).

## (6 bis) L'installation réelle sur ton Mac

```
▶ 2/8 Empreinte des autres projets (avant)
Empreinte « avant » écrite : 2 projet(s), 1565 fichiers, 11 LaunchAgent(s), 7 réglage(s) Application Support, 5 élément(s) divers
INTÉGRITÉ OK : identique à etat_avant.json (2 projet(s), 1565 fichiers, 11 LaunchAgent(s), 7 réglage(s) Application Support, 5 élément(s) divers)
▶ 5/8 Démarrage du démon (launchd)
  state = running
  runs = 1
▶ 6/8 Arrêt brutal, puis relance par launchd
  relancé tout seul : pid 38968 → 39177
▶ 7/8 Vérification : tours, page locale, premier état réel
  ✅ le démon fait ses tours
  ✅ page locale sur 127.0.0.1:47615, refusée sans jeton
▶ 8/8 Bilan
Démon : ✅ dernier tour à l'instant
Base : 0 Mo, droits 600
Réglages : OK
Registre : OK
Instantané iPhone : écrit (à l'instant)
Commandes de lecture : launchctl ✅, docker —, lsof ✅, git ✅, osascript ✅
INTÉGRITÉ OK : identique à avant_installation.json (2 projet(s), 1565 fichiers, 11 LaunchAgent(s), 7 réglage(s) Application Support, 5 élément(s) divers)
✅ Le tableau de bord est installé.
```

## (7) Premier état réel de tes modules

```
🟡 3 choses à regarder
Notifications : silence de nuit jusqu'à 8h

🟡 Assistant : 320 erreurs dans la dernière heure (et 1 autre chose)
🟡 Bouclier : « relève Gmail toutes les 5 min » : aucun passage depuis 1 j
🟢 Corvées : Tourne depuis 2 j · dernière analyse il y a 2 h 32
🟢 Nettoyeur : Tourne depuis 2 j · dernier inventaire du démarrage il y a 57 min
🟢 Quotidien : Tourne depuis 1 j · dernier brief parti il y a 16 h
🟢 Trieur : Tourne depuis 2 j · dernier document classé il y a 1 h 44
⚪ Ambiance : Pas installé
⚪ n8n : Pas installé
```

- 🟡 **Bouclier** : vrai. Sa relève Gmail n'a pas réussi depuis un jour (Bouclier n'en écrit la date qu'après une
  relève réussie). `bouclier doctor` dit pourquoi ; l'alerte le cite désormais elle-même (D-57).
- 🟡 **Assistant** : le nombre venait d'un défaut du tableau de bord à la première lecture des journaux (D-56), corrigé
  et testé ; reste « 1 autre chose » à lire avec `tableau module assistant`.
- 🟢 Corvées, Nettoyeur, Quotidien, Trieur ; ⚪ Ambiance et n8n ne sont pas installés sur ce Mac.
