# Décisions — Tableau de bord

Chaque choix ambigu, avec les alternatives écartées et la raison. Le plus récent en bas.

## 2026-10-07 · P0 — Reconnaissance et fondations

**D-01 · Le tableau de bord vit dans le dossier `tableau-de-bord/` du dépôt de l'assistant, sans toucher un octet du
reste.** Cette session tourne dans un conteneur cloud dont le seul endroit qui survit est le dépôt GitHub de
l'assistant (branche de travail). Un `git init` dans `~/Projets/tableau-de-bord` serait perdu (même constat que
Bouclier et Quotidien, D-01).
- C'est un **projet autonome** : son `pyproject.toml`, son `.venv`, son `check.sh`, ses tests, son `.gitignore`, ses
  données (`~/Library/Application Support/TableauDeBord/`) et son LaunchAgent.
- **Aucun fichier existant n'est modifié** (ni l'assistant, ni `bouclier/`, ni `quotidien/`, ni le `.gitignore`
  racine) : l'empreinte d'intégrité le prouve à chaque `check.sh`.
- Sur ton Mac : `install.sh` fonctionne depuis `~/Assistant/tableau-de-bord` (après `git pull`) comme depuis une
  copie dans `~/Projets/tableau-de-bord`.
*Écarté :* un dépôt git dans le dépôt (GitHub ne le garderait pas) ; un module sous le superviseur de l'assistant
(il faudrait modifier son code et `reglages.json`, ce que la mission interdit).

**D-02 · Git : un commit par phase verte, sur la branche de travail.** `git rev-parse HEAD` du dépôt avance donc avec
nos commits. L'empreinte compare à la place l'**arbre suivi hors `tableau-de-bord/`** et `git status` hors de notre
dossier, avec `--no-optional-locks` (git ne réécrit pas l'index d'un autre projet). HEAD au départ : `8c7ba63`
(« Quotidien P8-P10 »).

**D-03 · L'empreinte « avant » compare le code et les réglages, pas les données vivantes.** Sur ton Mac, l'assistant,
le Trieur, Bouclier et Quotidien écrivent sans cesse dans `donnees/`, `logs/`, leurs bases `.db`, leurs `etat.json`
et leurs caches. Sont comparés : le SHA-256 de chaque fichier de code et de réglages de chaque projet, HEAD et
`git status` (hors journaux et bases suivis par erreur), les plists des LaunchAgents et leur état launchd (chargé, en
marche, dernier code de sortie — pas le numéro de processus), les réglages dans `Application Support/<Projet>/`
(sans les `etat.json`, `brief.json` et caches réécrits en tournant), `~/.zshrc`, `~/.zprofile`, `crontab -l`,
`shortcuts list` et `docker ps -a` (nom, image, état — pas la durée « Up 3 hours »).
- La **liste des fichiers** des dossiers iCloud (`BoiteMac/`, `Bouclier/`) n'est pas comparée : un document que tu
  envoies depuis l'iPhone pendant `check.sh` n'est pas un changement de code (Quotidien la comparait ; ici elle
  aurait donné de fausses alertes d'intégrité).
- Nos agents de test `com.<x>.tdbtest.*` **sont** comparés (absents avant, ils doivent l'être après) ; notre propre
  label `com.<x>.tableau` et notre dossier `TableauDeBord` ne le sont pas (créés par notre installation).
- Ici : `integrite/etat_avant.json` (chemins du dépôt seulement) est versionné. Sur ton Mac : `install.sh` prend
  `integrite/mac/etat_avant.json` **avant toute installation** (jamais sur GitHub) ; `verifier.sh` choisit le bon.

**D-04 · Le dépôt est public : aucun prénom écrit dedans.** Comme Bouclier et Quotidien (D-04), les labels sont
construits à partir de ton **nom de session macOS** : notre agent est `com.<session>.tableau`, et la découverte
cherche `com.<session>.*` (donc exactement `com.<ton prénom>.*` si ta session porte ton prénom). Réglable :
`reglages.toml` → `[installation] prefixe_label`. Les agents de test sont `com.<session>.tdbtest.*`.

**D-05 · Construit dans un conteneur Linux (constat du 2026-10-07).**
- Ici : Linux x86_64, Python 3.11.15, `lsof` et `ps` présents, `docker` présent **sans démon**, Chromium et
  Playwright 1.56 présents. Absents : `launchctl`, `osascript`, `pmset`, `security`, `brctl`, rumps, iCloud.
- Toute commande du Mac passe par une seule porte, `tableau/systeme.py`, avec une **liste blanche** (D-09).
- Le faux écosystème (§9.1) ne peut pas créer de vrais LaunchAgents ici : il utilise un **faux launchd** qui lance
  et relance pour de vrai les faux modules (KeepAlive, ThrottleInterval) et répond à `launchctl list` et
  `launchctl print` au format de macOS ; le tableau de bord, lui, tourne sans modification. Sur ton Mac, le même
  test utilise de vrais LaunchAgents `com.<session>.tdbtest.*` (marqué `mac`, lancé par `install.sh`).

**D-06 · Échantillons réels : ceux qui existent ici, plus ceux de ton Mac à l'installation.**
- Ce conteneur contient de **vraies** sorties du code de l'assistant (tests et essais des sessions précédentes) :
  `logs/assistant.log` (9 761 lignes), `donnees/etat.db`, `donnees/trieur/trieur.db`. Elles sont **copiées**, puis
  anonymisées (noms de fichiers, chemins, e-mails, textes libres) dans `tests/fixtures/reelles/conteneur/`.
- Corvées, Nettoyeur, Bouclier et Quotidien n'ont pas de données ici : leurs échantillons sont **déduits de leur code
  source** (schémas recopiés à l'identique de leur `db.py`, formats de journal de leur `journal.py`) et de leurs README.
- Ambiance n'a ni code ni README dans ce dépôt : adaptateur générique tolérant (D-12).
- Sur ton Mac, `install.sh` capture les vrais échantillons dans `tests/fixtures/reelles/mac/` (jamais sur GitHub)
  et rejoue dessus les tests des adaptateurs.
- Les bases d'échantillon sont gardées en **SQL rejouable** (`.sql`), pas en `.db` : lisibles, comparables, et
  rien de binaire dans le dépôt.

**D-07 · Corvées, Nettoyeur, Trieur et le tri Gmail ne sont pas des LaunchAgents à eux.** La mission les nomme
`com.<prénom>.corvees`, `.nettoyeur`, `.trieur` ; dans le code réel, ils tournent **sous le superviseur de
l'assistant** (`com.assistant.superviseur`), qui les lance en `python -m modules.<nom>` (`corvees`, `demarrage` pour
le Nettoyeur, `trieur`, `mails` pour le tri Gmail), les relance s'ils tombent, et publie leur statut dans
`donnees/etat.db` (table `modules`) et `logs/assistant.log` (`[composant]` sur chaque ligne).
- Chaque adaptateur gère les deux cas : un plist `com.<session>.<module>` existe → on le suit comme un LaunchAgent ;
  sinon → processus fils du superviseur, statut du superviseur (copie de `etat.db`), plantages lus dans le journal
  (« Module « trieur » tombé (code 1) »).
- Bouclier (`com.<session>.bouclier`) et Quotidien (`com.<session>.quotidien`) sont de vrais LaunchAgents.

**D-08 · Port local 47615.** Non attribué, loin de n8n (5678, refusé dans les réglages). S'il est pris au démarrage :
premier port libre de 47616 à 47639, retenu dans `reglages.toml` (seule la ligne du port est réécrite).

**D-09 · Lecture seule par construction.** `systeme.executer` refuse toute commande hors liste blanche :
`launchctl list|print`, `docker ps|inspect|stats --no-stream`, `git --no-optional-locks rev-parse|log|status`, `ps`,
`lsof`, `pmset -g`, `sysctl -n`, une notification, l'ouverture de notre page, la lecture de notre clé (facultative)
dans le trousseau. Le diagnostic d'un autre module a sa propre porte (`executer_diagnostic`), qui exige une
`DemandeExplicite` (ton clic avec le jeton, ou ta commande dans le Terminal). 35 commandes interdites sont testées
(bootstrap, bootout, kickstart, kill, enable, disable, load, unload, docker restart/stop/exec, git checkout/reset…).

**D-10 · Les bases des autres : copiées, jamais ouvertes, et pas trop souvent.**
- Copie octet par octet de `.db`, `-wal`, `-shm` dans `Application Support/TableauDeBord/copies/`, taille/date/inode
  relevés avant et après (la base a bougé → recopie avec 0,2 s, 0,5 s, 1 s, 2 s, 4 s d'attente), `PRAGMA
  quick_check` sur la copie, copie effacée aussitôt. Ouverture refusée hors de notre dossier de copies.
- Une base n'est recopiée que si elle a bougé et au plus toutes les 10 min (`intervalles.copie_base_s`) : Corvées
  garde 30 jours d'événements, la recopier chaque minute coûterait du disque et du processeur. Entre deux copies, le
  battement d'un module se lit dans la **date de ses fichiers** (`stat`, sans rien ouvrir).
- Base de plus de 256 Mo ou disque presque plein : pas de copie (« inconnu » pour ce qui en dépend), pas de plantage.
- Preuve : un « module » écrit sans arrêt dans sa base WAL (délai de verrou de 50 ms de son côté) pendant 30 lectures :
  0 « database is locked » vu par le module, 0 plantage, original identique octet pour octet, aucun fichier créé.
