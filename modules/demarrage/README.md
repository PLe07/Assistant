# 🧹 Le Nettoyeur de démarrage

Il répond à trois questions sur ton Mac :
1. **Qu'est-ce qui se lance tout seul ?** Démarrage, ouverture de session, tâches de fond, extensions, cron.
2. **Qu'est-ce que ça coûte vraiment ?** Le processeur à l'ouverture de session et en continu, la mémoire,
   l'énergie, et la mise en veille empêchée.
3. **Quoi garder, couper ou nettoyer ?** Avec une commande réversible pour chaque élément.

Tout se fait sur ton Mac, sans Internet, sans IA, sans crédit Claude. **Il recommande, tu décides** : rien n'est
désactivé sans ta commande, et tout se défait.

## Les commandes

Depuis `~/Assistant` : `.venv/bin/python demarrage.py <commande>`. Si tu as ajouté le raccourci (voir
ACTIONS_HUMAINES.md), c'est simplement `demarrage <commande>`. `python assistant.py demarrage <commande>` marche
aussi.

| Commande | Ce qu'elle fait |
|---|---|
| `demarrage scan` | l'inventaire complet (une dizaine de secondes la première fois, puis 1 à 2 s) |
| `demarrage mesurer --minutes 10` | une mesure intensive maintenant : un relevé toutes les 5 s |
| `demarrage rapport` | écrit et ouvre le rapport (le classement, les verdicts, les commandes) |
| `demarrage desactiver ID` | montre ce qui serait fait, sans rien toucher |
| `demarrage desactiver ID --confirmer` | le fait : réversible, noté au journal |
| `demarrage restaurer ID --confirmer` | défait exactement ce qui avait été fait |
| `demarrage historique` | tes actions, et tes ouvertures de session une à une |
| `demarrage surveiller on` / `off` | la surveillance en fond (mesure à chaque connexion, alerte si un programme s'ajoute) |
| `demarrage doctor` | ce qui marche, ce qui est dégradé et pourquoi |

`ID` est l'identifiant à 8 caractères affiché dans le rapport. Son début (4 caractères au moins) ou le label
complet suffisent.

## Lire le rapport

- **En haut**, le résumé : combien d'éléments se lancent, combien te coûtent vraiment, et ce que tu gagnerais en
  coupant les 💤 et 👻.
- **La courbe** suit chaque ouverture de session :
  - « démarrage → connexion » : le temps entre l'allumage du Mac et ton arrivée sur le bureau ;
  - « connexion → calme » : le temps qu'il faut ensuite pour que le processeur se calme.
  C'est surtout la seconde courbe qui baisse quand tu coupes des éléments lourds.
- **Le classement**, par impact (0 à 100). Chaque fiche donne :
  - qui l'a fait (la signature) et ce qu'il fait ;
  - ses mesures ;
  - la dernière fois que tu as ouvert l'app ;
  - le verdict, avec sa raison ;
  - dans « Où il est, et comment agir » : la commande pour agir et celle pour annuler.
- **Les verdicts** :
  | Verdict | Sens |
  |---|---|
  | 🍎 Apple | fait partie de macOS. Jamais d'action, sous aucun prétexte. |
  | ✅ Utile | à garder : il sert, ou il ne coûte presque rien. |
  | 💤 Inutile au démarrage | l'app reste installée, elle ne se lance juste plus toute seule. |
  | 👻 Orphelin | le reste d'une app désinstallée : il pointe vers un programme qui n'existe plus. |
  | ⚠️ Inconnu | éditeur inconnu, pas de signature, ou un nom d'Apple sans signature d'Apple. À vérifier, jamais à supprimer à l'aveugle. |
- **« Impact … estimé »** : l'élément n'a pas encore été mesuré, la valeur vient de la base de connaissances.
  Lance `demarrage mesurer`, ou allume la surveillance.

## Ce que fait vraiment « desactiver … --confirmer »

| Élément | Ce qui est fait | Pour annuler |
|---|---|---|
| Agent de ta session (`~/Library/LaunchAgents`, ou intégré à une app) | `launchctl bootout` puis `launchctl disable` ; le fichier reste en place | `restaurer` : `enable`, puis `bootstrap` s'il tournait |
| Orphelin dans `~/Library/LaunchAgents` | son fichier part en quarantaine (`donnees/demarrage/quarantaine/…`), jamais effacé | `restaurer` le remet en place |
| App ouverte à la connexion | retirée de la liste par System Events (si tu l'as autorisé), sinon le chemin dans les Réglages | `restaurer` la remet |
| Pour tous les comptes (`/Library`), service système, extension, cron | rien d'automatique : la commande exacte à taper toi-même, et celle pour annuler | — |
| 🍎 Apple, ou l'Assistant lui-même | refusé | — |

Avant d'agir, il relit l'état actuel : ce qui est déjà fait n'est pas refait, et ce que tu as changé à la main est
respecté.

## La surveillance en fond

`demarrage surveiller on`. Le superviseur de l'Assistant la lance et la relance si besoin (il faut avoir fait
`python service.py installer` une fois, comme pour les autres modules). Elle :
- mesure chaque ouverture de session : un relevé toutes les 5 s pendant 5 min, puis toutes les 2 min ;
- refait le scan chaque jour, et tout de suite si un dossier de démarrage change ;
- t'envoie une notification si un nouveau programme se met à démarrer tout seul, par exemple « ⚠️ Nouveau
  programme au démarrage : Zoom Updater (Zoom Video Communications) » ;
- t'envoie un récap par semaine, seulement s'il y a un élément lourd qui ne sert à rien.
Au plus une notification par jour, jamais entre 23 h et 8 h.

Elle consomme moins de 0,3 % de processeur et moins de 40 Mo de mémoire.

## Désinstaller

- `demarrage surveiller off` : la surveillance s'arrête. Ce que tu as désactivé reste désactivé (`restaurer` si
  tu veux revenir en arrière).
- Pour effacer les mesures : supprime le dossier `~/Assistant/donnees/demarrage/`. Pense d'abord à `restaurer`
  ce qui est en quarantaine, si tu en as besoin.

## Pour les curieux

- Décisions : `DECISIONS.md`.
- Avancement et preuves : `PROGRESS.md`.
- Ce qui te reste à faire : `ACTIONS_HUMAINES.md`.
- Bilan : `RAPPORT_FINAL.md`.
- Démonstration du rapport : `demo/rapport_demo.html`.
