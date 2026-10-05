# Décisions — Détecteur de corvées répétées

Chaque choix ambigu, avec les alternatives écartées et la raison. Le plus récent en bas.

## 2026-10-05 · P0 — Reconnaissance

**D-01 · S'intégrer à l'Assistant existant plutôt que créer un projet séparé.**
Le projet de l'assistant existe : c'est ce dépôt (`~/Assistant` sur le Mac), dont le premier module est le tri
Gmail (`modules/mails`). Conformément au §1 de la mission (« respecte ses conventions »), le détecteur devient le
module `modules/corvees`, lancé et relancé par le superviseur de l'Assistant (`superviseur.py`, lui-même confié à
launchd par `python service.py installer`).
*Écarté :* un projet autonome `~/Projets/detecteur-corvees` avec son propre LaunchAgent. Il aurait doublé le
superviseur, la configuration, les notifications et l'accès à Claude, et le nom du LaunchAgent demandé contient un
prénom, qui ne doit pas apparaître dans ce dépôt public.

**D-02 · Emplacements : ceux de l'Assistant.**
Données : `donnees/corvees/` (base `corvees.db` en `chmod 600`, sel HMAC, rapport, propositions). Le dossier
`donnees/` n'est jamais versionné (`.gitignore`). Journal : `logs/assistant.log`, préfixe `[corvees]`, comme tous
les modules. Réglages : `reglages.json` → `modules.corvees`.
*Écarté :* `~/Library/Application Support/DetecteurCorvees/`, `~/Library/Logs/DetecteurCorvees/` et un
`config.toml`. Ils auraient créé un deuxième endroit pour les données, les journaux et les réglages.

**D-03 · Le cerveau : Claude via l'abonnement (`core.cerveau`), pas de clé API.**
L'Assistant n'a pas de clé API Anthropic : il passe par Claude Code (`claude -p`) avec le jeton de l'abonnement
stocké dans `.env`, lu au démarrage par `core.config`. launchd n'hérite pas du shell, mais ce n'est pas un problème
puisque le `.env` est lu par le programme lui-même. Le module réutilise ce canal (plafond quotidien, pause après
panne, journal des appels). Le coût est estimé en jetons × tarif (config) et le plafond mensuel de 2 $ s'applique à
cette estimation.
*Écarté :* le SDK `anthropic` avec `ANTHROPIC_API_KEY` ou le trousseau. Cela ferait une deuxième authentification
à gérer, alors que §6 demande de « réutiliser celle de l'assistant ».

**D-04 · Construit dans un conteneur Linux, pas sur le Mac.**
Cette session tourne dans un conteneur cloud (Linux x86_64, Python 3.11.15, sans `zsh` ni `shellcheck`). Le Mac
cible : MacBook Air Apple Silicon (Homebrew dans `/opt/homebrew`), venv en Python 3.14 (vu dans les sorties de
l'utilisateur). Conséquences :
- tout l'accès natif macOS (NSWorkspace, accessibilité, NSPasteboard, inactivité) est isolé dans
  `capteurs/natif.py`, derrière des interfaces simulées dans les tests ;
- les capteurs portables (fichiers via `watchdog`, historique zsh, SQLite des navigateurs) sont testés pour de vrai
  ici ;
- ce qui exige le vrai Mac (autorisations, mesure sur place) est décrit dans `ACTIONS_HUMAINES.md`, avec une
  commande prête : `python -m modules.corvees e2e`.

**D-05 · Git : le dépôt existe déjà.**
Pas de `git init`. Les commits se font sur la branche de travail, un par phase verte.

**D-06 · Désactivé par défaut, comme les autres modules qui observent.**
`yeux`, `oreilles` et `traduction` sont éteints par défaut. Le détecteur suit la même règle : il s'allume avec
`python assistant.py activer corvees`. Le superviseur le lance alors dans les 2 secondes et le relance s'il tombe.

**D-07 · Dépendances.**
Ajoutées au fonctionnement : `watchdog` (FSEvents sur le Mac) et `jsonschema` (validation des réponses de Claude).
Outils de développement (pytest, pytest-cov, ruff, mypy) : dans `requirements-dev.txt`, jamais dans
`requirements.txt`. Tout s'installe dans le venv de l'Assistant (`.venv`).

**D-08 · La commande `corvees`.**
`python -m modules.corvees <commande>`, ou plus court `python corvees.py <commande>` à la racine, sur le modèle de
`assistant.py`. Un alias zsh `corvees` est proposé dans `ACTIONS_HUMAINES.md`, puisque le `.zshrc` ne doit pas être
modifié.

**D-09 · Tests dans le dépôt.**
`tests/corvees/` : unitaires, simulation, e2e, vie_privee, perf. La porte unique est `modules/corvees/check.sh`.
La configuration des outils (ruff, mypy, pytest, coverage) est dans `pyproject.toml` à la racine, limitée au module.

## 2026-10-05 · P3 — Détecteurs, score, réglage

Réglage fait sur les graines 1 à 5 (jeu A). Les critères ont été vérifiés sur les graines 101 à 505, jamais
utilisées pour régler, puis sur un dernier lot jamais lancé avant (1111 à 5555).

**D-10 · Sessions.** Une session s'arrête après 10 minutes sans action, sur un signal d'inactivité, et à minuit.
Deux actions identiques de suite n'en font qu'une. Les titres de fenêtres ne servent pas à la détection : ils
varient trop. Ils restent notés, caviardés.

**D-11 · D1, croissance de motifs + lift ≥ 8.** On ne prolonge que les motifs déjà présents sur au moins 3 jours.
Pas de répétition d'un même token dans un motif : un aller-retour n'est pas une corvée. Le lift est calculé en
supposant les actions indépendantes.
*Écarté :* un lift calculé avec un modèle de Markov d'ordre 1. Une vraie corvée est déterministe (ses transitions
n'existent que par elle), donc ce modèle lui donnait un lift d'environ 1. *Écarté :* lift ≥ 4, qui laissait passer
des coïncidences 5 à 6 fois plus fréquentes que le hasard parmi des milliers de combinaisons testées.

**D-12 · D1 laisse les ponts purs à D4.** « Appli A → copie → appli B » a toujours un lift énorme par construction,
puisque la copie est toujours entre ses deux applis : seul D4 sait en juger.

**D-13 · D2, concentration.**
- Une appli utilisée toute la journée n'est pas une routine : il faut au moins 60 % de ses occurrences dans le
  créneau, ou 75 % sur le jour de la semaine.
- Le motif hebdomadaire est cherché avant le créneau quotidien : ce qui n'arrive que le lundi est une routine du
  lundi.
- Pour une suite d'actions, il faut 4 jours dans le créneau, et la même heure pour un motif hebdomadaire.
  Parmi des centaines de séquences rares, le hasard en fabrique avec 3 jours ou un même jour de la semaine.

**D-14 · D3, parcours et règles.** Les étapes d'un même fichier sont reliées par l'empreinte de son chemin
(avant → fichier). L'arrivée (le téléchargement) n'est que le contexte. Les noms sont ramenés à leur racine
(« Devoir_Eco_* » → « Devoir_* »). Des variantes trop rares séparément sont réunies sous leur préfixe commun
(au moins 3 caractères, « Lettre_motivation_* »), jamais sous « * » seul : ce ne serait plus une règle.

**D-15 · D4, test statistique au lieu d'un seuil de lift.** On calcule la probabilité de voir autant de copies
A → B par hasard (loi de Poisson), avec une correction de Bonferroni sur le nombre de paires testées, au risque
de 5 %.
*Écarté :* un seuil de lift. Safari est la source de copie dominante, donc un vrai pont Safari → Numbers n'y est
« que » 2,7 fois plus fréquent que le hasard, autant que certaines coïncidences.

**D-16 · D5.** Deux formes sont détectées :
- les lignes enchaînées : au moins 2 sous-commandes, 4 fois, sur 2 jours ;
- les suites de lignes : au plus 5 minutes d'écart, lift ≥ 3.

Le texte entre guillemets devient « * » : un message de commit varie à chaque fois et peut contenir du privé.

**D-17 · Score.**
- *Durée :* la somme du temps habituel de chaque étape, ou la durée mesurée si elle est plus longue, sans
  dépasser 3 fois ce temps. Entre deux étapes, on lit, on réfléchit : ce n'est pas la corvée. Une commande
  compte par sous-commande.
- *Facteurs :*
  - selon le type : fichiers et shell 1,0 ; routine 0,9 (heure fixe : la plus facile à programmer) ;
    séquence 0,6 ; pont 0,5 ;
  - action seule (une appli ou un site) : × 0,1, car c'est déjà instantané (le piège « Spotify ») ;
  - suite de navigation sans horaire : × 0,1. Dans une suite, une copie que D4 n'a pas retenue compte comme de
    la navigation.

**D-18 · Fusion des descriptions d'une même corvée.**
- *Critère :* des étapes en commun (les fichiers comparés par leur squelette : sorte, dossiers, extension), et au
  moins la moitié des occurrences de l'une au même moment que l'autre.
- *Représentant :* le meilleur score, une fois chacun évalué avec son propre horaire.
- *Type :* le plus parlant du groupe.
- *Écartés :* « la plus longue », qui ajoutait des actions de contexte, et « la plus vue », qui préférait une
  sous-séquence diluée par des coïncidences et perdait l'horaire.

**D-19 · Mémoire des refus.** Une corvée refusée est reconnue par ses étapes clés : tout sauf les simples
changements d'appli. « 3 fois plus fréquente » se mesure sur ces étapes clés, de la même façon au moment du refus
et ensuite. Une variante proposée d'abord (6 fois par mois) faisait croire au retour de la corvée entière
(24 fois par mois).

**D-20 · Simulateur.**
- Pendant une corvée, le bruit s'efface : on ne fait pas cinq choses à la fois, et l'énoncé permet au plus une
  action parasite.
- Le piège des secrets varie d'un jour à l'autre. Identique chaque jour, il formait une vraie suite répétée.
- Chaque jour a au moins une session.

**D-21 · Honnêteté de l'évaluation.**
- Le jeu B a été écrit après le réglage sur le jeu A.
- B a révélé des faiblesses génériques, corrigées sans toucher aux corvées : renommages de variantes, noms sans
  chiffres, guillemets, seuil des ponts, créneau des séquences, choix du représentant, hebdomadaire à heure fixe,
  squelette des fichiers. Le jeu A est resté à 100 %.
- Lot final jamais vu (1111 à 5555), laissé tel quel :
  - 49 corvées sur 50 retrouvées (98 %) ;
  - 1 fausse alerte sur 100 places du top 10.

  La corvée manquée est hebdomadaire : 4 occurrences par mois, le cas limite par nature.

**D-22 · Performance.** La fusion est indexée par étape et élaguée : un candidat sous le score minimal divisé
par 3 ne pourra jamais l'atteindre. Les fenêtres du calcul de hasard sont comptées une fois par longueur, et le
créneau est cherché par fenêtre glissante incrémentale. Pour 208 000 événements, l'analyse passe de 73 s à
environ 6 s.

## 2026-10-05 · P4 — Capteurs

**D-23 · C1, relevé toutes les 2 s plutôt qu'abonnement aux notifications.** On interroge NSWorkspace
(`frontmostApplication`) toutes les 2 secondes, et la boucle principale du démon fait tourner la boucle
d'événements de macOS, sans quoi la liste des applis ne se met pas à jour. Le résultat est le même qu'avec
`didActivateApplicationNotification`, mais sans observateur à gérer, et c'est testable. En secours, on prend le
propriétaire de la fenêtre la plus en avant (CGWindowList, sans autorisation).
*Écarté :* `osascript` / System Events, qui déclenche une demande d'autorisation « Automatisation ».

**D-24 · Premier passage : à partir de maintenant.** Les historiques zsh et des navigateurs ne sont pas lus dans
le passé : le détecteur observe à partir de son installation. Les corvées apparaissent donc au bout de quelques
jours, ce qui est le comportement attendu d'un observateur.

**D-25 · zsh, détection d'une réécriture.** Le curseur garde aussi l'empreinte des 64 octets qui le précèdent.
Linux et macOS peuvent redonner le même numéro de fichier (inode) à un historique réécrit, et le nouveau fichier
peut être plus long que l'ancien : sans cette empreinte, la réécriture passait inaperçue (vu en test). Une ligne
sans horodatage, relue après une réécriture, n'est jamais redonnée.

**D-26 · Fichiers : appariement symétrique, suppressions, corbeille.**
- Créations et suppressions attendent 2 s. « Supprimé ici, recréé là-bas sous le même nom » devient un
  déplacement, dans un sens comme dans l'autre : entre deux dossiers surveillés séparément, le système peut
  signaler les deux dans n'importe quel ordre (vu en test).
- Une suppression seule devient `fdel`. Un déplacement vers la corbeille ressemble à une suppression, car
  ~/.Trash exige l'Accès complet au disque. On ne prétend donc pas savoir que c'était la corbeille.
- Les fichiers temporaires et cachés sont ignorés (sauf la corbeille comme destination), ainsi que tout ce qui
  dépasse la profondeur réglée.
- Une conversion : le même nom de fichier, avec une autre extension, juste à côté (des fichiers seulement, pas un
  dossier homonyme).

**D-27 · Presse-papiers.** Chaque copie donne un événement « copie », gardé mais ignoré par la détection. Le pont
A → B est noté quand on change d'appli moins de 2 minutes après. Les types « secret », « éphémère » et
« auto-généré » des gestionnaires de mots de passe sont ignorés entièrement. On ne garde jamais le contenu :
seulement sa longueur et une empreinte HMAC.
