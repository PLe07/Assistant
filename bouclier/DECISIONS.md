# Décisions — Bouclier

Chaque choix ambigu, avec les alternatives écartées et la raison. Le plus récent en bas.

## 2026-10-06 · P0 — Reconnaissance

**D-01 · Bouclier vit dans le dossier `bouclier/` du dépôt de l'assistant, sans toucher un octet du reste.**
Cette session tourne dans un conteneur cloud dont le seul endroit qui survit est le dépôt GitHub de l'assistant
(branche de travail). Il n'y a pas de `~/Projets/bouclier` ici, et un `git init` séparé serait perdu.
- Bouclier est un **projet autonome** : son `pyproject.toml`, son environnement `.venv`, son `check.sh`, ses tests,
  son `.gitignore`, ses données (`~/Library/Application Support/Bouclier/`) et son LaunchAgent.
- **Aucun fichier existant n'est modifié** : ni `requirements.txt`, ni `pyproject.toml`, ni `README.md`, ni
  `.gitignore` de l'assistant. L'empreinte d'intégrité (455 fichiers) le prouve à chaque `check.sh`.
- Sur ton Mac, tu peux le laisser dans `~/Assistant/bouclier` (après `git pull`) ou le copier dans
  `~/Projets/bouclier` : `install.sh` fonctionne depuis n'importe où.
*Écarté :*
- `modules/bouclier` sous le superviseur de l'assistant, comme le Trieur : il faudrait modifier `reglages.json`
  et le code de l'assistant, ce que la mission interdit (« ne modifie pas son code ») ;
- un `git init` dans `bouclier/` : un dépôt dans le dépôt, que GitHub ne garderait pas.

**D-02 · Git : un commit par phase verte, sur la branche de travail du dépôt.**
`git rev-parse HEAD` du dépôt avance donc avec les commits de Bouclier. L'empreinte compare à la place **l'arbre
suivi hors `bouclier/`** (`git ls-tree -r HEAD`, filtré) et `git status` hors `bouclier/` : les deux doivent rester
identiques. `git status` est lancé avec `--no-optional-locks`, pour ne jamais réécrire l'index d'un projet.

**D-03 · L'empreinte « avant » sépare le code et les réglages (comparés) des données vivantes (ignorées).**
Sur ton Mac, l'assistant tourne : il écrit sans cesse dans `donnees/`, `logs/`, ses bases `.db` et ses caches.
Les comparer donnerait de fausses alertes. Sont comparés : chaque fichier de code et de réglages (dont
`reglages.json`), l'arbre git, les plists des LaunchAgents et leur état launchd, les réglages dans
`~/Library/Application Support/<Projet>/`, `~/.zshrc`, `~/.zprofile`, `crontab -l`, l'empreinte de la liste de
`BoiteMac/` et celle de `shortcuts list` (nos deux raccourcis exceptés, une fois que tu les auras ajoutés).
- Ici : `integrite/etat_avant.json` (chemins du dépôt seulement, aucun nom personnel) est versionné.
- Sur ton Mac : `install.sh` prend `integrite/mac/etat_avant.json` **avant toute installation** (jamais sur
  GitHub : il contient des noms de LaunchAgents) et le compare à la fin. `verifier.sh` choisit le bon fichier.

**D-04 · Le dépôt est public : aucun prénom écrit dedans.**
La mission nomme le LaunchAgent `com.thibaut.bouclier`. Le prénom ne doit pas apparaître dans ce dépôt public
(même règle que le Trieur, D-01). `install.sh` construit le label à partir de ton **nom de session macOS** :
`com.<session>.bouclier`, ce qui donne exactement `com.thibaut.bouclier` si ta session s'appelle ainsi. Réglable
dans `config.toml` (`[installation] prefixe_label`).

**D-05 · Construit dans un conteneur Linux (constat du 2026-10-06).**
- Ici : Linux x86_64, Python 3.11.15, `ffmpeg` 6.1.1 et `ffprobe` présents, `perl` présent.
- Absents ici : `sw_vers`, `shortcuts`, `automator`, `brctl`, `plutil`, `osascript`, `security`, `launchctl`,
  `exiftool`, `tesseract`, `sqlite3` (la bibliothèque Python suffit).
- Ton Mac (relevé par les projets précédents) : MacBook Air arm64, macOS 27.0.1, Python 3.14.4 dans le `.venv` de
  l'assistant, `pyobjc-framework-Vision` installé. Navigateurs, `exiftool`, `ffmpeg` et iCloud Drive : vérifiés par
  `bouclier doctor` sur le Mac.
- Tout ce qui est natif (notifications, trousseau, Corbeille, iCloud, Vision, raccourcis, Automator, launchd) passe
  par `bouclier/systeme.py` : les tests vérifient les commandes construites ; `tests/e2e_mac` les vérifie pour de
  vrai sur ton Mac.

**D-06 · Le réseau du conteneur ne laisse passer que PyPI et l'API Anthropic.**
`haveibeenpwned.com`, `rdap.org`, `openphish.com`, `urlhaus.abuse.ch`, `cybermalveillance.gouv.fr`,
`service-public.fr`… sont refusés par le pare-feu du conteneur (pas par Bouclier). Conséquences :
- HIBP, RDAP et les flux sont testés sur des réponses enregistrées au format officiel ; ils tournent pour de vrai
  sur ton Mac (premier tour du démon, puis `bouclier doctor`) ;
- les numéros et réflexes officiels sont vérifiés ici par une recherche limitée aux domaines officiels, puis
  **revérifiés automatiquement sur ton Mac** en lisant la page officielle elle-même (voir D-2x de P7).

**D-07 · Python 3.11 au minimum.**
Le SDK `anthropic` 1.x demande Python 3.10+, et `tomllib` (lecture de `config.toml`) est dans Python 3.11+.
`install.sh` cherche `python3.14` … `python3.11` (ton Mac a 3.14) et refuse le `python3` 3.9 d'Apple.

**D-08 · Gmail : pas de réutilisation possible, Bouclier aura son propre mot de passe d'application.**
Le module de tri de l'assistant passe par OAuth (`token.json`, `gmail.modify`), pas par IMAP ni par le trousseau.
La mission interdit de toucher aux fichiers de jetons d'un autre projet (un rafraîchissement les réécrirait).
Bouclier se connecte donc en IMAP avec **son** mot de passe d'application, rangé dans **son** élément de trousseau
`bouclier-gmail` (ACTIONS_HUMAINES.md). Sans lui : surveillance et inventaire Gmail en mode dégradé, le reste marche.

**D-09 · L'IA : le SDK officiel avec une clé, sinon ton abonnement par Claude Code.**
- Modèle par défaut : `claude-haiku-4-5` (le plus économique : 1 $ / 5 $ par million de jetons d'entrée / sortie,
  d'après la documentation embarquée du SDK, relevée le 2026-10-06). La mission demande « un modèle économique ».
- 1er moyen : le SDK `anthropic` avec `ANTHROPIC_API_KEY`, ou la clé rangée dans le trousseau (`bouclier-anthropic`).
  launchd n'héritant pas du shell, le démon lit le trousseau.
- 2e moyen (si pas de clé) : `claude -p` avec le jeton de ton abonnement rangé dans `bouclier-claude` (même
  méthode que l'assistant, sans lire ni modifier son `.env`).
- Plafond : 2 $ par mois, estimé avant chaque appel et compté après (prix de la config).

**D-10 · La liste blanche du réseau est appliquée deux fois.**
`reseau.telecharger` refuse toute adresse hors liste (et toute redirection hors liste) ; `reseau.installer_garde`
refuse toute résolution de nom hors liste dans tout le processus (bibliothèques comprises). Les tests coupent le
réseau et échouent si un hôte hors liste est seulement tenté. RDAP : seul le serveur désigné par une redirection
de rdap.org, en HTTPS, pour l'adresse `…/domain/<le domaine demandé>`, est permis.
