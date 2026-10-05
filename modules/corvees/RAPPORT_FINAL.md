# Rapport final — Détecteur de corvées répétées

Construit du 5 octobre 2026, phases P0 à P10. Chaque preuve ci-dessous est la sortie réelle d'une commande.
Le détail de chaque étape est dans [PROGRESS.md](PROGRESS.md), et les choix dans [DECISIONS.md](DECISIONS.md).

Légende : ✅ fait et prouvé · ⏳ fait dans l'environnement de construction (Linux), à confirmer sur le Mac par
une action humaine ([ACTIONS_HUMAINES.md](ACTIONS_HUMAINES.md) §3).

## Définition de « terminé »

| | Critère | Statut |
|---|---|---|
| 1 | `check.sh` vert | ✅ |
| 2 | Simulation : 5 graines, plus le 2e jeu de corvées écrit après le réglage | ✅ 100 % de rappel et de précision partout |
| 3 | Zéro faux secret retrouvé | ✅ 0 sur 10 mondes simulés |
| 4 | Bout en bout réel | ✅ conteneur (vrais fichiers, vrai zsh) · ⏳ partie applis sur le Mac |
| 5 | Démon installé, actif, relancé après un kill | ✅ sous le vrai superviseur (conteneur) · ⏳ sur le Mac |
| 6 | CPU, RAM, temps d'analyse mesurés et dans les budgets | ✅ conteneur · ⏳ avec les capteurs du Mac |
| 7 | `corvees doctor` sans erreur bloquante | ✅ |
| 8 | README en français | ✅ [README.md](README.md) |
| 9 | ACTIONS_HUMAINES.md : seulement l'impossible sans toi | ✅ 2 actions obligatoires, 2 facultatives |

## 1. check.sh

```
$ PYTHON=.venv/bin/python modules/corvees/check.sh
▶ ruff check
All checks passed!
  ✅ ruff check
▶ ruff format
74 files already formatted
  ✅ ruff format
▶ mypy
Success: no issues found in 36 source files
  ✅ mypy
▶ pytest + couverture ≥ 85 %
Required test coverage of 85.0% reached. Total coverage: 98.52%
376 passed, 1 skipped, 1 deselected in 75.56s (0:01:15)
  ✅ pytest + couverture ≥ 85 %
▶ simulation (5 graines + 2e jeu)
16 passed in 27.75s
  ✅ simulation (5 graines + 2e jeu)
▶ performance
1 passed in 10.04s
  ✅ performance
CHECK OK
```

Le test ignoré (« skipped ») est la partie du bout en bout qui ouvre TextEdit et Calculette. Elle ne tourne que sur
le Mac, à la demande (`CORVEES_E2E_MAC=1`). Le test « deselected » est l'appel réel à Claude (`-m live`), qui
demande un jeton.

## 2. Simulation (§9.1)

Un mois de vie d'étudiant simulé : beaucoup de bruit, 10 corvées plantées, 4 pièges. Le jeu B (10 autres
corvées : autres applis, dossiers, horaires, sortes) a été écrit après le réglage du moteur, pour prouver qu'il
reste générique.

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

Critères demandés : rappel ≥ 90 %, précision ≥ 80 %. Par honnêteté, un lot final jamais vu (graines 1111 à 5555)
donne 49 corvées trouvées sur 50 : le jeu B, graine 3333, manque la corvée hebdomadaire du vendredi, avec 1 fausse
alerte (90 % / 90 %). Les critères restent tenus. Ce lot n'a pas servi à régler le moteur.

## 3. Zéro faux secret

Dans chaque monde simulé sont plantés de faux secrets (IBAN, `sk-ant-…`, `ghp_…`, mot de passe dans une commande,
e-mail, téléphone), ainsi qu'une activité dans des applis et des sites exclus. La recherche porte sur :
- chaque fichier du dossier du détecteur, octet par octet : base, journal SQLite, sel, propositions, rapport HTML ;
- la demande envoyée à Claude, avec un « Claude perroquet » qui recopie tout ce qu'il reçoit ;
- le journal.

| Jeu | Graine | Chaînes cherchées | Fichiers fouillés | Octets | Demandes à Claude fouillées | Trouvés |
|---|---|---|---|---|---|---|
| A | 101 | 12 | 24 | 1 287 689 | 1 | 0 |
| A | 202 | 12 | 24 | 1 324 471 | 1 | 0 |
| A | 303 | 12 | 24 | 1 259 017 | 1 | 0 |
| A | 404 | 12 | 24 | 1 320 375 | 1 | 0 |
| A | 505 | 12 | 24 | 1 279 519 | 1 | 0 |
| B | 101 | 12 | 24 | 1 269 708 | 1 | 0 |
| B | 202 | 12 | 24 | 1 314 631 | 1 | 0 |
| B | 303 | 12 | 24 | 1 249 192 | 1 | 0 |
| B | 404 | 12 | 24 | 1 302 344 | 1 | 0 |
| B | 505 | 12 | 24 | 1 261 637 | 1 | 0 |

```
Total trouvé : 0
Exemples de faux secrets plantés : 06 98 76 54 32, FR7630006000011234567890189, S3cretMdp!42,
ghp_fauxJetonGithub0123456789abcdef, hunter2-le-faux, prenom.nom@exemple-faux.fr
```

Le test de bout en bout plante aussi un faux mot de passe dans une vraie commande zsh : il n'est retrouvé nulle
part.

## 4. Bout en bout réel

Un vrai démon (watchdog, lecture de l'historique zsh) tourne dans un bac à sable (`~/CorveesSandbox`, HOME de
test). 5 fichiers sont vraiment créés puis rangés, et 5 commandes vraiment exécutées par zsh 5.9 avec un HISTFILE
de test. Ensuite :

```
$ corvees analyser --maintenant
🔎 Analyse des 30 derniers jours…
   2 corvée(s) repérée(s) en 0.0 s :
   [ugn5ie] Ranger les « Devis_*.pdf » dans Devis · ≈ 7 min/mois
   [diesag] Commande « cd ~/CorveesSandbox && ls -la » · ≈ 6 min/mois
(historique écrit par zsh)
1 passed, 1 skipped
```

Ce test a trouvé 3 défauts réels, corrigés (DECISIONS D-44) :
- une commande perdue dans la même seconde ;
- la sauvegarde par copie de zsh prise pour une réécriture ;
- le journal SQLite en 644.

⏳ **Sur le Mac** : la partie applis (TextEdit et Calculette alternées, puis refermées), par
`CORVEES_E2E_MAC=1 .venv/bin/python -m pytest tests/corvees/e2e`.

## 5. Démon installé, relancé après un kill

Le détecteur est un module de l'Assistant, lancé par son superviseur, lui-même un LaunchAgent avec `KeepAlive` et
`ThrottleInterval` de 30 s (D-02, D-46). Le test a été fait avec le vrai superviseur, sur une copie isolée de
l'Assistant :

```
avant : pid 605
relancé en 7 s : pid 1796
[superviseur] Module « corvees » tombé (code -9) : code de sortie -9 · relance dans 5 s
[superviseur] Module « corvees » lancé (pid 1796)
[corvees] Détecteur de corvées : 7 capteurs
```

Le délai d'essai était de 5 s ; en vrai, l'Assistant relance au bout de 1 minute.

⏳ **Sur le Mac** : `python service.py installer`, `python assistant.py activer corvees`, puis le `pkill` de
ACTIONS_HUMAINES §3.

## 6. Ressources

| Mesure | Budget | Résultat |
|---|---|---|
| CPU moyen du démon, 10 minutes avec une activité toutes les 15 s | < 1 % | **0,166 %** |
| RAM maximale du démon (10 minutes) | < 120 Mo | **29,4 Mo** |
| RAM maximale du démon pendant l'analyse de 208 426 événements | < 120 Mo | **23 Mo** (l'analyse tourne à part : pic de 129 Mo pendant 6,5 s, puis rendu) |
| Taille de la base après 10 minutes | < 200 Mo | 0,57 Mo |
| Analyse de 30 jours, 208 534 événements | < 10 s | **6,7 s** (machine de construction lente) |
| Écritures en base | groupées | toutes les 30 s |

```
$ python tests/corvees/perf/mesure_demon.py 600
{'pid': 605, 'duree_s': 601, 'cpu_moyen_pct': 0.166, 'ram_max_mo': 29.4, 'base_mo': 0.57}
✅ dans les budgets (CPU < 1 %, RAM < 120 Mo, base < 200 Mo)
```

⏳ **Sur le Mac** : la même commande, avec les capteurs propres au Mac allumés (appli au premier plan, fenêtres,
presse-papiers, inactivité).

## 7. doctor

```
$ python assistant.py corvees doctor ; echo "code $?"
🩺 Détecteur de corvées
   ✅ Module allumé
   ✅ Démon vivant (battement il y a 46 s)
   ⚠️ Capteur apps désactivé : pas sur un Mac
   ⚠️ Capteur fenetres désactivé : pas sur un Mac
   ✅ Capteur fichiers ok
   ✅ Capteur shell ok
   ⚠️ Capteur navigateur désactivé : aucun historique de navigateur trouvé
   ⚠️ Capteur pressepapiers désactivé : pas sur un Mac
   ⚠️ Capteur inactivite désactivé : pas sur un Mac
   ✅ Base : 125 événements · 0.6 Mo (plafond 200 Mo) · lisible par toi seul
   ✅ Dernière analyse : lun. 5 oct. à 12:56 · prochaine : lun. 5 oct. à 21:00
   ✅ Claude ce mois-ci : 0.00 $ sur 2.00 $
   ⚠️ Claude : jeton absent du .env (python assistant.py renouveler-jeton)
code 0
```

Les ⚠️ viennent de l'environnement de construction (Linux, sans navigateur ni jeton). Sur ton Mac, ces capteurs
s'allument.

## 8 et 9. README et actions humaines

- [README.md](README.md) : à quoi ça sert, commandes, pause, purge, désinstallation, confidentialité, réglages,
  dépannage.
- [ACTIONS_HUMAINES.md](ACTIONS_HUMAINES.md) :
  - 2 actions obligatoires : mettre à jour et allumer ; vérifier sur le Mac ;
  - 2 facultatives : Accès complet au disque pour Safari ; alias et options zsh.
  - L'autorisation Accessibilité est déjà donnée si la traduction marche chez toi.

## Écarts au cahier des charges (assumés, voir DECISIONS.md)

- **Un module de l'Assistant, pas un projet à part** (D-01).
  - Le code est dans `modules/corvees/`, les données dans `donnees/corvees/` et les réglages dans
    `reglages.json`. Il n'y a donc ni dossier `detecteur-corvees`, ni `config.example.toml`.
  - Pas d'`install.sh` ni d'`uninstall.sh` : ce sont `service.py installer` et
    `assistant.py activer` / `desactiver corvees`.
- **Pas de LaunchAgent à part pour le détecteur** (D-02) : le superviseur de l'Assistant le lance et le relance.
  En plus, aucun nom de personne n'apparaît dans le dépôt public.
- **Claude par l'abonnement** (Claude Code, `core.cerveau`), pas par une clé API (D-04, D-32). Le budget de 2 $
  est suivi en équivalent API.
- **Construit dans un conteneur Linux**. Les capteurs propres au Mac (NSWorkspace, Accessibilité, NSPasteboard,
  inactivité) sont testés avec des imitations ; leur vrai fonctionnement se vérifie sur le Mac
  (ACTIONS_HUMAINES §3).

## Défauts trouvés en conditions réelles et corrigés (P8 à P10)

Chacun a d'abord été reproduit par un test, puis corrigé.

| Défaut | Conséquence évitée |
|---|---|
| Deux commandes zsh dans la même seconde | la seconde était perdue |
| zsh sauve son historique par copie | des commandes perdues à chaque fermeture de terminal |
| Journal SQLite (-wal, -shm) en 644 | données lisibles par un autre compte du Mac |
| « Base occupée » prise pour « base abîmée » | le démon tombait et perdait ses événements en attente |
| Messages d'erreur non caviardés | un secret cité dans une erreur arrivait au journal |
| Deux notifications possibles au même instant | notification en double |
| Purge pendant la suite du soir | fichiers orphelins après la purge |
| Analyse à 317 Mo | budget de 120 Mo dépassé : l'analyse tourne maintenant à part, le démon reste à 23 Mo |
| Seuils encore codés en dur | tous dans la config |
