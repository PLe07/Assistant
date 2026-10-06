# Avancement — Bouclier

Reprise après coupure : lire ce fichier et DECISIONS.md, puis reprendre à la première phase non cochée.

| Phase | État | Preuve |
|---|---|---|
| P0 Environnement, intégrité, squelette, check.sh, liste blanche | ✅ | ci-dessous |
| P1 Corpus d'arnaques | ✅ | 225 + 80 messages, ci-dessous |
| P2 Analyse locale n°20 | ✅ | 100 % / 0 % sur les deux corpus, ci-dessous |
| P3 IA, caviardage, veto, budget, réflexes | ✅ | veto 1 220/1 220, ci-dessous |
| P4 Inventaire n°18 | ✅ | précision 100 %, rappel 100 % sur 60 services, ci-dessous |
| P5 Fuites n°19 | ⏳ | |
| P6 Métadonnées n°21 | ⏳ | |
| P7 Fiche urgence n°22 | ⏳ | |
| P8 Raccourcis, actions rapides, iCloud | ⏳ | |
| P9 Démon, tableau de bord, doctor, bout en bout | ⏳ | |
| P10 Installation réelle | ⏳ | |
| P11 Revue hostile (2 passes) | ⏳ | |

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
