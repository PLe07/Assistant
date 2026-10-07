# Décisions — Quotidien

Chaque choix ambigu, avec les alternatives écartées et la raison. Le plus récent en bas.

## 2026-10-07 · P0 — Reconnaissance et fondations

**D-01 · Quotidien vit dans le dossier `quotidien/` du dépôt de l'assistant, sans toucher un octet du reste.**
Cette session tourne dans un conteneur cloud dont le seul endroit qui survit est le dépôt GitHub de l'assistant
(branche de travail). Il n'y a pas de `~/Projets/quotidien` ici, et un `git init` séparé serait perdu (même constat
que Bouclier, D-01).
- Quotidien est un **projet autonome** : son `pyproject.toml`, son `.venv`, son `check.sh`, ses tests, son
  `.gitignore`, ses données (`~/Library/Application Support/Quotidien/`) et son LaunchAgent.
- **Aucun fichier existant n'est modifié** (ni l'assistant, ni `bouclier/`, ni le `.gitignore` racine) :
  l'empreinte d'intégrité le prouve à chaque `check.sh`.
- Sur ton Mac : `install.sh` fonctionne depuis `~/Assistant/quotidien` (après `git pull`) comme depuis une copie
  dans `~/Projets/quotidien`.
*Écarté :* un `git init` dans `quotidien/` (un dépôt dans le dépôt, que GitHub ne garderait pas) ; un module sous le
superviseur de l'assistant (il faudrait modifier son code et `reglages.json`, ce que la mission interdit).

**D-02 · Git : un commit par phase verte, sur la branche de travail du dépôt.**
`git rev-parse HEAD` du dépôt avance donc avec les commits de Quotidien. L'empreinte compare à la place l'**arbre
suivi hors `quotidien/`** (`git ls-tree -r HEAD`, filtré) et `git status` hors `quotidien/`, avec
`--no-optional-locks` (aucune écriture dans l'index d'un autre projet).

**D-03 · L'empreinte « avant » compare le code et les réglages, pas les données vivantes.**
Sur ton Mac, l'assistant, le Trieur et Bouclier tournent : ils écrivent sans cesse dans `donnees/`, `logs/`, leurs
bases `.db` et leurs caches. Sont comparés : chaque fichier de code et de réglages des projets (dont `bouclier/`),
l'arbre git, les plists des LaunchAgents et leur état launchd (chargé, en marche, dernier code de sortie — le numéro
de processus change à chaque démarrage du Mac et ne dit rien), les réglages dans
`~/Library/Application Support/<Projet>/`, `~/.zshrc`, `~/.zprofile`, `crontab -l`, la liste des dossiers iCloud
`BoiteMac/` et `Bouclier/`, `shortcuts list` (nos deux raccourcis exceptés), `docker ps -a` (nom, image, état — pas
la durée « Up 3 hours », qui change toute seule) et le nom et le nombre d'éléments de chaque liste de Rappels.
- Rappels : une liste de nom « Courses (menu) », « Anniversaires » (ou suffixée « (Quotidien) ») qui **n'existait
  pas** dans la référence est la nôtre et n'est pas comparée ; une liste de ce nom qui existait **avant** est celle
  de quelqu'un d'autre et reste comparée (élément par élément : son nombre).
- Ici : `integrite/etat_avant.json` (chemins du dépôt seulement, aucun nom personnel) est versionné.
- Sur ton Mac : `install.sh` prend `integrite/mac/etat_avant.json` **avant toute installation** (jamais sur GitHub :
  noms de LaunchAgents et de listes) et le compare à la fin. `verifier.sh` choisit le bon fichier.

**D-04 · Le dépôt est public : aucun prénom écrit dedans.**
Comme Bouclier (D-04), le label est construit à l'installation à partir de ton **nom de session macOS** :
`com.<session>.quotidien`, ce qui donne exactement `com.thibaut.quotidien` si ta session porte ton prénom. Réglable
dans `reglages.toml` (`[installation] prefixe_label`). `install.sh` vérifie que le label et la commande `quotidien`
sont libres avant d'installer.

**D-05 · Construit dans un conteneur Linux (constat du 2026-10-07).**
- Ici : Linux x86_64, Python 3.11.15, `docker` présent sans démon. Absents : `osascript`, `launchctl`, `shortcuts`,
  `plutil`, `security`, `brctl`, `sw_vers`, l'app Rappels, Contacts, iCloud.
- Ton Mac (relevé par les projets précédents) : MacBook Air arm64, macOS 27, Python 3.14 ; `install.sh` cherche
  `python3.14` … `python3.11` et refuse le `python3` 3.9 d'Apple (`tomllib` est dans Python 3.11+).
- Tout ce qui est natif (notifications, Rappels, Contacts, trousseau, presse-papiers, Messages, launchd, signature des
  raccourcis) passe par une seule interface (`quotidien/systeme.py`) : les tests vérifient les commandes construites ;
  `tests/e2e_mac` (marqués `reel`) les vérifient pour de vrai sur ton Mac, lancés par `install.sh`.

**D-06 · Le pare-feu du conteneur refuse Open-Meteo.**
`api.open-meteo.com` répond « 403 » au tunnel du conteneur de construction (politique réseau de l'environnement, pas
de Quotidien). Conséquences :
- le format de la réponse est relevé dans la documentation officielle d'Open-Meteo (paramètres, unités, et surtout :
  pluie et rafales d'une heure *h* = cumul et maximum **de l'heure précédente**) ; les fixtures du dépôt sont
  construites à ce format, y compris les jours de changement d'heure ;
- sur ton Mac, `install.sh` fait une **vraie** requête, en garde une capture anonymisée
  (`tests/meteo/fixtures/reelles/`, coordonnées arrondies) et rejoue toute la chaîne météo dessus
  (`tests/e2e_mac`) ; `quotidien doctor` affiche l'âge de la dernière prévision reçue.
- Quotidien demande `timeformat=unixtime` : chaque heure est un instant exact, converti en heure de Paris par
  `zoneinfo` ; aucune ambiguïté possible les nuits de changement d'heure.

**D-07 · Deux fichiers à toi, dans `~/Library/Application Support/Quotidien/`.**
`profil.toml` (le petit fichier : goûts, allergies, budget, jours chargés, trajets) et `reglages.toml` (ville,
heures, IA, listes de Rappels). Modèles commentés dans le projet : `profil.example.toml`, `reglages.example.toml`.
Un fichier illisible ou une valeur fausse est remplacé par la valeur par défaut, avec un message qui dit laquelle et
pourquoi (`quotidien doctor`). *Écarté :* les mettre dans iCloud (proches.toml contient des notes sur des personnes :
il reste dans le dossier privé du Mac).

**D-08 · Une allergie mal écrite n'est jamais ignorée.**
Une allergie hors des 14 allergènes réglementaires (« noix de pécan ») est signalée **et** ajoutée aux aliments
interdits (contrainte dure, comme une aversion) : une faute de frappe ne doit pas laisser passer un aliment dangereux.
