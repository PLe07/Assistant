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

## 2026-10-08 · P4 — Alertes et rapport

**D-25 · Une alerte se mérite : deux tours et 90 secondes.** Un problème vu une seule fois (un processus entre deux
relances, une copie de base ratée) ne réveille personne. Il disparaît depuis 150 s : il est réglé. Il revient avant :
rien n'a été dit, rien n'est répété.

**D-26 · Trois notifications par jour, ferme.** Ce qui dépasse attend le lendemain matin et ne part que si c'est
encore vrai (sinon la page et le journal le montrent). Le rapport de la semaine compte dans les trois. Une
notification que le Mac refuse d'afficher compte comme partie (la page la montre) : pas de nouvelle tentative en
boucle.

**D-27 · La nuit, seule une boucle qui consomme passe.** Une boucle de plantages est « qui consomme » si elle a
relancé au moins 2 × le seuil (6 fois en 10 min) ou si le processus dépasse 25 % de processeur. Le reste part à
8 h, en une seule notification. La sourdine retient tout, boucle comprise : c'est toi qui l'as demandée.

**D-28 · Un problème remplacé ne se « résout » pas.** La boucle devenue arrêt, le budget passé de 80 à 100 % :
l'ancien est clos sans message, le nouveau est annoncé. Un module que tu éteins : son alerte est close avec
« ⚪ … est éteint, en pause ou désinstallé ». Un code changé que tu acceptes : clos sans message.

**D-29 · Le rapport de la semaine est fait une fois, rattrapé au réveil.** Jamais pour une semaine observée moins
d'un jour (installation récente). « Bien tourné » = au moins 95 % des tours en 🟢 (hors ⚪). Les crédits de la
semaine = le total du mois maintenant moins celui du rapport précédent (fin du mois précédent comprise au
changement de mois) ; tendance « en hausse » au-delà de + 20 %, « en baisse » en dessous de − 20 %.

## 2026-10-08 · P5 — Page web

**D-30 · Une seule façon de dessiner : côté serveur.** Le direct (SSE) n'envoie qu'un numéro de version ; la page
recharge son propre fragment. Pas de second rendu en JavaScript qui pourrait diverger, et la page marche même si le
direct est coupé (un simple rechargement suffit).

**D-31 · Le jeton partout dans l'adresse, aucun cookie.** Feuille de style et script compris. Un cookie serait
partagé avec tout autre service sur 127.0.0.1 ; le jeton dans l'adresse ne fuit pas grâce à
`Referrer-Policy: no-referrer` et à l'absence de tout lien vers l'extérieur. La page d'erreur n'a aucun lien.

**D-32 · Une Origin absente est acceptée sur un POST, pas une Origin étrangère.** Les navigateurs envoient toujours
Origin sur un POST ; `curl` non. Le jeton reste exigé deux fois (adresse et `X-Jeton`), et le corps JSON oblige un
site étranger à une requête préalable que nous ne servons pas (`OPTIONS` → 405).

**D-33 · Graphiques dessinés en SVG, sans bibliothèque.** Une mesure par graphique (jamais deux axes), barres fines
posées sur la ligne de base, courbe de 2 px coupée là où le Mac n'a rien observé, infobulle par colonne et tableau
des chiffres pour chaque graphique. Rien à citer dans CREDITS.md pour les graphiques.

**D-34 · Le bandeau compte les choses à regarder, pas les modules.** Chaque problème d'un module 🔴 ou 🟡 compte ;
un module 🟡 sans problème précis (état inconnu) compte pour un.

**D-35 · Le diagnostic d'un module : sur ton clic, confirmé, un à la fois.** Une boîte de confirmation, puis
`executer_diagnostic` avec la preuve de ta demande ; sa sortie est caviardée avant d'être montrée. Deux clics
rapides ne lancent pas deux diagnostics.

## 2026-10-08 · P6 — Démon, barre des menus, iPhone, CLI

**D-36 · Un seul processus : le démon porte l'icône.** Sur le Mac, rumps tient le fil principal (exigence de macOS),
les tours tournent dans un fil à côté ; la page locale dans un troisième. Pas de bouton « Quitter » dans le menu :
launchd relancerait le démon aussitôt (`KeepAlive`), l'arrêt se fait par `./uninstall.sh`.

**D-37 · L'iPhone ne voit aucun texte venu d'un module.** Ni la phrase d'état (qui peut citer un nom de fichier),
ni l'activité : seulement pastilles, nombres (erreurs, documents en attente, choses à regarder) et crédits. Écrit
quand l'un d'eux change, sinon toutes les 15 minutes.

**D-38 · La CLI lit, le démon écrit.** La CLI lit notre base et le registre sans jamais réécrire le registre ; ses
seules écritures sont dans notre base (référence acceptée, sourdine). Elle marche démon arrêté et le signale.

**D-39 · « Rapport de la semaine » du menu : à la demande, à part.** Il couvre les 7 derniers jours jusqu'à
maintenant et va dans `rapports/a-la-demande/` ; le rapport du dimanche reste celui du dimanche.

**D-40 · Les tests du démon font vivre le faux Mac.** Un écosystème figé produirait de vraies attentes manquées au
bout de 15 minutes : chaque tour de test fait d'abord travailler les faux modules (battements, relève Gmail,
relevés). Les modules supervisés tournent vraiment : un petit superviseur de test lance de vrais processus
`python -m modules.<nom>`, tués à la fin du test.

## 2026-10-08 · P7 — Faux écosystème

**D-41 · Le juge fait tourner le vrai démon, comme sur ton Mac.** `python -m tableau demon` dans son propre processus,
avec sa vraie page, ses vrais tours et ses vraies commandes ; les 7 faux modules sont de vrais petits démons Python
(journal, base SQLite en WAL) gardés en vie par un launchd (le faux ici : KeepAlive, ThrottleInterval, `launchctl
list/print` au format de macOS ; le vrai sur ton Mac avec `TDB_VRAI_LAUNCHD=1`, agents `com.<ta session>.tdbtest.*`
retirés dans le `finally`). Un **espion d'audit Python dans le processus du démon** note toute écriture, toute
suppression et toute connexion SQLite sous les dossiers des modules : le fichier doit rester vide.

**D-42 · Réglages resserrés pour le juge, normaux pour la performance.** Le juge tourne en quelques minutes : un tour
toutes les 10 s, confirmation et résolution en 30 s, processeur élevé sur 1 min, boucle sur 3 min, file bloquée après
1 min pour le module « File » ; quota et silence de nuit levés (ils ont leurs tests propres). La mesure de
performance de 30 min garde les réglages normaux (un tour par minute). Les notifications du démon testé sont
coupées (`TABLEAU_NOTIFICATIONS=coupees`) : notées dans la base, jamais affichées.

**D-43 · Une panne, une seule alerte.** Le juge l'a montré : un module en boucle de plantages écrit une erreur à
chaque plantage et ne fait plus son travail. Pendant un arrêt, une boucle, un figement ou n8n injoignable, ni le pic
d'erreurs ni les attentes manquées ne font d'alerte à part : l'alerte de la panne dit déjà tout (le détail du module
continue de les montrer). Et dans l'heure qui suit la fin d'une boucle, ses erreurs ne font pas un « pic d'erreurs ».

**D-44 · `file_max_min` vaut pour toutes les files du module.** Le registre le promettait, seul l'adaptateur du
Trieur l'appliquait : l'adaptateur de base l'applique désormais à chaque file déclarée.

**D-45 · L'adaptateur `tolerant` pour tout futur module.** Celui d'Ambiance, qui lit s'ils existent un battement, des
dépenses et maintenant des preuves d'attente (`preuve:<id>` dans `meta` ou `etat`). Le README explique comment
déclarer un nouveau module avec lui.

**D-46 · « s'est arrêté N fois aujourd'hui ».** Le compte part de minuit : « depuis ce matin » était faux le soir.

## 2026-10-08 · P8 — Installation

**D-47 · L'installation agit seulement sur notre propre agent.** `install.sh` fait `bootstrap` de
`com.<toi>.tableau`, puis l'arrêt brutal (`kill -9` de **notre** démon) et vérifie que launchd le relance : c'est ce
que la mission demande (P8). La règle « launchctl print et list seulement » vaut pour le tableau de bord face aux
autres modules, et un test vérifie que les deux scripts n'appellent launchctl en écriture que sur notre label.

**D-48 · L'agent : RunAtLoad, KeepAlive, ThrottleInterval 30 s, Nice 10, entrées-sorties en priorité basse, session
graphique (Aqua).** L'icône de la barre des menus a besoin de ta session ; le démon ne tourne donc qu'une fois tu es
connecté, comme les autres agents de ta session.

**D-49 · La désinstallation ne laisse rien.** Agent, commande `~/.local/bin/tableau`, données, journaux, instantané
iCloud (et le dossier `Tableau` s'il est vide), `.venv` (seulement s'il a été créé par `install.sh`) ; la clé Admin
facultative seulement si tu dis oui. Ce qui n'est pas à nous (même nom, autre contenu) n'est jamais touché.

**D-50 · `etat.json` pour l'assistant.** Un résumé de quelques lignes (bandeau, pastille et phrase de chaque module,
caviardées) dans notre dossier, réécrit à chaque tour : l'assistant peut le lire sans rien appeler (INTEGRATION.md).
