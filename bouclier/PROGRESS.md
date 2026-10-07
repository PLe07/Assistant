# Avancement — Bouclier

Reprise après coupure : lire ce fichier et DECISIONS.md, puis reprendre à la première phase non cochée.

| Phase | État | Preuve |
|---|---|---|
| P0 Environnement, intégrité, squelette, check.sh, liste blanche | ✅ | ci-dessous |
| P1 Corpus d'arnaques | ✅ | 225 + 80 messages, ci-dessous |
| P2 Analyse locale n°20 | ✅ | 100 % / 0 % sur les deux corpus, ci-dessous |
| P3 IA, caviardage, veto, budget, réflexes | ✅ | veto 1 220/1 220, ci-dessous |
| P4 Inventaire n°18 | ✅ | précision 100 %, rappel 100 % sur 60 services, ci-dessous |
| P5 Fuites n°19 | ✅ | croisement, date, une notification par fuite, ci-dessous |
| P6 Métadonnées n°21 | ✅ | 7 formats + vidéo, SSIM ≥ 0,99, ICC gardé, ci-dessous |
| P7 Fiche urgence n°22 | ✅ | numéros sourcés, PDF lu, A6 une page, ci-dessous |
| P8 Raccourcis, actions rapides, iCloud | ✅ | plists valides, entrée/réponse iCloud testées, ci-dessous |
| P9 Démon, tableau de bord, doctor, bout en bout | ✅ | un « jour » de démon simulé, Gmail intact, ci-dessous |
| P10 Installation | ✅ | installée deux fois sur ton Mac : relance launchd 30 s, iCloud 5 à 11 s, intégrité identique (RAPPORT_FINAL §6) |
| P11 Revue hostile (2 passes) | ✅ | 39 pièges inédits 🟠/🔴, 15 vrais messages ⚪, 6 corrections, RAPPORT_FINAL.md |

## P0 — Environnement, empreinte, squelette (✅)

- Empreinte « avant » prise **avant la première ligne de Bouclier** : `integrite/etat_avant.json`
  (455 fichiers du dépôt hors `bouclier/`, arbre git hors `bouclier/`, `.zshrc`, liste de `BoiteMac/`…).
- `integrite/verifier.sh` au début et à la fin de `check.sh`.
- Liste blanche du réseau (`bouclier/reseau.py`) et filet de test qui coupe et espionne le réseau (`tests/conftest.py`).
- Fondations : réglages, caviardage, base SQLite (600, base abîmée mise de côté), journal caviardé,
  notifications (3 par jour, silence 23 h – 8 h), interface du Mac.

```
$ ./check.sh
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
  ✅ pytest : unitaires et intégrité
  ✅ sécurité, réseau, vie privée
TOTAL                      574     24    96%
  ✅ couverture ≥ 90 % sur bouclier/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```

## P1 — Corpus d'arnaques (✅)

- `tests/corpus_arnaques/generer.py` : 225 messages dans le corpus principal (135 arnaques des 14 familles, 10
  injections, 80 légitimes dont des pièges), 80 dans le 2e corpus (48 arnaques, 32 légitimes) écrit **avant** les
  règles, avec des marques et des domaines absents du premier et de la liste des marques.
- SMS en texte, mails complets (en-têtes, Authentication-Results, Reply-To, désinscription, texte + HTML, base64,
  quoted-printable, ISO-8859-1). Variantes : fautes, émojis, raccourcisseurs, punycode, sosies, faux en-têtes.
- Contexte imité déterministe : RDAP (4/10 récents, 3/10 inconnus, 3/10 anciens), flux (1 lien piégé sur 5),
  inventaire (cliente de La Banque Postale et de Boursobank).

```
$ ./check.sh   (extrait)
  ✅ corpus d'arnaques (principal + 2e corpus inédit)
CHECK OK
```

## P2 — Analyse locale du détecteur n°20 (✅)

- `bouclier/arnaque/` : extraction (SMS, .eml avec texte + HTML + vraies adresses des liens, image par OCR),
  en-têtes (SPF/DKIM/DMARC, nom affiché, Reply-To), liens (sosies de 56 marques, punycode, caractères trompeurs,
  raccourcisseurs, adresse en chiffres, « @ » trompeur, extensions risquées, hébergeurs gratuits), date de création
  par RDAP (nom de domaine seulement, cache 1 an), flux OpenPhish et URLhaus téléchargés et consultés en local,
  13 familles d'arnaques françaises, faux proche, pression psychologique, demandes dangereuses, injection,
  croisement avec l'inventaire (« ta banque » chez qui tu n'as pas de compte).
- 20 « sondes » écrites après les réglages (10 arnaques, 10 vrais messages) : toutes bien classées.

```
$ ./check.sh
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
92 passed in 1.91s
  ✅ pytest : unitaires et intégrité
12 passed in 9.66s
  ✅ corpus d'arnaques (principal + 2e corpus inédit)
28 passed in 0.17s
  ✅ sécurité, réseau, vie privée
TOTAL                             1588     44    97%
  ✅ couverture ≥ 90 % sur bouclier/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```

Analyse locale seule, sans IA (`tests/.cache/scores.md`) :

| Corpus | Arnaques 🔴 | 🟠 | 🟡 | ⚪ | Légitimes 🔴 | 🟠 | 🟡 | ⚪ |
|---|---|---|---|---|---|---|---|---|
| principal (145 arnaques dont 10 injections, 80 légitimes) | 125 | 20 | 0 | 0 | 0 | 0 | 0 | 80 |
| 2e corpus inédit (48 arnaques, 32 légitimes) | 32 | 16 | 0 | 0 | 0 | 0 | 0 | 32 |

Arnaques 🟠/🔴 : 100 % (cible ≥ 95 %) · arnaques ⚪ : 0 · légitimes 🔴 : 0 % (≤ 2 %) · légitimes 🟠 : 0 % (≤ 10 %).
Injections : les 10 du corpus en 🟠/🔴 ; 10 injections greffées sur chacune des 135 arnaques ne font jamais baisser
le score.

## P3 — IA, caviardage, injection, veto, budget, réflexes (✅)

- `arnaque/ia.py` : client SDK (clé API : environnement ou trousseau `bouclier-anthropic`) ou `claude -p` (jeton
  `bouclier-claude`), demande caviardée dans une balise à nombre aléatoire, JSON pydantic (pas de niveau « sûr »),
  un seul nouvel essai si JSON invalide, 2 s puis 4 s sur 429/529/5xx, budget 2 $/mois estimé avant et compté après.
- `arnaque/veto.py` : l'IA monte librement, descend d'un niveau au plus (confiance ≥ 0,6), jamais sous 🟠 avec un
  indice critique ; ses phrases rassurantes, ses liens, ses numéros et son jargon sont écartés.
- `arnaque/reponse.py` + `reflexes.json` : la réponse au format du §3.4, gestes tirés de la base (33700,
  signal-spam.fr, opposition, THESEE, Perceval, 17Cyber, Info Escroqueries), 5 réflexes de base pour le raccourci.
- `urgence/sources.json` : chaque numéro et site avec ses pages officielles (D-14) ; revérification en ligne sur le Mac.
- `arnaque/historique.py` (caviardé, 90 jours), `arnaque/analyse.py` (l'enchaînement), `cli.py` (`verifier`,
  `historique`), `arnaque/ocr.py` + `ocr_vision.py` (Apple Vision sur le Mac).
- Veto avec IA imitée contradictoire : 305 messages × 4 avis = 1 220 cas, 0 violation, aucune réponse « sûr ».
- Caviardage de bout en bout : nom, téléphone, adresse, e-mail, IBAN et carte plantés absents de la demande à l'IA,
  du journal et de l'historique.
- Test réel avec l'IA (`-m reel`, 6 messages dont 2 injections, < 0,03 $) : prévu sur le Mac (P10).

```
$ ./check.sh
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
136 passed in 3.99s
  ✅ pytest : unitaires et intégrité
14 passed in 10.36s
  ✅ corpus d'arnaques (principal + 2e corpus inédit)
30 passed in 2.17s
  ✅ sécurité, réseau, vie privée
TOTAL                             2246     48    98%
  ✅ couverture ≥ 90 % sur bouclier/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK

$ bouclier verifier "Colissimo : votre colis est en attente. Payez 1,99 € : https://colissimo-suivi-frais.top/p"
🔴 Arnaque très probable — faux message « Colissimo »
• Le lien mène à « colissimo-suivi-frais.top », pas au site officiel de Colissimo (laposte.fr).
• Il te demande de payer 1,99 € pour un colis : La Poste et les transporteurs ne font jamais ça par SMS ou par mail.
• Le site se termine par « .top », une extension très utilisée par les arnaques.
👉 Ne clique pas. Signale le SMS au 33700. Supprime-le.
Déjà payé ou donné ta carte ? Opposition tout de suite au 0 892 705 705, puis plainte en ligne (THESEE).
```

## P4 — Inventaire des comptes n°18 (✅)

- `comptes/imap_lecture_seule.py` : Gmail en EXAMINE, UID SEARCH, UID FETCH avec BODY.PEEK/FLAGS seulement ; tout
  le reste est refusé avant envoi. Dossier « Tous les messages » trouvé par l'attribut \All.
- `comptes/navigateurs.py` : Chrome, Brave, Edge, Arc (copie de `Login Data`, une seule requête
  `origin_url, username_value`), Firefox (`logins.json`, champs « password » écartés à la lecture).
- `comptes/services.json` : 2 814 services, dont 163 courants en France avec un lien direct de suppression (D-19).
- `comptes/inventaire.py` + `lancer.py` + `rapport.py` + `tableau_de_bord.py` : classement compte / abonnement,
  dernière activité, statuts posés par toi (`bouclier compte vinted supprimer`), rapport local `Bouclier.html`.
- Boîte imitée de 60 services (40 comptes, 20 abonnements, 25 mails de personnes, sujets en UTF-8 brut et encodés) :
  **précision 100 %, rappel 100 %**, drapeaux de 20 messages identiques avant et après, 0 commande interdite.
- Base `Login Data` de test avec une colonne mot de passe remplie de leurres : jamais lue (requêtes espionnées).

```
$ ./check.sh
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
136 passed in 4.21s
  ✅ pytest : unitaires et intégrité
14 passed in 10.84s
  ✅ corpus d'arnaques (principal + 2e corpus inédit)
27 passed in 1.40s
  ✅ inventaire des comptes et fuites
30 passed in 2.04s
  ✅ sécurité, réseau, vie privée
TOTAL                                     2936     86    97%
  ✅ couverture ≥ 90 % sur bouclier/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```

## P5 — Alerte fuites n°19 (✅)

- `fuites/hibp.py` : liste publique Have I Been Pwned (sans clé), cache du jour, copie gardée en cas de panne,
  option payante par adresse (clé dans config.toml, désactivée par défaut).
- `fuites/croisement.py` : correspondance par service (sous-domaines, alias de marque) ou domaine, filtre de date
  (fuite antérieure au compte écartée), une seule notification par fuite (résumé unique au premier passage).
- `fuites/traductions.py` : les données exposées en français ; `fuites/rapport.py` : partie du tableau de bord
  avec « que faire » et l'attribution CC BY 4.0 ; `bouclier fuites [--mettre-a-jour]`.
- Fixture HIBP de 7 fuites (dont spam, fabriquée, sans domaine, antérieure au compte, site inconnu) : seules les
  2 bonnes ressortent ; une nouvelle fuite → 1 notification, jamais 2.

```
$ ./check.sh
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
136 passed in 4.73s
  ✅ pytest : unitaires et intégrité
14 passed in 11.00s
  ✅ corpus d'arnaques (principal + 2e corpus inédit)
35 passed in 1.62s
  ✅ inventaire des comptes et fuites
30 passed in 2.05s
  ✅ sécurité, réseau, vie privée
TOTAL                                     3165     93    97%
  ✅ couverture ≥ 90 % sur bouclier/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```

## P6 — Nettoyeur de métadonnées n°21 (✅)

- `metadonnees/formats/` : image (JPEG, PNG, WebP sans perte ; TIFF, HEIC ; orientation appliquée ; ICC gardé ;
  option date), pdf (informations, XMP, PieceInfo, auteurs d'annotations), office (core/app/custom ; commentaires et
  révisions signalés), video (ffmpeg).
- `metadonnees/lecture.py` (le rapport : « position GPS (Bordeaux), appareil (Apple iPhone 15), numéro de série,
  auteur… »), `verif.py` (relecture indépendante + exiftool s'il est là), `nettoyeur.py` (copie « (propre) »,
  original jamais modifié, `--remplacer` par la Corbeille du Finder), `bouclier nettoyer`.
- Fixtures générées avec GPS, appareil, numéro de série, auteur, XMP, IPTC, profil ICC « Display P3 » (un vrai
  profil v2) ; JPEG avec image annexe ; photo en orientation 6.
- Résultats : 0 métadonnée sensible restante (octets bruts + Pillow + pikepdf + zip), pixels identiques pour
  JPEG/PNG/WebP, SSIM ≥ 0,99 après rotation, ICC « Display P3 » conservé, empreinte de l'original identique.
  Les tests ont trouvé deux vrais défauts, corrigés : Pillow recopiait le commentaire JPEG et pillow-heif le XMP de
  l'original lors d'un réenregistrement.

```
$ ./check.sh
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
136 passed in 4.45s
  ✅ pytest : unitaires et intégrité
14 passed in 12.13s
  ✅ corpus d'arnaques (principal + 2e corpus inédit)
35 passed in 1.48s
  ✅ inventaire des comptes et fuites
18 passed in 1.11s
  ✅ métadonnées et fiche urgence
30 passed in 2.06s
  ✅ sécurité, réseau, vie privée
TOTAL                                     3758    139    96%
  ✅ couverture ≥ 90 % sur bouclier/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```

## P7 — Fiche urgence hors-ligne n°22 (✅)

- `urgence/fiche.py` (contenu et HTML autonome), `pdf.py` (A4), `carte_a6.py` (une page), `ecran_verrouille.py`
  (1179 × 2556), `infos.py` (`mes_infos_urgence.toml` commenté, sans santé), `service.py` (génération, copie
  iCloud, revérification en ligne, rappel des 6 mois), `bouclier urgence [generer|editer|verifier|ouvrir]`.
- Tests : chaque numéro affiché est dans `sources.json` avec des pages officielles et une date ; le texte du PDF
  (pypdf) contient tous les numéros ; le HTML n'a ni `src`, ni feuille de style, ni police extérieure ; la carte A6
  fait 1 page au format A6 ; une ligne vide n'apparaît pas ; « allergique… », « O+ » écartés ; un numéro disparu de
  sa page est retiré et signalé une seule fois ; rappel à 6 mois, pas avant.
- Rendus regardés (carte, écran verrouillé) : deux défauts de mise en page corrigés (nom coupé, ligne qui débordait).

```
$ ./check.sh
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
136 passed in 4.48s
  ✅ pytest : unitaires et intégrité
14 passed in 10.64s
  ✅ corpus d'arnaques (principal + 2e corpus inédit)
35 passed in 1.72s
  ✅ inventaire des comptes et fuites
25 passed in 2.80s
  ✅ métadonnées et fiche urgence
30 passed in 1.98s
  ✅ sécurité, réseau, vie privée
TOTAL                                     4230    159    96%
  ✅ couverture ≥ 90 % sur bouclier/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```

## P8 — Raccourcis iPhone, actions rapides, entrée iCloud (✅)

- `raccourcis/generer.py` : « Arnaque ? » (nom unique, `Bouclier/entree/`, 20 × 3 s, réponse affichée, 5 réflexes
  embarqués) et « Envoyer sans traces » (100 % iPhone) ; plists binaires, `plutil -lint`, `shortcuts sign --mode
  anyone` (sur le Mac) ; `raccourcis/recettes_manuelles.md` (plan B, noms d'actions en français).
- `raccourcis/actions_rapides.py` : « Est-ce une arnaque ? » (Finder et texte sélectionné), « Nettoyer les
  métadonnées » ; `bouclier verifier --stdin --fenetre`, `bouclier nettoyer --fenetre`.
- `entree_icloud.py` : fichiers fantômes iCloud demandés (`brctl download`, relance toutes les 2 min), taille stable,
  traitement unique, réponse écrite d'un coup dans le même dossier iCloud, notification même la nuit (ta demande),
  purge des copies de plus de 30 jours.

```
$ ./check.sh
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
146 passed in 4.32s
  ✅ pytest : unitaires et intégrité
14 passed in 10.70s
  ✅ corpus d'arnaques (principal + 2e corpus inédit)
35 passed in 1.59s
  ✅ inventaire des comptes et fuites
25 passed in 2.63s
  ✅ métadonnées et fiche urgence
30 passed in 2.31s
  ✅ sécurité, réseau, vie privée
TOTAL                                     4494    169    96%
  ✅ couverture ≥ 90 % sur bouclier/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```

## P9 — Démon, Gmail, doctor, tableau de bord, bout en bout (✅)

- `daemon.py` : boucle de 3 s réveillée par FSEvents ; tâches datées en base (D-25) ; une brique en panne n'arrête
  jamais les autres ; notifications de la nuit envoyées à 8 h ; tableau de bord réécrit après chaque changement.
- `surveillance_gmail.py` : boîte de réception en lecture seule, à partir du jour où Gmail est relié (D-26) ; délai
  10 / 20 / 40 / 60 min après un échec.
- `doctor.py`, score « Hygiène numérique » et ses 3 actions dans le tableau de bord (D-27).
- `installation.py` : ce que `install.sh` pose, vérifié « à nous » avant d'y toucher (D-28).
- `tests/e2e/` (dans `check.sh`) : un jour de démon sur un faux Mac (raccourci → réponse, Gmail → alerte, flux,
  fuites, inventaire, fiche), drapeaux Gmail identiques avant/après, panne isolée, réglages abîmés, installation
  relancée deux fois, plist d'un autre jamais touché.
- Bug trouvé par le test : un compte supprimé demandait encore la double authentification. Corrigé.

```
$ bouclier installation preparer   (dans un faux dossier personnel)
  ✅ réglages créés : ~/Library/Application Support/Bouclier/config.toml
  ✅ commande bouclier : ~/.local/bin/bouclier
  ✅ action rapide « Est-ce une arnaque » : installée
  ✅ action rapide « Est-ce une arnaque (texte) » : installée
  ✅ action rapide « Nettoyer les métadonnées » : installée
  ✅ agent de démarrage : ~/Library/LaunchAgents/com.<session>.bouclier.plist
  ⚠️ iCloud Drive introuvable : le raccourci « Arnaque ? » ne pourra pas joindre le Mac
$ bouclier tableau --sans-ouvrir
🛡️ Hygiène numérique : 76/100
  1. Lance l'inventaire de tes comptes : bouclier inventaire
  2. Prépare ta fiche urgence : bouclier urgence editer, puis bouclier urgence
  3. Relie Gmail en lecture seule pour que les mails piégés soient repérés (ACTIONS_HUMAINES.md)

$ ./check.sh
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
146 passed in 3.92s
  ✅ pytest : unitaires et intégrité
14 passed in 9.85s
  ✅ corpus d'arnaques (principal + 2e corpus inédit)
35 passed in 1.67s
  ✅ inventaire des comptes et fuites
25 passed in 2.39s
  ✅ métadonnées et fiche urgence
30 passed in 1.92s
  ✅ sécurité, réseau, vie privée
10 passed, 1 deselected in 4.78s
  ✅ bout en bout (démon, doctor, installation)
TOTAL                                     5033    189    96%
  ✅ couverture ≥ 90 % sur bouclier/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```

## P10 — Installation (✅ sur Mac imité ; la preuve réelle est la sortie de `./install.sh` sur ton Mac)

- `install.sh` (8 étapes, D-30) et `uninstall.sh` ; `bouclier installation verifier` (kill puis relance, aller-retour
  iCloud texte et capture, nettoyage) ; démon à deux rythmes (D-29) ; empreinte launchd sans pid (D-31) ;
  `tests/e2e_mac` (D-32).
- `tests/e2e/test_scripts_installation.py` : install.sh deux fois, uninstall.sh deux fois puis `--tout`, dans un
  Mac imité où le démon tourne pour de vrai ; refus de sudo et de Linux.
- `tests/e2e` : un inventaire interminable ne retarde pas la réponse au raccourci (fil « bouclier-taches »).

```
$ ./install.sh   (Mac imité : faux launchd, Linux, réseau coupé)
▶ 1/8 Python 3.11 ou plus
▶ 2/8 Empreinte des autres projets (avant)
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
▶ 3/8 Environnement Python de Bouclier
  déjà à jour
▶ 4/8 Dossiers, commande bouclier, actions rapides, agent de démarrage
  ✅ commande bouclier : ~/.local/bin/bouclier
  ✅ action rapide « Est-ce une arnaque » : installée
  ✅ action rapide « Est-ce une arnaque (texte) » : installée
  ✅ action rapide « Nettoyer les métadonnées » : installée
  ✅ agent de démarrage : ~/Library/LaunchAgents/com.<session>.bouclier.plist
  ✅ dossier iCloud : ~/Library/Mobile Documents/com~apple~CloudDocs/Bouclier
▶ 5/8 Raccourcis « Arnaque ? » et « Envoyer sans traces »
  ⚠️ Arnaque ?.shortcut non signé (la commande « shortcuts » n'existe pas ici (macOS 12 ou plus)) : recette manuelle dans ACTIONS_HUMAINES.md
▶ 6/8 Démarrage de la surveillance
  com.<session>.bouclier en marche
▶ 7/8 Vérification : arrêt brutal puis relance, demande déposée dans iCloud
  ✅ launchctl print : com.<session>.bouclier tourne (pid 1948)
  ✅ kill 1948 : relancé par launchd en 2 s (pid 1962)
  ✅ texte déposé dans iCloud : réponse du démon en 4 s (⚪ Pas de signe d'arnaque détecté)
  ✅ fichiers de test retirés d'iCloud
  ⚠️ capture d'écran : reçu mais pas lu (lecture des images indisponible sur cet ordinateur)   ← Linux : pas d'Apple Vision
▶ 8/8 Bilan
✅ démon : com.<session>.bouclier tourne (pid 1962), dernier tour il y a 0 s
✅ inventaire : 0 comptes, dernier inventaire : 07/10/2026 07:15
✅ fiche urgence : générée le 07/10/2026 07:15, copiée sur iCloud
INTÉGRITÉ OK : identique à avant_installation.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
✅ Bouclier est installé et surveille.
Adresses tentées par tous les processus : openphish.com, urlhaus.abuse.ch, haveibeenpwned.com et des sites
officiels (gouv.fr, service-public.fr, chu-bordeaux.fr, centres-antipoison.net, ars.sante.fr) : toutes permises.

$ ./uninstall.sh
  ✅ surveillance arrêtée : com.<session>.bouclier
  ✅ agent retiré, commande retirée, 3 actions rapides retirées
INTÉGRITÉ OK : identique à avant_desinstallation.json
✅ Bouclier est retiré.

$ ./check.sh
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
147 passed in 3.72s
  ✅ pytest : unitaires et intégrité
14 passed in 9.07s
  ✅ corpus d'arnaques (principal + 2e corpus inédit)
35 passed in 1.37s
  ✅ inventaire des comptes et fuites
25 passed in 2.19s
  ✅ métadonnées et fiche urgence
30 passed in 1.75s
  ✅ sécurité, réseau, vie privée
14 passed, 1 deselected in 23.59s
  ✅ bout en bout (démon, doctor, installation)
TOTAL                                     5148    198    96%
  ✅ couverture ≥ 90 % sur bouclier/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```

## P11 — Revue hostile en deux passes (✅)

- Passe 1 : 25 pièges inédits et 15 vrais messages ; corrections (D-33) : faux positif 3-D Secure, caractères
  invisibles, phrases des sosies et du punycode, « activez votre dispositif », énergie de la boucle, erreurs
  imprévues caviardées. Mails authentifiés passant par SendGrid ou Mailchimp : ⚪.
- Passe 2 : 14 nouveaux pièges, tous repérés sans correction.
- README, ACTIONS_HUMAINES, INTEGRATION (`etat.json`, `verifier --json`), RAPPORT_FINAL.

```
$ python -m tests.corpus_arnaques.mesure principal
| | 🔴 | 🟠 | 🟡 | ⚪ |
| Arnaques | 125 | 20 | 0 | 0 |
| Légitimes | 0 | 0 | 0 | 80 |
$ python -m tests.corpus_arnaques.mesure inedit
| Arnaques | 32 | 16 | 0 | 0 |
| Légitimes | 0 | 0 | 0 | 32 |

$ ./check.sh
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
147 passed in 3.71s
  ✅ pytest : unitaires et intégrité
69 passed in 9.54s
  ✅ corpus d'arnaques (principal + 2e corpus inédit)
35 passed in 1.57s
  ✅ inventaire des comptes et fuites
25 passed in 2.31s
  ✅ métadonnées et fiche urgence
30 passed in 1.79s
  ✅ sécurité, réseau, vie privée
16 passed, 1 deselected in 24.25s
  ✅ bout en bout (démon, doctor, installation)
TOTAL                                     5206    200    96%
  ✅ couverture ≥ 90 % sur bouclier/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```

## Après la première installation réelle (✅)

Sur ton Mac : deux `./install.sh` réussis (RAPPORT_FINAL §6). Corrigé ensuite (D-36) : OpenPhish (www + miroir
officiel GitHub, raison de l'échec dans doctor, nouvel essai toutes les heures), `gmail-relier` qui demande l'adresse
et teste la connexion, attente du premier tour avant le bilan, inventaire vide expliqué, « capture d'écran déposée ».
