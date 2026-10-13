# Décisions de Voix

Chaque choix ambigu, avec la date, le choix, les alternatives et la raison. Les plus récentes en bas.

**D-01 · Voix vit dans le dépôt de l'assistant, dossier `voix/` (2026-10-13).**
Choix : le code est dans `~/Assistant/voix` (comme le Tableau de bord, Bouclier, Quotidien), un commit par phase verte
sur la branche de travail. Alternative : `git init` dans `~/Projets/voix`. Raison : tu récupères tout par
`git pull` de ce dépôt ; un dépôt imbriqué ne se pousse ni ne se tire avec lui. L'empreinte d'intégrité traite le
reste du dépôt comme « un autre projet » (tout ce qui est hors de `voix/` doit rester identique).

**D-02 · Construit dans un conteneur Linux, vérifié sur ton Mac par `install.sh` et `voix verifier` (2026-10-13).**
Il n'y a pas de Mac ici : pas de `say`, pas de micro, pas de launchd, pas d'AppKit. Ce qui ne dépend pas du Mac est
prouvé ici (compréhension, actions avec de faux exécutables, moteur audio, Whisper sur un corpus synthétisé, logique
de l'app). Ce qui en dépend (micro réel, Apple Speech, raccourci global, bulle, LaunchAgents, Core Audio) est vérifié
automatiquement par `install.sh` puis `voix verifier` sur le Mac, avec la preuve affichée.

**D-03 · Environnement (2026-10-13).**
- Conteneur : Ubuntu 24.04, x86_64, 4 processeurs, 15 Go ; Python 3.13.14 (venv), Swift 6.2.4 ; voix françaises
  espeak-ng 1.51 + MBROLA fr1 à fr7 ; ffmpeg.
- Ton Mac (connu par les installations précédentes) : Apple Silicon (Homebrew dans `/opt/homebrew`), Python 3.14.4
  (`/opt/homebrew/bin/python3.14`). `sw_vers`, `uname -m`, `xcode-select -p`, `swift --version`, `say -v '?'` (voix
  françaises) et la reconnaissance Apple sur l'appareil en fr-FR sont relevés par `install.sh` (étape 1) et par
  `voix doctor` ; ils seront recopiés ici à la première installation.

**D-04 · Swift : un Core sans macOS, vérifié partout ; l'app compilée une seule fois sur le Mac (2026-10-13).**
Le paquet `app/` a quatre cibles : `CommandesVocalesCore` (protocole, découpage des lignes, états de l'écoute, raccourci,
suspension pendant les appels : Foundation seulement), `ControlesCore` + `controles-core` (les vérifications du Core,
lançables **sans XCTest**, que les seuls Command Line Tools du Mac n'ont pas toujours), les tests XCTest (qui appellent
les mêmes vérifications) et `CommandesVocales` (l'app macOS). Ici : Swift 6.2.4 officiel, extrait de l'image
`swift:6.2.4-noble` (miroir Google de Docker Hub, couche vérifiée par son empreinte SHA-256), car swift.org est bloqué
depuis ce conteneur. `swift-tools-version:5.9` (mode de langage 5) : compile avec tout Swift 5.9 à 6.x.

**D-05 · Modèles et leurs sources (2026-10-13).**
- Mot d'éveil : openWakeWord **0.5.1** depuis PyPI, qui contient les modèles officiels (`hey_jarvis_v0.1.onnx`,
  `melspectrogram.onnx`, `embedding_model.onnx`), mêmes fichiers que les versions GitHub ; leurs SHA-256 sont figés
  dans le code et vérifiés à l'installation. (GitHub est bloqué depuis ce conteneur ; PyPI ne l'est pas.)
- Détection de voix : Silero VAD depuis le paquet PyPI `silero-vad` (modèle ONNX inclus), lu avec onnxruntime, sans
  torch ; WebRTC VAD en repli.
- Whisper sur ton Mac : téléchargé depuis Hugging Face à l'installation, chaque fichier vérifié contre l'empreinte que
  publie Hugging Face (SHA-256 des fichiers LFS).
- Whisper ici, pour mesurer seulement : Hugging Face est bloqué depuis ce conteneur ; les conversions ONNX officielles
  `Xenova/whisper-base` et `Xenova/whisper-small` (quantifiées 8 bits) viennent d'un paquet npm tiers (empreinte npm
  vérifiée). Elles ne servent qu'au banc d'essai du conteneur et ne sont **jamais** installées sur ton Mac.

**D-06 · Corpus audio : `say` sur ton Mac, espeak-ng + MBROLA ici (2026-10-13).**
Le générateur choisit son synthétiseur : `say` (toutes les voix françaises, 3 débits) sur le Mac, espeak-ng avec les
7 voix MBROLA françaises ici. Mêmes phrases, mêmes bruits, mêmes critères.

**D-07 · Ce que l'installation de Voix fait remarquer aux autres modules, sans rien toucher chez eux (2026-10-13).**
Le Tableau de bord ajoute **lui-même** Voix à son registre (`modules.toml`) quand il découvre `com.<toi>.voix` : ce
fichier est donc traité comme une donnée vivante par notre empreinte. Son gardien d'intégrité signalera aussi que le
code de l'assistant a changé (le dossier `voix/` est nouveau) ; le Nettoyeur signalera une fois les nouveaux éléments
de démarrage. C'est normal, c'est écrit dans le README.

**D-08 · Raccourci : ⌃⌥Espace s'il est libre, sinon le premier candidat libre (2026-10-13).**
D'usine, macOS met « sélectionner la source de saisie suivante » sur ⌃⌥Espace (même avec une seule source). Voix ne
modifie jamais les raccourcis du système : `install.sh` lit l'export en lecture seule de `com.apple.symbolichotkeys`
(une entrée absente garde sa valeur d'usine, donc compte comme prise) et retient le premier libre de : ⌃⌥Espace,
⌃⌥⌘Espace, ⌃⇧Espace, ⌃⌥V. Le choix est écrit dans `choix.json` ; ce que tu écris dans `reglages.toml` passe devant.
Si une autre app a déjà pris la combinaison (refus de RegisterEventHotKey), l'app passe au candidat suivant et le dit.

**D-09 · Python : celui de ton Mac (3.14) ; 3.13 ici (2026-10-13).**
Toutes les roues nécessaires existent pour Python 3.14 sur Apple Silicon (numpy, onnxruntime, mlx, numba, rapidfuzz,
tokenizers, webrtcvad-wheels, scipy, scikit-learn). Le conteneur n'a pas 3.14 : 3.13. `mlx-whisper` est installé sans
torch (torch ne sert qu'à convertir des modèles).

**D-10 · Les noms d'agents : `com.<ta session>.voix` et `com.<ta session>.voix.app` (2026-10-13).**
Comme les autres modules : le préfixe est le nom de ta session macOS (réglable dans `reglages.toml`,
`[installation] prefixe_label`), jamais écrit dans le dépôt.

**D-11 · La compréhension : deux lectures, toutes deux déterministes et strictes (2026-10-13).**
1. La **grammaire** reconnaît la phrase entière (verbes, objets du catalogue, nombres, durées) ; c'est la lecture
   rapide et sûre des tournures connues.
2. Si elle ne reconnaît rien, une **seconde lecture** essaie, dans l'ordre :
   - la même demande **remise dans l'ordre** (« Safari, ouvre-le », « dans une heure rappelle-moi… », « ouvre Safari…
     non, Chrome », « garde que Word et cache le reste »), puis repassée par toute la grammaire ;
   - la demande **sans ce qui l'entoure** : le but (« pour la réunion »), une proposition de plus (« il rame »), une fin
     sans liaison (« le bébé dort ») ; seulement si la fin coupée n'a ni négation, ni nombre, ni complément (« de la
     guitare », « dans la voiture »), si la phrase ne commence pas par un article (un avis : « le mode sombre, c'est
     joli »), et pour une fin sans liaison, seulement un ordre simple sans objet ;
   - le **nom exact** d'un objet suivi d'une fin (« ouvre Excel le fichier des ventes ») : score ≥ 0,97, jamais un nom
     commun seul (« le dossier secret de la NASA » n'ouvre pas ton dossier) ;
   - les **questions par mots** (`questions.py`) et les **sacs de mots** (`sacs.py`) : l'ordre des mots est libre, mais
     **chaque** mot doit être expliqué (un mot du sujet, un mot permis, ou un mot-outil) ; un seul mot inexpliqué et
     rien n'est reconnu ; deux intentions possibles et rien non plus ; jamais de nombre.
   Garde-fous communs : un participe n'est pas un ordre (« j'ai cherché partout ») ; « va chercher » n'est pas
   « cherche » ; « oui »/« non » se disent franchement (« d'accord, je vois » n'est pas une confirmation) ; une
   information (heure, météo…) n'est jamais tirée d'une phrase coupée (« quelle heure est-il à Tokyo » reste incomprise).
Pourquoi : la grammaire seule tenait 100 % sur ses tournures mais tombait à 66–92 % sur des tournures neuves (D-13).

**D-12 · Les conventions de sens, appliquées partout et dans les jeux de phrases (2026-10-13).**
Un nom seul n'est pas un ordre (« musique », « Safari » : pas compris, avec suggestions). Une plainte non plus (« c'est
trop fort »). « Mode muet » est la voix de l'assistant (« passe en mode muet » = se taire). « Cherche X » sans moteur
= Spotlight (« cherche sur Google X » = le web) ; Spotlight retire l'article (« la facture » → « facture »). Les verbes
faibles (« mets », « joue », « écoute ») n'ouvrent qu'un nom dit presque exactement, jamais « à » quelque chose (« joue
aux cartes »). Un raccourci au nom exact passe avant un mode d'Ambiance absent (« lance mode lecture »). Un nom dit
exactement passe avant la priorité des genres (« lance Révisions » = la playlist). Commander, réserver, payer : refus.
Un ordre composé (« ferme Chrome et Safari ») n'est pas pris en charge.

**D-13 · La mesure anti-triche : protocole et résultats, sans retouche (2026-10-13).**
Protocole : un jeu de phrases écrit d'un bloc, à la main, sans relire la grammaire ; passé **une seule fois** ; le
premier résultat est consigné tel quel ; ensuite seulement, le jeu sert au réglage (et un jeu neuf devient la mesure).
Depuis le jeu 7, chaque ordre est vérifié **jamais vu** (texte normalisé absent de tous les jeux précédents) avant le
passage. Premiers passages (seuils anti-triche : intention ≥ 95 %, paramètres ≥ 93 %) :

| Jeu | Nature | Ordres | Intention | Paramètres | Hors catalogue : actions | Sensibles |
|---|---|---|---|---|---|---|
| 2 | premier jeu écrit à la main | 327 | 70,6 % | (non conservé) | — | — |
| 3 | tournures orales | 463 | 91,8 % | 99,3 % | 2 / 58 | 15/16 |
| 4 | **hostile** (tournures choisies pour casser) | 405 | 65,7 % | 98,5 % | 1 / 59 | 9/14 |
| 5 | **hostile** | 408 | 89,7 % | 99,5 % | 1 / 60 | 14/15 |
| 6 | représentatif (57 % d'ordres déjà vus) | 371 | 98,1 % | 100 % | 1 / 60 | 12/12 |
| 6 | … ses 158 ordres neufs seulement | 158 | 95,6 % | — | — | — |
| 7 | 416 ordres **jamais vus** | 416 | **89,2 %** | 99,5 % | 2 / 60 | 11/12 |
| 8 | 413 ordres **jamais vus** | 413 | **86,4 %** | 98,9 % | 4 / 60 | 11/11 |

Conclusion honnête : sur des phrases vraiment neuves, la compréhension par règles reconnaît **86 à 89 %** des ordres
du premier coup ; le seuil de 95 % **n'est pas atteint**. Les paramètres, eux, sont justes à ≥ 98,9 % dès qu'une
intention est reconnue, et un ordre non reconnu ne fait **rien** (« pas compris » + 3 suggestions). Après réglage, les
8 jeux (4 838 ordres, 617 hors catalogue) sont à ≥ 98 % d'intentions, ≥ 99,5 % de paramètres, 0 action hors catalogue.
J'ai arrêté là : chaque tour de réglage ajoutait des règles (et des risques de faux positifs, vus et corrigés au jeu 8)
sans faire monter le premier passage. Pistes, à décider avec toi : l'aide-mémoire (P7) avec les tournures qui marchent
à coup sûr ; l'IA optionnelle (éteinte par défaut) pour traduire une phrase non comprise en une intention de la liste
blanche, toujours validée et confirmée ; tes propres phrases ajoutées à la volée (`commandes.toml`).

**D-14 · Les objets : nom partiel et nom exact (2026-10-13).**
Un mot de 4 lettres ou plus qui fait partie du nom d'**un seul** objet suffit (« ma playlist jazz » → « Jazz du
soir », score 0,84 ; plusieurs objets → « lequel ? »). Un nom dit exactement n'est jamais battu par un nom seulement
proche d'un genre prioritaire. Les synonymes français courants sont dans `apps_connues.json` (« enregistreur vocal »
→ Dictaphone, « agenda » → Calendrier).

**D-15 · Les actions qui demandent une autorisation passent par l'app, avec des ordres fermés (2026-10-13).**
Quitter ou cacher une app, piloter Musique et Spotify, changer l'apparence, verrouiller l'écran, afficher une
notification : le moteur Python envoie à l'app « Commandes Vocales » un **ordre de la liste** (`app.quitter`,
`musique.pause`, `apparence.regler`…) et des paramètres validés (identifiant d'app, lecteur, booléen) ; l'app ne reçoit
jamais de script. Alternative : `osascript` depuis le moteur. Raison : macOS demande l'autorisation « Automatisation »
au nom du programme qui envoie l'Apple Event ; depuis l'app, tu vois « Commandes Vocales » dans Réglages, pas un Python
anonyme, et une seule autorisation suffit. Le volume reste par `osascript` (aucune autorisation demandée), le niveau
passé en argument (`on run argv`), jamais collé dans le script.

**D-16 · Ce que la voix lance : une liste blanche, des arguments un par un (2026-10-13).**
Huit programmes du système (`open`, `osascript`, `networksetup`, `pmset`, `shortcuts`, `mdfind`, `defaults` en
lecture, `say`) cherchés dans `/usr/bin`, `/bin`, `/usr/sbin`, `/sbin` ; quatre commandes publiques de tes modules
(`tableau`, `ambiance`, `quotidien`, `bouclier`) cherchées dans `~/.local/bin`, Homebrew et ton PATH. Jamais de shell,
un délai maximum, un environnement réduit. Un seul fichier lance des programmes (`actions/executeur.py`, plus la
lecture des raccourcis clavier dans `cli.py`) ; un test le vérifie dans tout le code, avec l'absence de `shell=`,
`eval`, `os.system`. Le lecteur du catalogue (`mdfind`, `shortcuts list`) passe aussi par l'exécuteur.

**D-17 · Ce que la voix accepte d'ouvrir (2026-10-13).**
Un chemin absolu, existant, **dans ta maison** (ou une app d'un dossier Applications) ; jamais un fichier qui s'exécute à
l'ouverture (`.command`, `.sh`, `.app` hors Applications, `.workflow`, `.pkg`, `.webloc`…) ni un fichier exécutable ;
jamais un lien qui sort de ta maison. Les adresses : `https` seulement. Un alias de `commandes.toml` qui viole ces
règles est refusé au chargement (et l'erreur est affichée) ; un résultat Spotlight qui les viole n'est pas ouvert.

**D-18 · « Annule » et « Tu confirmes ? » (2026-10-13).**
« Annule » défait la dernière action **réversible** — volume, son coupé, apparence, Wi-Fi, concentration — en remettant
exactement l'état lu juste avant (pas « l'inverse supposé ») ; jusqu'à 20 actions en arrière. Ouvrir, fermer ou
chercher ne s'annule pas, et Voix le dit. Les actions sensibles (mise en veille, « ferme tout », « ferme tout sauf »,
Wi-Fi coupé, routine marquée `sensible = true`) demandent « Tu confirmes ? » : « oui » dans les 5 s → fait ; « non »,
silence ou n'importe quelle autre phrase → rien (« D'accord, je ne fais rien. »). Un « oui » arrivé trop tard ne fait
rien non plus.

**D-19 · Tes modules : découverts, jamais touchés (2026-10-13).**
`which` (dans les dossiers de D-16) dit lesquels sont installés ; un module absent répond « … n'est pas installé ».
Les modes d'Ambiance viennent de son README, lu en **lecture seule** à côté de sa commande ; un mode qu'il n'annonce pas
est refusé. Délai maximum 10 s (`[modules] delai_s`), sortie résumée à 300 caractères. Voix n'ouvre ni n'écrit aucun
fichier de leurs dossiers, et ne les arrête ni ne les relance. Pendant la construction, seuls de faux exécutables
(qui notent leurs arguments) ont été lancés.

**D-20 · La météo, les minuteurs, le journal : sans réseau et sur ton disque seulement (2026-10-13).**
« La météo » ouvre l'app Météo (aucun appel réseau depuis Voix). Les minuteurs et rappels (20 au plus) sont gardés dans
`minuteurs.json` (0600) et survivent à un redémarrage du moteur ; à l'échéance, une notification par l'app (repli :
`osascript` avec le message en argument). Le journal garde les 100 dernières commandes (texte, intention, résultat ;
jamais d'audio), e-mails et longues suites de chiffres masqués ; `voix journal` l'affiche, `voix oublier` l'efface,
`[journal] actif = false` l'arrête.
