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
