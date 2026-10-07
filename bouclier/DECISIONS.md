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
La mission nomme le LaunchAgent avec ton prénom. Le prénom ne doit pas apparaître dans ce dépôt public
(même règle que le Trieur, D-01). `install.sh` construit le label à partir de ton **nom de session macOS** :
`com.<session>.bouclier`, ce qui donne exactement le nom demandé si ta session porte ton prénom. Réglable
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

**D-11 · Analyse locale : des indices pondérés et expliqués, le texte ne peut qu'ajouter des points.**
Chaque indice (`Signal`) a un poids et une phrase en français simple. Seuls des faits techniques vérifiés
(expéditeur authentifié par le serveur qui a reçu le mail, site ancien) retirent des points : un message ne peut pas
« se blanchir » en parlant. Score 0–100 → 🔴 ≥ 70, 🟠 ≥ 45, 🟡 ≥ 20, ⚪ sinon. Un indice critique (lien déjà
signalé, lien déguisé par « @ », sosie qui demande de payer, demande de code, de valider une opération, coursier,
injection) tient le verdict à 🟠 au moins ; deux indices critiques donnent 🔴. La pression psychologique est
plafonnée à 20 points (elle existe aussi dans les vrais messages).

**D-12 · Une famille d'arnaque demande un thème, une accroche ET un moyen d'agir.**
Un vrai SMS de livraison sans demande d'argent, une vraie alerte bancaire sans lien ni numéro restent ⚪. Une accroche
dans une phrase négative (« ne communiquez jamais ce code ») est une mise en garde et ne compte pas. À égalité, une
famille précise (colis, annonce…) l'emporte sur une famille fourre-tout (banque, support, impayé) pour l'explication.

**D-13 · Les marques : une liste fermée de sites officiels, et trois manières d'imiter.**
56 marques visées en France (livraison, administrations, banques, annonces, abonnements, énergie, santé, commerce),
chacune avec ses sites officiels ; tout `*.gouv.fr` est officiel pour les administrations. Un sosie « contient » la
marque, la « déforme » d'une ou deux lettres (nom enregistré seulement, mots courants exclus : « email » n'imite pas
« gmail », « party » n'imite pas « darty »), ou la copie avec des « caractères » trompeurs (cyrillique, accent,
« rn » pour « m », chiffres).

**D-14 · Numéros et sites officiels : un registre unique, vérifié deux fois.** (2026-10-06)
`bouclier/urgence/sources.json` liste chaque numéro (15, 17, 18, 112, 114, 33700, opposition 0 892 705 705,
Info Escroqueries, centre antipoison et CHU de Bordeaux, 3237) et chaque site (17Cyber, signal-spam.fr, THESEE,
Perceval…) avec ses pages officielles. Le conteneur de construction n'accède pas à ces sites (proxy) : les pages ont
été lues le 2026-10-06 par un moteur de recherche limité aux domaines officiels (aucun numéro tiré de la mémoire).
Sur le Mac, `bouclier urgence verifier` retélécharge chaque page et vérifie que le numéro (et un mot-clé) y figure :
un numéro qu'aucune page ne mentionne plus est signalé puis retiré. SOS Médecins Bordeaux est **exclu** : aucune page
d'un site officiel permis ne le donne. Les ARS (`*.ars.sante.fr`, pharmacies de garde) rejoignent la liste blanche.
Un numéro officiel payant (0 892 705 705) n'est pas compté comme « numéro surtaxé piège » par le détecteur.

**D-15 · L'IA : JSON validé, nombre aléatoire dans les balises, phrases filtrées.**
Le message part caviardé dans `<message_non_fiable_XXXX>` où XXXX est tiré au hasard à chaque appel : un escroc ne
peut pas fermer la balise. Toute balise de ce nom présente dans le message est retirée. Le texte caché d'un mail
n'est jamais envoyé. Le schéma pydantic n'a pas de niveau « sûr ». Les phrases de l'IA ne sont affichées que si
elles ne rassurent pas, ne contiennent ni lien ni numéro, ni jargon ; les gestes viennent toujours de
`reflexes.json`, jamais de l'IA. Texte limité à 4 000 caractères, 400 jetons de réponse : environ 0,003 $ l'appel.

**D-16 · Le veto : l'IA monte librement, descend d'un niveau au plus.**
Sans indice critique, l'IA peut baisser d'un seul niveau, et seulement si elle est sûre d'elle (confiance ≥ 0,6).
Avec un indice critique, jamais sous 🟠. Alternative écartée : laisser l'IA trancher (une IA trompée par une
injection non repérée rendrait « Pas de signe »). Vérifié sur les 305 messages × 4 avis contradictoires.

**D-17 · `claude -p` comme l'assistant, et jamais dans les tests.**
Même ligne de commande que l'assistant (éprouvée sur ton Mac) : sans outil, sans session gardée, dans un dossier
vide, clé API retirée de l'environnement. Les tests remplacent la recherche du programme `claude` ; le test réel
(`-m reel`) ne tourne que sur macOS (il a tenté une fois le Claude du conteneur de construction : corrigé).

**D-18 · Les raisons affichées : les indices critiques d'abord, puis les plus lourds.**
Ainsi « Il te demande de payer 1,99 € » passe avant « .top », comme dans l'exemple du §3.4.

**D-19 · La base des services vient de deux bases ouvertes, avec une liste française par-dessus.** (2026-10-06)
Plutôt que d'écrire des liens de suppression de mémoire (risque d'erreur), `outils/importer_bases.py` fusionne :
JustDeleteMe (liens de suppression, difficulté ; licence MIT) et 2factorauth (double authentification, catégories ;
licence MIT), avec 278 services courants en France choisis à la main (nom, catégorie, domaines). Résultat :
2 814 services, dont 326 courants en France et **163 avec un lien direct de suppression** (≥ 150 demandés).
Les comptes de services publics sont marqués « ne se supprime pas ». Licences et versions dans CREDITS.md.
Alternative écartée : télécharger ces bases sur le Mac (hors liste blanche du réseau).

**D-20 · Inventaire : en-têtes seulement, les personnes exclues, ton statut jamais touché.**
Seuls FROM, SUBJECT, DATE et LIST-UNSUBSCRIBE sont lus (par lots de 500, en reprenant au dernier message vu ; un
changement d'UIDVALIDITY fait tout reprendre). Une adresse de messagerie personnelle (gmail.com, orange.fr…) ou ton
propre domaine n'est jamais un « service ». Les en-têtes en UTF-8 brut (RFC 6532) sont décodés : bogue trouvé par
le test des 60 services (rappel 62 % → 100 %). Le lecteur IMAP n'envoie que LIST, EXAMINE, UID SEARCH et UID FETCH
avec des éléments qui ne marquent rien (BODY.PEEK, FLAGS…) : tout le reste est refusé avant envoi.
Le trousseau n'est lu que pour nos propres éléments `bouclier-…` (vérifié par un test).

**D-21 · Fuites : liste publique HIBP une fois par jour, croisée en local, une notification par fuite.**
La liste `/api/v3/breaches` (sans clé, User-Agent identifiable, attribution CC BY 4.0 affichée) est retéléchargée au
plus une fois toutes les 23 h ; une panne garde la copie précédente. Les fuites retirées, fabriquées ou de simples
listes de spam sont écartées. Correspondance par le service de l'inventaire (alias de marque compris :
forum.google.com → Google) ou par le domaine enregistrable. Filtre de date : une fuite antérieure au mail de
bienvenue du compte est écartée (date de création inconnue : la fuite est gardée, par prudence). Premier passage :
les fuites anciennes sont notées et résumées en **une** notification ; ensuite, une notification par nouvelle
fuite, jamais deux fois. Option payante (ta clé HIBP) : marque les fuites où ton adresse figure exactement.

**D-22 · Métadonnées : sans perte quand c'est possible, Python plutôt qu'exiftool.**
exiftool n'est pas sur ce Mac de construction et son archive officielle n'est pas sur la liste blanche du réseau :
Bouclier nettoie avec des bibliothèques Python (Pillow, pillow-heif, pikepdf, zip) et n'utilise exiftool, s'il est
déjà installé sur ton Mac, que pour **relire** le résultat (relecture indépendante). JPEG, PNG et WebP sans rotation
à appliquer sont nettoyés segment par segment, sans recompression (pixels identiques, vérifié) ; une photo tournée
(orientation ≠ 1) est remise à l'endroit puis réenregistrée en qualité 95 (SSIM ≥ 0,99, vérifié) ; TIFF et HEIC
sont réenregistrés à partir des pixels. Le profil ICC est toujours recopié. Les images annexes d'un JPEG (MPF, avec
leurs propres EXIF) sont jetées. Vidéos : `ffmpeg -map_metadata -1 -c copy` si ffmpeg est installé, sinon rien
n'est modifié et Bouclier le dit. Commentaires et révisions suivies d'un document Office : signalés, pas retirés.
Le lieu du rapport (« Bordeaux ») vient d'une petite liste de villes, sans réseau.

**D-23 · Fiche urgence : seulement des numéros sourcés, SOS Médecins exclu, rien de santé.**
Chaque numéro de la fiche vient du registre `sources.json` (D-14) ; un numéro que la dernière revérification n'a
retrouvé sur aucune de ses pages est retiré (notification une seule fois). SOS Médecins Bordeaux est exclu : aucune
page d'un site officiel permis ne le donne. Tes infos (`mes_infos_urgence.toml`) sont facultatives ; un champ vide
n'apparaît pas ; un texte qui ressemble à une donnée de santé (allergie, traitement, groupe sanguin…) est écarté et
signalé (la Fiche médicale de l'app Santé est faite pour ça). Sorties : HTML autonome, PDF A4, carte A6 d'une page,
image d'écran verrouillé 1179 × 2556 (iPhone 14 Pro à 16) seulement si tu as donné un texte ou un contact, copie du
PDF dans iCloud `Bouclier/`. Rappel « relis ta fiche » tous les 6 mois. pypdf rejoint les dépendances de test
(lecture du texte des PDF).

**D-24 · Raccourcis et entrées du Mac : la mécanique éprouvée du Trieur, avec nos propres noms.**
« Arnaque ? » donne à l'élément partagé un nom unique (`arnaque-<date>-<nombre>`), l'enregistre dans
`Bouclier/entree/`, puis lit `Bouclier/reponses/<nom>.txt` toutes les 3 s pendant 60 s ; sans réponse, il affiche les
5 réflexes de base écrits dans le raccourci. Un chemin relatif d'un raccourci désignant le dossier iCloud de l'app
Raccourcis (leçon du Trieur, D-12), le Mac surveille `iCloud Drive/Bouclier` ET `iCloud Drive/Shortcuts/Bouclier` et
répond dans le même dossier que l'entrée. « Envoyer sans traces » ne parle jamais au Mac (Convertir l'image en JPEG,
« Conserver les métadonnées » désactivé, puis Partager). Les actions rapides et le service « texte sélectionné »
reprennent la structure Automator de l'action du Trieur, avec l'identifiant `fr.bouclier.*` ; un paquet du même nom
qui n'est pas à Bouclier n'est jamais touché. Les copies déposées pour Bouclier (entrées, réponses) de plus de 30
jours sont retirées (les originaux restent dans Messages ou Photos). La structure exacte des actions d'un raccourci
ne peut pas être vérifiée sans iPhone : la recette manuelle (noms d'actions en français) est le plan B.

## 2026-10-07 · P9 — Démon, Gmail, doctor, tableau de bord, installation

**D-25 · Le démon : une boucle qui ne s'arrête jamais, des dates de tâches gardées en base.**
Un seul LaunchAgent (`KeepAlive`, `ThrottleInterval` 30 s) lance `python -m bouclier demon`. Chaque tour (3 s, ou
tout de suite quand FSEvents voit un fichier dans l'entrée iCloud) : entrée du raccourci, puis les tâches dues
(Gmail 5 min, flux et fuites chaque jour, inventaire chaque semaine, numéros de la fiche tous les 6 mois). La date
de la prochaine exécution de chaque tâche est écrite en base (`prochain:<tâche>`) : un redémarrage ou une veille ne
la décale pas et ne relance pas tout. Une tâche qui plante est notée, retentée dans 1 h, et n'empêche jamais les
autres ; un réglage abîmé fait tourner le démon sur les valeurs par défaut (signalé par `doctor`). Écarté : un
LaunchAgent par tâche (plus d'éléments de démarrage pour le Nettoyeur, plus de risques de collision).

**D-26 · Gmail : la boîte de réception seulement, à partir du jour où tu relies Gmail.**
Au premier passage, Bouclier note le dernier UID et n'analyse pas l'ancien courrier (des centaines d'alertes
inutiles sinon). Ensuite : EXAMINE, `BODY.PEEK[]` limité à 5 Mo, analyse locale, IA seulement si le score hésite,
notification seulement pour « Arnaque » ou « Très suspect ». Après un échec IMAP, le délai double (10, 20, 40 puis
60 min au plus) ; un Gmail non relié est revérifié toutes les heures, sans notification.

**D-27 · `doctor` et le score « Hygiène numérique » : des constats, jamais des actions automatiques.**
`bouclier doctor` donne l'état de chaque brique (✅ / ⚠️ / ❌) avec la solution en une ligne. Le score (0 à 100) part
de 100 et retire des points pour ce qui compte vraiment : une fuite qui te concerne (14 chacune, 3 au plus), pas de
double authentification sur un compte important ou bancaire encore actif (10), fiche urgence absente (9) ou vieille
de plus de 6 mois (5), inventaire jamais lancé (10), comptes marqués « à supprimer » (2 chacun, 10 au plus), Gmail
non relié (5), plus de 20 comptes à trier (3). Les 3 retraits les plus lourds deviennent les 3 actions affichées.

**D-28 · L'installation pose 5 choses, chacune vérifiée « à nous » avant d'être touchée.**
Le LaunchAgent `com.<session>.bouclier`, le lanceur `~/.local/bin/bouclier` (marqué), les actions rapides
`fr.bouclier.*`, les 2 raccourcis signés dans iCloud Drive/Bouclier, et nos dossiers. Si la commande `bouclier`, le
lanceur ou le plist existent déjà sans être à Bouclier, l'installation s'arrête et l'explique. Tout peut être relancé
sans effet de bord. La désinstallation retire ce qui a été posé ; tes données restent sauf `--tout` ; le dossier
iCloud Bouclier reste toujours (il est dans ton iCloud, à toi de décider).

## 2026-10-07 · P10 — Installation

**D-29 · Le démon a deux rythmes : la réponse au raccourci dans le fil principal, le reste dans un fil à part.**
Un inventaire de grosse boîte Gmail peut durer plusieurs minutes : pendant ce temps, l'iPhone attend une réponse
60 s au plus. Le fil principal ne fait que l'entrée iCloud et les notifications gardées pour la nuit (toutes les
3 s) ; Gmail, listes, inventaire, fuites, fiche urgence et ménage tournent dans le fil « bouclier-taches », avec
leur propre connexion SQLite (une connexion par fil), un seul à la fois. SIGTERM de launchd réveille la boucle tout
de suite (launchd tue au bout de 20 s). Le tableau de bord est écrit par un fichier temporaire propre à chaque fil.

**D-30 · `install.sh` vérifie pour de vrai ce qu'il a installé, sur ton Mac.**
Huit étapes, relançables : Python ≥ 3.11 ; empreinte des autres projets avant ; `.venv` (pip seulement si
`pyproject.toml` a changé) ; dossiers, commande, actions rapides, plist ; raccourcis signés ; `launchctl bootout`
de l'ancienne version, `enable`, `bootstrap`, attente du pid ; puis `bouclier installation verifier` : `launchctl
print`, `kill` du démon, attente de la relance par launchd (90 s au plus, ThrottleInterval compris), dépôt d'un
texte et d'une capture d'écran dans `iCloud Drive/Bouclier/entree/` et attente de la réponse du démon ; ces fichiers
de test (`bouclier-verif-*`) sont analysés pour de vrai, sans notification ni trace dans l'historique, puis retirés.
Enfin `bouclier doctor` et la comparaison de l'empreinte. Tout est copié dans `~/Library/Logs/Bouclier/
installation-<date>.log`. Jamais de sudo (refusé). `uninstall.sh` : bootout, attente, retrait de ce qui est à
Bouclier, empreinte avant/après ; `--tout` retire aussi les données ; le dossier iCloud et le projet restent.
Ici (Linux), les deux scripts sont lancés pour de vrai deux fois chacun dans un Mac imité : faux launchctl qui lance
VRAIMENT le démon et le relance après un kill, `uname` = Darwin, réseau coupé et noté dans chaque processus.

**D-31 · L'empreinte des LaunchAgents des autres projets : chargé et en marche, pas le numéro de processus.**
Le pid change à chaque redémarrage du Mac : le comparer aurait fait échouer `check.sh` sur ton Mac sans que rien
n'ait changé. On compare le plist (SHA-256), « chargé » et « en marche ». La référence du Mac peut être placée
ailleurs (`BOUCLIER_INTEGRITE_MAC`, utilisé par les tests).

**D-32 · Les vérifications qui demandent ton Mac sont des tests `reel` dans `tests/e2e_mac`.**
Apple Vision sur une capture, `plutil -lint` des actions rapides installées, `shortcuts sign` des 2 raccourcis,
Gmail réel : drapeaux et libellés de 20 messages témoins identiques avant et après l'analyse de 3 messages et la
lecture des en-têtes (base jetable, aucune notification). Lancés à la demande (ACTIONS_HUMAINES.md), jamais par
`check.sh` (ils ont besoin de ton compte).

## 2026-10-07 · P11 — Revue hostile (2 passes)

**D-33 · Ce que la revue hostile a trouvé et corrigé.**
Passe 1 (attaquant puis reviewer), 25 pièges inédits et 15 vrais messages qui leur ressemblent :
- **Faux positif** : un vrai SMS 3-D Secure (« saisissez le code 552013 sur la page de paiement… ne le communiquez
  jamais ») était 🟠. Règle séparée en deux : *transmettre* un code (à un conseiller, par SMS, « donnez-le ») est
  toujours une demande ; *saisir* un code n'en est pas une quand le message fournit lui-même le code et n'a ni lien ni
  numéro. Exception unique : le code de remise d'un colis « à donner au livreur » (Amazon, Chronopost), légitime.
  Le piège « votre code est 552013, communiquez-le au conseiller » reste 🔴.
- **Caractères invisibles** (espace de largeur nulle, marques de sens d'écriture) : retirés avant les règles (« rem
  boursement » ne passe plus entre les mailles) ; dans un lien, ils sont un signe critique (« lien:invisible »).
- **Phrases** : un sosie « à une lettre près » (credit-agricoIe.fr) le dit clairement ; un nom en punycode est
  affiché décodé (jamais « xn--… »).
- « Activez votre nouveau dispositif sécurité » avec un lien rejoint les demandes de compte.
- **Énergie** : la boucle de 3 s écrivait deux fois en base à chaque tour (≈ 57 000 écritures par jour) et relisait
  config.toml. Désormais : un battement toutes les 30 s, réglages relus seulement s'ils changent (test : ≤ 10
  écritures pour 100 tours au repos). Le Nettoyeur ne verra pas Bouclier comme gourmand.
- **Journal d'erreurs de launchd** : une erreur imprévue n'y écrit plus que son type (crochets `sys.excepthook` et
  `threading.excepthook` vers le journal caviardé).
Passe 2, 14 nouveaux pièges (i sans point, alpha latin, o arménien, pleine chasse, accent, « rn », lettre doublée,
faux sous-domaines, faux conseiller « compte sécurisé », faux proche) : tous 🟠 ou 🔴 sans nouvelle correction. Les
39 pièges et 15 vrais messages sont devenus des tests permanents (`tests/corpus_arnaques/test_revue_hostile.py`).
Vérifiés sans défaut : écriture IMAP impossible (EXAMINE, `BODY.PEEK`, `LOGOUT` seul), colonne de mot de passe
jamais nommée, journal caviardé, aucun fichier hors de `bouclier/` modifié depuis le premier commit de Bouclier.

**D-34 · L'intégration à l'assistant passe par deux portes stables, sans importer Bouclier.**
`etat.json` (à côté du tableau de bord, écrit en même temps, chmod 600) et `bouclier verifier --json`. L'assistant
garde son propre environnement Python ; il n'a pas à connaître la base de Bouclier. INTEGRATION.md donne les
quelques lignes à ajouter (brief du matin, bouton du menu).

**D-35 · Dans Messages, un SMS n'a pas de bouton « Partager » : la capture d'écran est le chemin principal.**
La documentation (README, ACTIONS_HUMAINES, recette manuelle) part de la capture d'écran (lue en local par Apple
Vision) ; pour un mail ou un lien, appui long → Partager ; sur le Mac, `--presse-papiers`.

## 2026-10-07 · Après la première installation réelle sur ton Mac

**D-36 · Ce que ton Mac a montré, et ce qui a changé.**
L'installation a réussi deux fois (relance par launchd en 30 s, réponse iCloud en 5 à 11 s, Apple Vision, raccourcis
signés, intégrité identique). Quatre défauts visibles seulement là :
- **OpenPhish jamais téléchargé** (URLhaus et HIBP l'étaient) : cause la plus probable, une redirection vers
  `www.openphish.com`, refusée par la liste blanche, ou un refus du site. `www.openphish.com` est permis, et le miroir
  officiel d'OpenPhish sur GitHub (`raw.githubusercontent.com/openphish/public_feed/…`, mis à jour toutes les 12 h)
  sert de secours : **cette adresse-là seulement** (tout autre chemin de raw.githubusercontent.com reste refusé). La
  raison d'un échec est gardée (`flux-erreurs.json`) et affichée par `doctor` ; une liste ratée est retentée toutes
  les heures, une liste de moins de 20 h n'est pas retéléchargée.
- **`gmail-relier ADRESSE`** tapé tel quel : l'adresse est maintenant demandée si elle manque ou n'a pas de « @ » ; le
  mot de passe d'application est vérifié aussitôt par une vraie connexion en lecture seule (EXAMINE), les espaces de
  l'affichage de Google sont retirés, et le démon lance Gmail et l'inventaire dans les secondes qui suivent.
- **Bilan trop tôt** : `install.sh` (étape 7) attend la fin du premier tour du démon (3 min au plus) avant `doctor`.
- **Inventaire à 0 sans explication** : `doctor` dit quels navigateurs ont été lus, que Safari ne l'est jamais (ses
  mots de passe sont au trousseau) et qu'il faut relier Gmail.
