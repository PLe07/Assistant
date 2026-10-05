# Décisions — Nettoyeur de démarrage

Chaque choix ambigu, avec les alternatives écartées et la raison. Le plus récent en bas.

## 2026-10-05 · P0 — Reconnaissance

**D-01 · Construit dans un conteneur Linux, vérifié ensuite sur le Mac.**
Cette session tourne dans un conteneur cloud (Linux x86_64, Python 3.11, zsh présent, mais ni `launchctl`, ni
`sfltool`, ni `codesign`, ni `mdls`, ni `pmset`, ni `systemextensionsctl`, et un `top` différent de celui de macOS).
`uname -m`, `sw_vers` et les commandes du §0 ne peuvent donc pas être vérifiés ici. Le Mac cible est connu par les
sorties déjà collées pendant le Détecteur de corvées : MacBook Air Apple Silicon (arm64), macOS 26 (paquets
`macosx_26_0` installés par pip), venv en Python 3.14, zsh.
Conséquences :
- tout ce qui parle au Mac passe par une seule interface (`systeme.py`, D-04) ;
- les formats de sortie sont reconstruits d'après leur documentation (D-05) ;
- la commande `demarrage doctor` vérifie sur le Mac la présence de chaque commande et dit ce qui est dégradé ;
- les vérifications qui exigent le vrai Mac sont listées dans `ACTIONS_HUMAINES.md`.

**D-02 · Un module de l'Assistant, pas un projet séparé.**
Comme le Détecteur de corvées (voir `modules/corvees/DECISIONS.md` D-01), le Nettoyeur devient
`modules/demarrage` dans le dépôt de l'Assistant (`~/Assistant` sur le Mac, dont le premier module est le tri
Gmail `modules/mails`). Il reprend les conventions du dépôt : réglages dans `reglages.json` → `modules.demarrage`,
journal dans `logs/assistant.log` avec le préfixe `[demarrage]`, notifications par `core.notifications` (qui gère
déjà les heures silencieuses, la pause et le plafond horaire), et la porte `check.sh` du module.
Données : `donnees/demarrage/` (base SQLite en `chmod 600`, quarantaine, rapport HTML, cache des signatures).
Le dossier `donnees/` n'est jamais versionné.
*Écarté :* `~/Library/Application Support/NettoyeurDemarrage/` et `~/Library/Logs/NettoyeurDemarrage/`. Ils sont
dans le périmètre autorisé, mais ils auraient créé un deuxième endroit pour les données et les journaux. Le
réglage `dossier` (ou `$DEMARRAGE_DOSSIER`) permet de les choisir quand même.

**D-03 · Pas de LaunchAgent à part ; libellés neutres.**
La surveillance de fond est un module lancé et relancé par le superviseur de l'Assistant. Le superviseur est
lui-même confié à launchd par `python service.py installer` (RunAtLoad, KeepAlive, ThrottleInterval).
`demarrage surveiller on|off` allume ou éteint ce module, exactement comme `assistant.py activer …`.
Le Nettoyeur se reconnaît donc lui-même dans l'inventaire : tout libellé `com.assistant.*` est marqué « c'est
moi » et n'est jamais proposé à la désactivation.
Le dépôt est public : les éléments de test s'appellent `com.assistant.nettoyeur.test.*` au lieu du libellé
demandé, qui contient un prénom. C'est la même raison que D-01 des corvées.
*Écarté :* un LaunchAgent `com.<prénom>.nettoyeur` en plus du superviseur. Il aurait été un deuxième programme au
démarrage, ce qui est un comble pour un nettoyeur de démarrage, et il aurait mis un prénom dans le dépôt.

**D-04 · Une seule porte vers le Mac : `systeme.py`.**
Les collecteurs, la mesure et les actions ne lancent jamais `subprocess` eux-mêmes. Ils reçoivent un objet
`Systeme` qui fournit cinq choses :
- `executer(commande, delai)` : une liste d'arguments, jamais de shell, toujours un délai ;
- `chemin(absolu)` : place un chemin du Mac sous une racine qu'on peut changer ;
- `maintenant()` et `attendre(s)` : l'heure ;
- `a_la_commande(nom)` : la commande existe-t-elle ?
Le vrai Mac (`Mac`) refuse toute commande `sudo`, `su` ou `doas` avant de la lancer. Le faux Mac des tests
(`tests/demarrage/faux_mac`) enregistre chaque commande, ce qui permet aux tests de sécurité de prouver qu'aucune
commande modifiante ne part sans `--confirmer`.
*Écarté :* simuler avec `unittest.mock.patch("subprocess.run")` partout. C'est fragile, et ça ne permet pas de
déplacer les racines (`/Library`, `/Applications`) vers un dossier de test.

**D-05 · Fixtures : formats reconstruits ici, fixtures réelles capturées sur le Mac.**
Je ne peux pas lancer `launchctl` ou `codesign` dans ce conteneur. `tests/demarrage/fixtures/formats/` contient
des sorties reconstruites d'après le format documenté de chaque commande. Elles sont anonymisées par construction
(utilisateur `utilisateur`, UID 501) et volontairement « sales » : colonnes décalées, espaces et accents dans les
chemins, lignes inattendues.
`modules/demarrage/capturer.py`, lancé sur le Mac, capture les vraies sorties en lecture seule, les anonymise
(dossier personnel, nom de compte, nom complet, nom de l'ordinateur, adresses e-mail, UUID) et refuse d'écrire si
le nom de compte reste visible. Il les range dans `tests/demarrage/fixtures/reelles/`, qui n'est pas versionné
(seul son README l'est). Un test analyse tous les fichiers trouvés là : rien ici, tout sur le Mac.
*Écarté :* versionner les sorties réelles. Elles listeraient publiquement les logiciels installés sur le Mac.

**D-06 · Pas de psutil.**
`ps -axo pid=,ppid=,uid=,%cpu=,rss=,etime=,time=,comm= -ww` donne tout ce qu'il faut. Le temps processeur cumulé
(`time`) permet de calculer les secondes de processeur exactes entre deux mesures, sans dépendre de la moyenne
glissante de `%cpu`. L'en-tête est supprimé (`=`) et `comm` est en dernier, donc les chemins avec des espaces
restent entiers. L'UID numérique évite d'écrire des noms de comptes.
*Écarté :* psutil (dépendance compilée de plus, et le §5 le rend facultatif).

**D-07 · « sudo » n'existe que dans un texte à recopier.**
Pour les éléments globaux (S2, S8, extensions système), le Nettoyeur affiche la commande à taper soi-même. Le mot
`sudo` n'apparaît donc que dans `actions/instructions.py`, qui fabrique ces textes et ne lance jamais rien. Un test
de sécurité parcourt tout le code du module et échoue si `sudo` apparaît ailleurs. Il échoue aussi en cas de
`shell=True`, `os.system` ou `subprocess` hors de `systeme.py`.

**D-08 · `restaurer` est aussi une simulation sans `--confirmer`.**
Le §8 demande « aucun subprocess modifiant sans `--confirmer` ». Annuler une désactivation modifie le Mac autant
que la faire : `restaurer ID` montre donc ce qu'il ferait, et `restaurer ID --confirmer` le fait.

**D-09 · Le test de bout en bout sur le Mac est un fichier à part, jamais « sauté ».**
Les tests qui exigent le vrai Mac (agents de test chargés pour de vrai, `caffeinate`, `launchctl bootout`) sont
dans `tests/demarrage/e2e_mac/`. `check.sh` ne les lance pas. Ils échouent franchement s'ils tournent ailleurs
que sur macOS. L'utilisateur les lance à la main (`ACTIONS_HUMAINES.md`). Aucun test du module n'utilise `skip`.
*Écarté :* `pytest.mark.skipif(sys.platform != "darwin")`. Ce serait un test sauté dans la porte, ce qui est
interdit.

**D-10 · Où se range la vérité terrain.**
Le faux Mac de §8 est dans `tests/demarrage/faux_mac/construire.py`, à côté des autres tests du module, et non dans
`tests/faux_mac/`. Les tests du dépôt sont rangés par module (`tests/corvees`, `tests/demarrage`).

## 2026-10-05 · P1 — Modèle, collecteurs S1-S4 et S6

**D-11 · Les noms de fichiers du §8, dans `modules/demarrage/`.**
Le paquet ne s'appelle pas `nettoyeur/` mais `modules/demarrage/` (D-02). À l'intérieur, les noms du §8 sont
gardés : `collecteurs/agents_utilisateur.py`, `agents_globaux.py`, `apple.py`, `apps_embarquees.py`,
`launchd_etat.py`… Trois fichiers communs s'y ajoutent :
- `collecteurs/plists.py` : lire un plist sans planter ;
- `collecteurs/applications.py` : l'index des apps installées ;
- `scan.py` : l'orchestration.
`config.example.toml`, `install.sh` et `uninstall.sh` sont remplacés par les mécanismes de l'Assistant :
`reglages.json` et `service.py installer|desinstaller`.

**D-12 · « Signé Apple » ne suffit pas : il faut une fiche d'Apple.**
Un plist d'un tiers peut lancer un programme de macOS : `/usr/bin/curl`, `/bin/sh script`, `/usr/bin/open -a`.
C'est même la persistance classique d'un logiciel indésirable. L'étiqueter 🍎 le rendrait intouchable. La règle :
- **🍎** : sous `/System` (S3), ou un label `com.apple.*` dont le programme est signé Apple, ou un élément
  d'ouverture qui est une app signée Apple ;
- **un interpréteur** (`sh`, `bash`, `zsh`, `python3`, `osascript`, `env`, `nohup`, `open`) : le programme retenu
  est le script ou l'app qu'il lance, pas l'interpréteur ;
- **un programme système lancé par la fiche d'un tiers** : il est marqué `programme_systeme`, sans éditeur connu
  (le verdict en P5 le traitera comme à vérifier) ;
- **un label `com.apple.*` sans signature Apple** : il est marqué `se_dit_apple`, donc à vérifier.

**D-13 · S3 sans codesign ; S4 actif seulement s'il est enregistré.**
- Les éléments de `/System` sont sur le volume système scellé : ils sont étiquetés Apple sans lancer `codesign`.
  C'est des centaines d'appels en moins, et le scan reste sous les 15 s.
- Un agent embarqué dans une app (S4) n'est qu'une déclaration tant que l'app ne l'a pas enregistré. Il est
  « actif » s'il est chargé dans launchd ; S5 (Réglages) complétera en P3.

**D-14 · S6 : ce qui est chargé sans fichier connu.**
Les labels chargés dans ta session sans plist trouvé deviennent des fiches « launchd », avec leur programme lu par
`launchctl print gui/UID/label`. C'est le cas, par exemple, d'une app hors de `/Applications`.
Ce qui n'est pas du démarrage est ignoré : les apps ouvertes à la main (`application.*`), les services anonymes et
`com.apple.*`.
Il y a au plus 60 appels `launchctl print` par scan.
Les daemons système ont « chargé » et « désactivé » inconnus (`None`) quand `launchctl print system` est refusé
sans root : on ne devine pas.

**D-15 · Doublons et apps déplacées.**
- **Même label à deux endroits** : deux fiches marquées `doublon`. Au sein d'une même source, l'identifiant
  intègre le chemin du plist pour rester unique.
- **App déplacée** : si le programme a disparu mais qu'une app du même nom existe ailleurs, la fiche le dit
  (`app_deplacee_vers`). La fiche pointe vers l'ancien emplacement, elle est donc cassée, mais ce n'est pas une
  désinstallation.

## 2026-10-05 · P3 — Collecteurs S5, S7-S10, modes dégradés

**D-16 · S5 : trois méthodes, et l'honnêteté sur ce qu'on a vu.**
`sfltool dumpbtm` donne tout : apps d'ouverture, tâches de fond, et l'état activé/désactivé que tu as choisi dans
les Réglages. Il sert aussi à compléter les fiches déjà connues (S1, S4) au lieu de créer des doublons.
Ses repli sont moins complets, et S5 est alors marqué « dégradé », avec la raison :
- System Events ne voit que les apps « Ouvrir à la connexion », pas les tâches de fond ;
- la déduction prend les apps lancées dans les 2 minutes après l'ouverture de session. Elle peut confondre avec
  une app que tu as ouverte toi-même tout de suite ; la fiche indique « déduit ».
L'appel à System Events est en lecture seule (le script ne contient que « get »). Il a un délai de 10 s et n'est
jamais réessayé dans le même scan.

**D-17 · S8 et S9 : ce qui ne se lance plus, et ce qui ne sort pas.**
- **S8** : un assistant de `/Library/PrivilegedHelperTools` sans LaunchDaemon qui le lance ne démarre plus. Il est
  noté `sans_plist`, et le verdict (P5) le traitera en reste d'app.
- **S9** : la ligne de crontab complète ne sert qu'à calculer l'identifiant, elle n'est jamais gardée. Seuls le
  programme et l'horaire le sont, car une commande cron peut contenir un mot de passe ou un jeton.

**D-18 · S10 : jamais le texte d'une ligne de ~/.zshrc.**
On ne garde que le fichier, le numéro de ligne, la cause reconnue (nvm, conda, oh-my-zsh, compinit sans -C,
pyenv, rbenv, SDKMAN, brew shellenv, thefuck, brew update) et un conseil.
Un ~/.zshrc contient souvent des `export …_TOKEN=…`.

## 2026-10-05 · P4 — La mesure

**D-19 · Ce qu'on appelle « ouverture de session » et « calme ».**
- **Démarrage → connexion** (`connexion − kern.boottime`) : affiché pour information. Il inclut le temps passé
  devant l'écran de connexion.
- **Connexion → calme** : la courbe principale, celle que tes choix font bouger. Le calme est le début de la
  première période d'au moins 30 s où le processeur total reste sous 15 % de la capacité de tous les cœurs
  (`hw.ncpu`). Le processeur total est calculé exactement : la somme des secondes de processeur consommées entre
  deux relevés (`time` de ps), divisée par la durée et le nombre de cœurs.
- **L'heure de connexion** vient de `last` (à la minute) ou, à défaut, du journal de loginwindow (15 s au plus).
  Elle est affinée par le lancement de ton plus ancien processus quand il tombe dans la même minute.
- **L'année absente de `last`** est celle du démarrage, ou la suivante pour une connexion juste après le Nouvel
  An, jamais dans le futur.
- **Les heures locales** passent par `time.mktime`, qui suit le fuseau du Mac et le passage à l'heure d'été.

**D-20 · On rattache au relevé, on ne garde pas les processus.**
Garder chaque processus à chaque relevé ferait environ 360 000 lignes par jour. À la place, chaque relevé
rattache tout de suite les processus aux éléments du dernier scan (D-21), et ne garde qu'une ligne par élément
actif : secondes de processeur depuis le relevé précédent, mémoire, énergie (si `top` a tourné), veille empêchée.
Un processus vu pour la première fois compte en entier s'il est né après le relevé précédent (ou après la
connexion, au premier relevé d'une session). Sinon, le premier relevé sert de référence.
Un PID est le même processus tant que son heure de lancement estimée ne bouge pas de plus de 2 s. Au-delà, c'est
un PID réutilisé.

**D-21 · Le rattachement, et une exception au « bundle ».**
L'ordre est celui du §4 : PID launchd → exécutable → bundle de l'app → parent.
L'étape « bundle » ne s'applique qu'aux processus lancés directement par launchd (parent 1). Sinon, un agent
d'une app (Docker) prendrait aussi les processus de l'app que tu as ouverte toi-même.
Quand plusieurs fiches partagent une app, l'élément d'ouverture passe d'abord, puis les agents, Apple en dernier.

**D-22 · Rétention et zsh.**
- **Rétention** : les relevés de plus de 60 jours deviennent des agrégats par jour, élément et mode (processeur
  total, mémoire moyenne, énergie moyenne, nombre de veilles empêchées) ; les sessions et le temps de zsh sont
  gardés.
- **zprof** tourne dans une copie de tes fichiers zsh, dans `donnees/demarrage/`, effacée juste après ; tes
  fichiers ne sont jamais ouverts en écriture. C'est vérifié avec le vrai zsh dans `tests/demarrage/e2e`.
- **psutil** n'est toujours pas utilisé (D-06) : `ps` donne déjà le temps processeur cumulé, et un processus root
  qu'on ne peut pas lire n'existe pas pour ps (pas d'erreur à gérer).
