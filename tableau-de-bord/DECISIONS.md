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

## 2026-10-07 · P1 — Sondes

**D-11 · L'âge d'une entrée de file = la première fois que le tableau de bord l'a vue.** La date de modification
d'un fichier dit quand il a été écrit, pas quand il est arrivé (un PDF d'il y a un an déposé à l'instant) ; `ctime`
n'est pas fiable après un déplacement selon le système de fichiers. Le « premier vu » est gardé dans notre base
(juste à une minute près, et après un redémarrage). Seuls les fichiers déjà présents la toute première fois qu'on
regarde un dossier prennent leur `ctime`. Les pages que le Trieur écrit lui-même dans `BoiteMac/` (« Mon
coffre.html », « Derniers classements.html », « … (Trieur).html ») et les fichiers temporaires ne comptent pas ; un
fantôme iCloud (`.x.pdf.icloud`) compte, signalé « pas encore téléchargé », et n'est jamais téléchargé par nous.

**D-12 · Un journal : la pile d'appels appartient à sa ligne.** Une ligne datée suivie d'un `Traceback` (format de
l'assistant : « Plantage : … » puis la pile) compte **une** erreur ; une pile seule (sortie d'erreur brute
`demon.erreurs.log`) en compte une, avec sa dernière ligne (« ValueError: … ») comme message. Les erreurs sont
rangées par tranches de 5 minutes (1 h, 24 h et moyenne sur 7 jours exactes) ; le curseur et ces compteurs sont dans
notre base : un redémarrage ne recompte rien.

## 2026-10-07 · P2 — Registre et adaptateurs

**D-13 · Les attentes et plafonds, déduits des README et du code des modules (à vérifier, réglés chez eux d'abord).**

| Module | Attente | Tolérance | Plafond Claude | Lu chez le module (prime) |
|---|---|---|---|---|
| Quotidien | brief chaque jour vers 7h15 | 20 min | 2 $ | `reglages.toml` : `[heures] brief`, `[ia] budget_mensuel_usd` |
| Corvées | analyse chaque jour vers 21h | 60 min (reportée si batterie < 30 % ou Mac en veille) | 2 $ | `reglages.json` : `modules.corvees.analyse.heure`, `.ia.budget_mensuel_usd` |
| Trieur | aucun document en attente depuis plus de 15 min | — | 1 $ | `modules.trieur.ia.budget_mensuel_usd` |
| Bouclier | relève Gmail toutes les 5 min | 15 min | 2 $ | `config.toml` : `[gmail] active`, `intervalle_minutes`, `[ia] budget_mensuel_usd` |
| Nettoyeur | un relevé toutes les 2 min (surveillance allumée) | 10 min | — (pas de Claude) | `modules.demarrage.actif` |
| Assistant | — (voir D-15) | — | — (abonnement) | `claude.appels_max_par_jour` |
| Ambiance | — (voir D-14) | — | — | — |

Les files `BoiteMac/`, `Bouclier/entree/`, `Quotidien/entree/`, `~/Desktop/À trier/` (la mission) et
`~/Documents/À trier par l'assistant` (le vrai dossier du Trieur depuis son D-57) sont « bloquées » au-delà de
30 min (réglable).

**D-14 · Ambiance : adaptateur générique tolérant.** Ni son code ni son README ne sont dans ce dépôt. Labels attendus
`com.<session>.ambiance` et `.ambiance.audio`, dossiers `Application Support/Ambiance` et `Logs/Ambiance` ; un
battement et un coût du mois sont lus **s'ils existent** (clé `battement` ou `demon_battement` dans `meta`/`etat`,
table `depenses_ia` ou `couts` avec `cout_usd`). Pas d'attente ni de plafond tant qu'on ne les connaît pas : à
compléter dans `modules.toml` (ACTIONS_HUMAINES.md, facultatif).

**D-15 · Le tri Gmail n'a pas d'attente « toutes les 3 min ».** Il n'écrit rien quand il n'a rien à trier (ni dans le
journal, ni dans `memoire.db`) : une attente périodique donnerait de fausses alertes chaque nuit calme. On suit son
statut dans le superviseur (actif, en relance, désactivé) et la date du dernier mail trié. La carte « Assistant »
réunit le superviseur, l'icône, le tri Gmail et les appels à Claude.

**D-16 · Un module éteint ou en pause n'est pas une panne.** Corvées et le Nettoyeur sont éteints au départ, le
superviseur peut tout mettre en pause, Corvées a sa propre pause : la pastille est ⚪ avec la raison et la commande
pour rallumer, jamais une alerte.

**D-17 · Le registre est généré une fois, puis il est à toi.** Jamais réécrit : un module découvert plus tard est
**ajouté à la fin** ; un module connu que tu as retiré revient seulement s'il apparaît vraiment (son plist) ;
`actif = false` le fait ignorer ; `dossier_projet = "auto"` est déduit de la découverte à chaque fois (sans toucher
au fichier). Un fichier illisible : les modules connus sont surveillés quand même, le fichier n'est pas réécrit,
`tableau doctor` dit pourquoi.

**D-18 · Le battement : la base copiée, complétée par la date de ses fichiers.** Une petite base (moins de 4 Mo :
statuts, battements) est recopiée à chaque tour si elle a bougé ; une grosse (Corvées garde 30 jours d'événements)
au plus toutes les 10 minutes. Entre deux copies, la date de dernière écriture de la base (`stat`, sans l'ouvrir)
complète le battement lu dedans.

**D-19 · Le coût de l'assistant est un équivalent API.** Il passe par l'abonnement Claude Code : aucun dollar n'est
facturé à l'appel. Pour comparer, ses jetons (table `appels_claude`, appels réussis) sont multipliés par les tarifs
publics (relevés le 2026-10-06 dans la documentation d'Anthropic) ; les alias « haiku », « sonnet », « opus »
désignent la génération actuelle (`claude-haiku-5-5` 0,10/0,50 $, `claude-sonnet-5-5` 2/10 $, `claude-opus-5-5`
4/20 $ par million de jetons). Affiché « estimé », sans plafond ; le nombre d'appels du jour est comparé à
`appels_max_par_jour`.

## 2026-10-08 · P3 — Analyses

**D-20 · Le retard se compte en temps éveillé.** Un Mac qui dort ne fait rien, et ce n'est pas une panne : une
attente périodique, un battement figé se mesurent en minutes où le Mac était réveillé. Une attente quotidienne dont
l'échéance tombe pendant la veille a sa limite **reportée au réveil + tolérance** : le module a le temps de rattraper.
Une échéance d'avant la première fois où le tableau de bord a vu le module ne compte pas (pas de fausse alerte le
jour de l'installation).

**D-21 · Une trace jusqu'à 30 min avant l'heure compte.** Le brief de 7h15 fait à 6h50 est « tenu » ; fait la
veille au soir, non.

**D-22 · Le gardien relit tout une fois par jour.** Toutes les 30 min (et à chaque signal FSEvents), un fichier dont
la taille, la date et le numéro n'ont pas bougé n'est pas relu : le contrôle reste sous la seconde. Une fois par jour,
tout est relu, même ce qui paraît identique.

**D-23 · FSEvents attend 20 s de calme et ne marque que le bon module.** Une sauvegarde touche souvent plusieurs
fichiers : le contrôle part 20 s après le premier signal. Plusieurs modules partagent le dépôt de l'assistant : seul
celui dont le périmètre de code est touché est recontrôlé. Les fichiers vivants (bases, journaux, caches) ne
déclenchent rien.

**D-24 · Une pastille, une raison.** 🔴 si un problème grave, 🟡 si quelque chose à regarder ou si l'état est
inconnu, ⚪ si pas installé, éteint ou en pause (seul le code changé y est encore signalé), sinon 🟢. La phrase de
la carte est celle du premier problème, suivie de « (et N autres choses) ».
