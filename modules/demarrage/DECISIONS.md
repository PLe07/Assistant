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

## 2026-10-05 · P5 — Scores, verdicts, connaissances, gains

**D-23 · L'action dépend de la source, le verdict du reste.**
Le verdict dit quoi en penser, l'action dit comment agir, et l'action vient de la source :
| Cas | Action |
|---|---|
| 🍎 Apple, ou « c'est moi » | aucune |
| ⚠️ Inconnu | vérifier (jamais supprimer) |
| déjà inactif | aucune |
| élément d'ouverture de session (S5) | Réglages, ou System Events si permis |
| global (S2, S4 daemons, S7, S8) ou cron | instructions à recopier |
| 👻 Orphelin dans ~/Library/LaunchAgents | quarantaine |
| autre cas | `launchctl bootout` + `disable` |
Le juge (`juger`) impose aussi deux garde-fous en dernier, quel que soit l'ordre des règles dans la config :
- un verdict 🍎 n'a jamais d'action ;
- un verdict ⚠️ n'a que « vérifier ».

**D-24 · Orphelin : seulement quand c'est sûr.**
Un programme absent n'est déclaré 👻 que si son plus proche dossier existant se lit (`absent_certain`). Sinon, on
ne voit peut-être simplement pas dedans : le verdict est ⚠️ « on ne conclut pas ».
Deux autres cas d'orphelin exigent une signature valide, sinon c'est ⚠️ (on ne pousse jamais à se débarrasser de
ce qu'on ne connaît pas) :
- une app associée (AssociatedBundleIdentifiers) désinstallée ;
- un assistant privilégié que plus rien ne lance.

**D-25 · « Inconnu » : ce qui compte comme éditeur connu.**
Est connu :
- Developer ID, App Store ou Apple ;
- une extension système avec son équipe (macOS ne l'active que notarisée) ;
- une signature ad hoc dont la base de connaissances nomme l'éditeur (services Homebrew) ;
- un programme de macOS lancé par une fiche tierce, seulement si la base de connaissances connaît la fiche.

Est inconnu : non signé, signature invalide, ad hoc anonyme, faux « com.apple », plist illisible, programme
non dit. Le script d'une tâche cron est non signé, donc ⚠️ : c'est souvent le tien, et le rapport le dit.

**D-26 · Mesures, scores et estimations.**
- **Processeur à l'ouverture** : la médiane des 5 dernières sessions (0 s pour une session où l'élément n'a pas
  tourné).
- **Croisière** : secondes de processeur / durée couverte sur 7 jours. Les trous de plus de 3 pas (veille, Mac
  éteint) sont exclus, avec le relevé qui les suit.
- **Mémoire** : la médiane quand il tourne.
- **Veille** : « empêche la veille » dès 5 % des relevés.
- **Pas encore mesuré** : l'impact typique de la base de connaissances (faible 3, moyen 12, fort 30). Il est
  affiché « estimé » et ne compte pas dans « te coûtent vraiment ».
- **Élément inactif** : impact 0.
- **« helper »** est retiré des motifs de mise à jour : l'assistant réseau de Docker ou d'un VPN n'en est pas un.
  Quand la base de connaissances reconnaît l'élément, c'est elle qui dit si c'est une mise à jour.

**D-27 · La base de connaissances, rangée du plus précis au plus général.**
82 entrées en français. La première entrée dont un motif correspond l'emporte.
Un test vérifie qu'aucune entrée générale ne masque une entrée plus précise placée après elle : par exemple,
« Mise à jour de OneDrive » avant « OneDrive », et « Docker (réseau et socket) » avant « Docker Desktop ».
Un élément absent de la base reçoit une description générique qui ne dit que ce qu'on sait.

## 2026-10-05 · P6 — Actions réversibles et sécurité

**D-28 · Le plan lit, la confirmation agit.**
`desactiver` établit toujours d'abord un plan, en lisant l'état actuel : `launchctl print gui/UID/label` (chargé ?)
et `print-disabled` (désactivé ?). Ce plan ne contient que les commandes encore nécessaires. Si tout est déjà fait,
il n'y a rien à faire et rien n'est noté : c'est l'idempotence.
`est_lecture` liste les seules commandes qu'une simulation peut lancer. Les tests de sécurité prouvent qu'aucune
autre ne part, sur le faux Mac et sur le vrai `Mac` dont `subprocess.run` est intercepté.

**D-29 · Restaurer d'après le journal, pas d'après le scan.**
`restaurer` défait la dernière action encore en place sur l'élément, avec ce que le journal a noté avant
d'agir :
- `enable` s'il n'était pas désactivé avant ;
- `bootstrap` s'il était chargé ;
- sortie de quarantaine.
L'état actuel est relu d'abord : si tu as déjà tout remis à la main, il n'y a rien à faire, et l'action est
seulement marquée annulée.
Une action à moitié faite (le bootout passé, le disable refusé) est notée telle quelle, pour que `restaurer` sache
la défaire.

**D-30 · La quarantaine ne supprime rien.**
Le plist part dans `donnees/demarrage/quarantaine/<horodatage>/` (dossier 700), avec un manifeste : chemin
d'origine, empreinte SHA-256, état avant.
Au retour, deux refus possibles :
- un fichier a pris la place d'origine : on ne l'écrase pas ;
- le plist en quarantaine a été modifié : on ne remet pas un fichier qu'on ne reconnaît plus.

**D-31 · Ce que le Nettoyeur ne fait jamais lui-même.**
- **🍎 et « c'est moi »** : refus.
- **Éléments globaux, extensions et cron** : le texte exact à recopier, avec la commande d'annulation. Pour un
  agent de `/Library/LaunchAgents`, ce sont des commandes de ta session, sans administrateur ; pour un daemon, les
  commandes `sudo` à taper toi-même.
- **⚠️ Inconnu** : de quoi le reconnaître (éditeur, fichier, programme, date d'apparition, commande `codesign` en
  lecture), et la phrase « Ne le supprime pas à l'aveugle ».
- **Élément d'ouverture** : System Events retire l'élément (et `restaurer` le remet) si l'autorisation existe.
  Sinon, le chemin exact dans les Réglages, et rien n'est noté au journal.

## 2026-10-05 · P7 — Rapport, CLI, notifications, surveillance

**D-32 · Le rapport : un fichier local, sans rien d'Internet.**
- **Fichier** : `donnees/demarrage/rapport.html` (600), ouvert par `open`. Aucun script ni police externe.
- **Thème** : clair ou sombre selon le Mac, avec un bouton pour forcer l'un ou l'autre. Le choix est gardé dans
  le navigateur ; si ce n'est pas possible, il est simplement oublié.
- **Courbe** : deux séries dans la même unité (secondes), donc un seul axe, avec légende, valeur en bout de ligne,
  info-bulle au survol et tableau « Voir les chiffres ». Les couleurs (bleu/orange) sont validées en clair et en
  sombre par le script de la palette (daltonisme, contraste). Une session « pas calme en 5 min » coupe la ligne au
  lieu d'inventer une valeur.
- **Vérification visuelle** : chaque version est photographiée en clair, en sombre et à 390 px de large, sans
  défilement horizontal. Les longs chemins se coupent.
- **Commandes** : les fiches donnent `demarrage …` (l'alias à ajouter une fois, décrit dans ACTIONS_HUMAINES) et
  la commande launchctl équivalente.

**D-33 · Une session non observée ne compte pas.**
La médiane du « processeur à l'ouverture » ne prend que les sessions vraiment mesurées (avec des relevés). Une
session où la surveillance a démarré trop tard aurait fait croire à 0 s pour tout le monde. C'est le rapport de
démonstration qui a montré le défaut : « 0,0 s de processeur en moins ».

**D-34 · Notifications : une par jour, rien la nuit, rien de perdu.**
- **Les règles** : au plus une notification par jour civil, jamais entre 23 h et 8 h (réglable).
- **Ce qui attend** : une notification retenue attend le premier moment permis. Plusieurs nouveaux éléments
  retenus sont regroupés en une seule notification, et ils passent avant le récap.
- **Le premier scan** sert de référence : on n'annonce pas « nouveau » tout ce qui existait déjà.
- **Ce qui n'est pas signalé** : un élément « chargé sans fichier » (S6), souvent passager ; un élément Apple ;
  « c'est moi » ; un élément inactif.
- **Le récap** (toutes les semaines) ne part que s'il y a un élément lourd 💤 ou 👻.
- **L'envoi** passe par `core.notifications` de l'Assistant, qui garde sa propre pause globale.

**D-35 · La surveillance.**
- **Au lancement**, si la connexion date de moins de 5 min et que cette session n'est pas déjà suivie : le mode
  « ouverture de session ». Il note aussi les apps lancées dans les 2 premières minutes, qui servent à S5 en
  dernier recours.
- **Sinon**, la session est notée « pas observée ».
- **À chaque tour** : battement, scan (chaque jour, ou tout de suite si un des dossiers de démarrage a changé),
  relevé (énergie toutes les 10 min), purge quotidienne, et zsh + récap chaque semaine.
- **Un tour en panne** ne fait jamais tomber le module : une base devenue illisible est rouverte, c'est-à-dire
  mise de côté et reconstruite.
- **`module.py`** donne au superviseur la boucle, et à `python assistant.py etat` son état.
