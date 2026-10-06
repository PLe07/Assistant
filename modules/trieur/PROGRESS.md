# Avancement — Trieur unifié

| Phase | Statut | Preuve |
|---|---|---|
| P0 Reconnaissance, squelette, check.sh | ✅ | ci-dessous |
| P1 Corpus + vérité terrain | ✅ | 124 documents, 19 types, 11 pièges ; 5 tests |
| P2 Extraction | ✅ | 18 tests ; temps mesurés ci-dessous |
| P3 Classement, champs, nommage | ✅ | corpus 1 : 100 % des types ; corpus 2 inédit : 97 % / 90 % |
| P4 File, doublons, déplacement sûr, annulation, apprentissage | ✅ | 17 tests de la chaîne + 5 de l'interface Mac |
| P5 Coffre à garanties, Rappels, rétractation, pages HTML | ✅ | 5 tests |
| P6 Couche IA | ✅ | 9 tests + espion sur tout le corpus : 0 fuite |
| P7 Entrées, action rapide, raccourcis | ✅ | 8 tests (horloge imitée) |
| P8 Démon, notifications, doctor, CLI | ✅ | 17 tests ; démon 0,3 % de processeur, 64 Mo |
| P9 Bout en bout réel, performance | ✅ ici · ⏳ Mac | bac à sable : 124 documents, 0 perdu, 0 écrasé, tout annulé intact |
| P10 Installation réelle | ⏳ Mac | `trieur installer` testé en bac à sable ; ACTIONS_HUMAINES.md |
| P11 Revue hostile | ✅ | 8 défauts corrigés, chacun testé ; RAPPORT_FINAL.md |

## P0 — Reconnaissance (✅)

Voir DECISIONS.md D-01 à D-12. Squelette `modules/trieur/`, `tests/trieur/`, `trieur.py`, `check.sh`.

Les suites `corpus`, `securite` et `perf` n'ont pour l'instant qu'un test de squelette (pytest refuse une suite
vide) ; elles sont remplies en P1, P6 et P9.

```
$ PYTHON=…/venv/bin/python modules/trieur/check.sh
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
Required test coverage of 85.0% reached. Total coverage: 91.14%
  ✅ pytest + couverture ≥ 85 %
  ✅ corpus (principal + 2e corpus inédit)
  ✅ sécurité et vie privée
  ✅ performance
CHECK OK
```

## P1 — Corpus et vérité terrain (✅)

`tests/trieur/corpus/` :
- `donnees.py` : émetteurs, produits (18 durables, 8 consommables, 3 d'occasion), personnes et numéros inventés ;
  IBAN, numéros de sécurité sociale et de carte ont des clés valides ;
- `contenu.py` : 19 types, 2 à 10 variantes chacun, avec des pièges de date (impression, échéance, période,
  prélèvement) et de montant (lignes d'un relevé, sous-totaux, TVA) ;
- `rendu.py` : 3 mises en page de PDF texte (dont une où le nom de l'émetteur n'est qu'une image), tickets
  thermiques, scans dégradés (± 7°, flou, bruit, contraste), photos de tickets (fond, ombre, EXIF tourné), HEIC ;
- `generer.py` : le corpus principal et `verite.json`.

Composition (graine 20261006) : 124 entrées, dont 82 PDF texte, 20 scans (12 JPG, 8 PDF image), 9 photos de
tickets (dont 3 avec orientation EXIF), 4 HEIC ; 2 factures envoyées avec la note « garantie 3 ans ».
Pièges : paysage (JPG et HEIC), PDF protégé, PDF corrompu, fichier vide, doublon exact, santé peu lisible, deux
factures au même nom, emoji, fantôme iCloud, 300 pages, courriel avec la facture en pièce jointe.

```
$ pytest tests/trieur/corpus
5 passed in 47.49s
```

## P2 — Extraction (✅)

`modules/trieur/extraction/` :
- `pdf.py` : le texte avec PyMuPDF (pdftotext en repli) ;
  - cas limites : vide, protégé, abîmé (y compris « 0 page ») ;
  - un long PDF : les 3 premières pages et la dernière ;
  - un scan : les pages sont rendues à 200 dpi pour l'OCR ;
  - un logo dans le haut de la 1re page (le nom de l'émetteur dessiné) : il est lu par l'OCR (D-19).
- `image.py` : orientation EXIF, HEIC (`sips` sur le Mac), recadrage du document, PDF cherchable avec le texte en
  calque invisible.
- `ocr.py` : Vision (Mac), tesseract, RapidOCR (tests, D-05/D-18). Les morceaux sont remis en lignes après
  correction de l'inclinaison du scan (D-18). Cache optionnel, versionné.
- `formats.py` : .docx, texte, liens (.url, .webloc, adresse seule), courriel .eml et ses pièces jointes.

Temps réels dans le conteneur, extraction + classement, **sans cache**, moteur RapidOCR (plus lent que Vision) :

```
moteur OCR : rapidocr
heic           n=4  moyenne  2.00 s  max  3.38 s
pdf_texte      n=4  moyenne  0.48 s  max  1.69 s   (le max inclut le 1er chargement du modèle, pour un logo)
photo_exif     n=3  moyenne  1.54 s  max  3.31 s
photo_ticket   n=4  moyenne  0.96 s  max  1.26 s
scan_jpg       n=4  moyenne  3.21 s  max  3.68 s
scan_pdf       n=4  moyenne  2.87 s  max  3.41 s
```
Budgets du §9 : PDF texte < 3 s ✅, photo de ticket < 8 s ✅.

## P3 — Classement, champs, nommage (✅)

`modules/trieur/classement/` :
- `texte.py` (mise à plat), `dates.py` (formats français, étiquette de chaque date, choix selon le type),
  `montants.py` (montant TTC d'après son étiquette, colonnes respectées) ;
- `emetteurs.json` : 166 émetteurs (commerces, sites, supermarchés, énergie, télécoms, banques, organismes,
  mutuelles, assurances, transport, hébergement, agences, marques) ; `emetteurs.py` (en-tête, site, texte ; nom
  lu en haut sinon) ;
- `regles.toml` + `regles.py` : 136 indices pondérés pour 18 types, points par catégorie d'émetteur, confiance ;
- `champs.py` : produits durables, mention de garantie, occasion, achat en ligne, numéro, détail du nom ;
- `nommage.py` : `AAAA-MM-JJ_Emetteur_Type_Detail_Montant.pdf`, 120 caractères au plus, « -2 » si pris, dossier ;
- `garanties/duree.py` : durée (note > mention > légale, D-13) et rappel de rétractation (D-15).

Réglage sur le corpus 1 (il n'y a pas eu d'IA) :
- 1re mesure : type 100 % (PDF) et 85 % (scans), date 88 %, montant 95 %, garanties 72 % ;
- les causes trouvées et corrigées :
  - lignes de scan mélangées (page de travers) → redressement (D-18) ;
  - mots collés par l'OCR → espaces facultatifs dans les règles et les étiquettes de date ;
  - « Délivrée le » pris pour une livraison ;
  - la colonne « Qté » collée au prix (« 1 249,99 ») → colonnes gardées (D-20) ;
  - le logo du générateur coupait les noms longs → corrigé dans le générateur (D-21).

Le 2e corpus (`generer2.py`, 60 documents) a été écrit **après** ce réglage (D-22). Sa 1re mesure est gardée
telle quelle, sans retouche des règles.

```
$ pytest tests/trieur/corpus -s          (OCR en cache ; 7 passed in 116.68s)
corpus 1 (réglage)                         corpus 2 (inédit, 1re mesure)
critère             justes    taux         critère             justes    taux
type_texte         82/82    100.0 %        type_texte         38/39     97.4 %   (seuil 85)
type_image         35/35    100.0 %        type_image         19/21     90.5 %   (seuil 75)
date              116/117    99.1 %        date               58/60     96.7 %   (seuil 85)
montant           117/117   100.0 %        montant            58/60     96.7 %   (seuil 80)
emetteur          117/117   100.0 %        emetteur           58/60     96.7 %
garantie           33/33    100.0 %        garantie           14/14    100.0 %   (seuil 90)
retractation        8/8     100.0 %        retractation        3/3     100.0 %
pieges              6/6     100.0 %        fausse_garantie     0
fausse_garantie     0
```

Ce qui rate encore sur le corpus 2 (pour la revue P11) :
- une attestation scannée dont l'OCR a collé tout le titre (« ATTESTATIONDEPAIEMENT ») → « À vérifier » ;
- une facture de service scannée à 0,71 de confiance (seuil 0,75) → « À vérifier » ;
- une notice Apple : la marque est aussi un site marchand, ce qui tire vers « facture » → « À vérifier » ;
- un ticket d'un magasin inconnu de la base : la marque du produit (Bosch) est prise pour l'émetteur.
Avec Claude (P6), ces documents passeront par lui au lieu d'« À vérifier ».

```
$ PYTHON=…/venv/bin/python modules/trieur/check.sh
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
Required test coverage of 85.0% reached. Total coverage: 96.19%
  ✅ pytest + couverture ≥ 85 %
  ✅ corpus (principal + 2e corpus inédit)
  ✅ sécurité et vie privée
  ✅ performance
CHECK OK
```

## P4 — File, doublons, déplacement sûr, annulation, apprentissage (✅)

- `base.py` (SQLite), `rangement.py` (copie exclusive, empreinte, suppression de l'original), `traitement.py` (la
  chaîne, `annuler`, `corriger`, `apprendre_deplacement`), `systeme.py` (le Mac derrière une interface), `api.py`
  (`modules.trieur.ajouter`).
- Testé : file idempotente ; facture rangée et original supprimé ; un fichier déjà au nom visé jamais écrasé
  (« -2 ») ; doublons selon la source ; erreurs réessayées 3 fois, original intact ; copie fausse ou fichier modifié
  pendant le traitement → rien ne bouge ; photo de facture → PDF cherchable + original archivé, puis annulation
  complète ; photo → Pictures ; PDF protégé → À vérifier ; lien, zip, note ; courriel et sa pièce jointe ;
  Téléchargements seulement si sûr ; corriger (et le suivant du même émetteur est reconnu), corriger l'émetteur,
  déplacement à la main ; API.

## P5 — Coffre à garanties (✅)

- `garanties/coffre.py`, `pages.py`.
- Testé : facture en ligne → fiche, alias, 2 rappels (30 et 7 jours, 9 h) + rétractation (livraison + 11 j) dans
  « Trieur-TEST » ; annuler retire tout ; vieux document : pas de rappel passé ; corriger retire la garantie ;
  garanties à la main, modifier, supprimer, échéances du jour ; Rappels en panne : la fiche reste ; pages HTML
  (échappement, mode sombre, aucun lien externe, une page à toi jamais remplacée).

## P6 — Couche IA (✅)

- `ia/caviardage.py`, `ia/__init__.py`.
- Testé avec un Claude imité : caviardage des données d'une personne fictive ; documents sensibles retenus ;
  réponse valide ; relance unique sur format faux ; pannes 529/429 (attente 2 s puis 4 s), panne définitive sans
  relance ; budget ; IA coupée ; Claude qui voit un document sensible ; dans la chaîne.
- L'espion sur tout le corpus 1 (seuil forcé pour tout envoyer à Claude) :

```
$ pytest tests/trieur/securite -s
89 messages, 18 documents sensibles retenus
5 passed in 39.22s
```
  Aucun des 18 documents sensibles n'est parti ; aucun message ne contient l'IBAN, la carte, le n° de sécurité
  sociale, le courriel, le téléphone, l'adresse, la ville, le nom ou le prénom de la personne fictive ; aucun
  numéro de 13 chiffres ou plus ; chaque extrait fait 3000 caractères au plus ; aucun fichier perdu.

```
$ PYTHON=…/venv/bin/python modules/trieur/check.sh          (après P4-P6)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
Required test coverage of 85.0% reached. Total coverage: 96.28%
96 passed, 1 deselected in 5.12s
  ✅ pytest + couverture ≥ 85 %
  ✅ corpus (principal + 2e corpus inédit)
  ✅ sécurité et vie privée
  ✅ performance
CHECK OK
```

## P7 — Entrées, action rapide du Finder, raccourcis (✅)

- `entrees/surveillance.py` (E1 boîte iCloud et fantômes, E2 À trier, E5 Téléchargements et AirDrop),
  `entrees/finder.py` (E3), `raccourcis/` (§8), E4 = `trieur ajouter` et `modules.trieur.ajouter`.
- Testé avec une horloge imitée : 3 mesures stables avant de prendre un fichier ; fichier qui grossit attendu ;
  fichiers cachés, pages du Trieur, téléchargements en cours ignorés ; fantôme iCloud demandé une fois (relancé
  après 2 min) ; note de l'iPhone ; note orpheline ; Téléchargements : seulement les PDF arrivés après
  l'installation, 2 min de calme ; fichier laissé jamais repris en boucle ; AirDrop ; action rapide (plist valide,
  jamais par-dessus un paquet étranger) ; raccourcis (note enregistrée avant le document) ; signature imitée.

## P8 — Démon, notifications, doctor, commandes (✅)

- `daemon.py`, `notifications.py`, `doctor.py`, `cli.py`, `arborescence.py`, `installer.py` ; ligne 🗂 dans
  `python assistant.py etat` et `python assistant.py trieur …`.
- Testé : de la boîte au classement avec la note « garantie 3 ans » (fiche à 36 mois, note effacée, page du coffre
  écrite, notification) ; 5 documents → un seul résumé ; le matin, la garantie qui finit dans 30 jours (une fois) ;
  déplacement à la main suivi ; la boucle du superviseur ; toutes les commandes (ajouter, journal, statut, coffre,
  garantie, annuler, corriger, ranger-existant, arborescence, pages, doctor, installer).

```
$ pytest tests/trieur/perf -s           (moteur RapidOCR, sans cache ; Vision est plus rapide sur le Mac)
PDF texte : max 0.81 s · photo de ticket : max 1.64 s (rapidocr)
démon : 6.7 ms par tour de 2 s = 0.335 % de processeur ; mémoire au repos 64 Mo, pic 70 Mo
```

```
$ PYTHON=…/venv/bin/python modules/trieur/check.sh          (après P7-P8)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
Required test coverage of 85.0% reached. Total coverage: 95.93%
121 passed, 1 deselected in 10.27s
  ✅ pytest + couverture ≥ 85 %
  ✅ corpus (principal + 2e corpus inédit)         (corpus 1 : émetteur 116/117 après D-46, le reste inchangé)
  ✅ sécurité et vie privée
  ✅ performance
CHECK OK
```

## P9 — Bout en bout et performance (✅ ici, ⏳ sur le Mac)

- `tests/trieur/e2e/test_bout_en_bout.py` : tout le corpus 1 déposé dans la boîte iCloud et « À trier » d'un bac à
  sable, le démon tourne (OCR de la machine, Claude imité) :
  - chaque fichier déposé est retrouvé (rangé, photos, À vérifier) ; aucun ne reste dans les entrées ;
  - deux fichiers placés d'avance aux noms que le Trieur choisit sont intacts (le sien reçoit « -2 ») ;
  - plus de 110 rangés, 2 photos, 1 doublon, 0 erreur ; plus de 32 garanties, alias, rappels dans Trieur-TEST ;
    pages HTML ; notifications regroupées ; le fantôme iCloud demandé ;
  - puis **tout est annulé** : chaque fichier revient à sa place, octet pour octet ; rien ne reste dans Classés.
- `tests/trieur/e2e_mac/test_bout_en_bout_mac.py` : le même chemin sur ton Mac (Vision, tags, alias, Rappels,
  iCloud, sips, plutil, signature d'un raccourci), avec nettoyage garanti (D-53). Hors Mac, il échoue franchement.
- `tests/trieur/perf` : voir P8 (PDF 0,81 s, photo 1,64 s, démon 0,34 %, 64 Mo).

## P10 — Installation (⏳ sur le Mac)

`python trieur.py installer` (testé en bac à sable : dossiers, action rapide, raccourcis, date d'installation,
pages, allumage) ; les étapes sur le Mac et l'iPhone sont dans ACTIONS_HUMAINES.md.

## P11 — Revue hostile (✅)

Voir RAPPORT_FINAL.md § 4 et D-49 à D-52 : 8 défauts trouvés et corrigés, chacun avec son test ; aucun `sudo`,
réseau, shell ni `rm -rf` dans le code (test automatique).

```
$ PYTHON=…/venv/bin/python modules/trieur/check.sh          (final)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
Required test coverage of 85.0% reached. Total coverage: 96.26%
128 passed, 1 deselected in 61.99s (0:01:01)
  ✅ pytest + couverture ≥ 85 %
7 passed in 111.47s (0:01:51)
  ✅ corpus (principal + 2e corpus inédit)
6 passed in 47.24s
  ✅ sécurité et vie privée
2 passed in 14.12s
  ✅ performance
CHECK OK
```

## Sur ton Mac — 1er passage de `tests/trieur/e2e_mac` (macOS 27.0.1, Python 3.14.4)

```
pdf_texte : 0.02 s → facture_achat (0.90), attendu facture_achat
photo_ticket : 0.29 s → ticket_caisse (0.95), attendu ticket_caisse
  n°4 photo-test.heic → classe ticket_caisse 0.95 2025-10-16_Carrefour_Ticket_22,22€.pdf
  … (11 documents : 10 PDF, scans et photos + 1 HEIC, tous rangés)
types justes : 10/10
tags Finder : ['Facture', 'Garantie']
garanties : 9, rappels dans Trieur-TEST : 0
Nettoyage : rien ne reste
FAILED … assert ([])        ← les rappels
WARNING Rappels a refusé : 94:95: syntax error: Il est impossible de régler note à item 3 of argv.
        Accès non autorisé. (-10003)
```
- ✅ Vision : PDF texte 0,02 s, photo de ticket 0,29 s (budgets 3 s et 8 s) ; 10 types justes sur 10 ; HEIC par
  `sips` ; tags du Finder ; alias ; nettoyage complet.
- ❌ Rappels : `note` est un mot réservé d'AppleScript → corrigé (D-54). Les étapes suivantes du test (plutil,
  signature, annulation) n'ont pas encore tourné : 2e passage à faire.

## Sur ton Mac — 2e passage de `tests/trieur/e2e_mac` (après D-54) : ✅

```
pdf_texte : 0.02 s → facture_achat (0.90), attendu facture_achat
photo_ticket : 0.22 s → ticket_caisse (0.95), attendu ticket_caisse
  … 11 documents rangés (dont photo-test.heic → ticket_caisse 0.95)
types justes : 10/10
tags Finder : ['Facture', 'Garantie']
garanties : 9, rappels dans Trieur-TEST : 16
signature du raccourci : ✅

Nettoyage : rien ne reste
1 passed, 5 warnings in 62.09s (0:01:02)
```
- 16 rappels pour 9 garanties : 2 par garantie, sauf celle d'un MacBook reconditionné déjà expirée (aucun rappel
  dans le passé, D-33).
- plutil a validé l'action rapide et les deux raccourcis ; la signature « anyone » marche ; l'annulation a rendu
  les 11 fichiers intacts ; il ne reste ni bac à sable, ni BoiteMac-TEST, ni liste Trieur-TEST.
- Les 5 avertissements viennent de PyMuPDF sous Python 3.14 (« SwigPyPacked has no __module__ ») : sans effet.

## Sur ton Mac — l'installation : ✅ (doctor : 1 faux ❌, corrigé par D-55)

- `trieur.py installer` : tout ✅ (dossiers, boîte iCloud, action rapide, deux raccourcis signés, Téléchargements,
  pages, surveillance allumée).
- `trieur.py doctor` juste après : tout ✅ (bibliothèques, Vision, outils du Mac, 136 indices, 166 émetteurs,
  budget Claude 0,000 $ sur 1,00 $) sauf « ❌ surveillance allumée mais muette » : lancé avant que le superviseur
  ait démarré le Trieur. D-55 : battement dès le premier tour, et doctor qui distingue ⏳ démarrage, superviseur
  arrêté et plantage (2 tests de plus : `test_doctor_dit_pourquoi_la_surveillance_est_muette`,
  `test_le_battement_des_le_premier_tour_et_pendant_une_longue_file`).

## Sur ton Mac — après D-55 : ✅ surveillance active

```
🗂 Trieur : surveille (battement il y a 17 s) · 0 rangé(s), 0 à vérifier
✅ surveillance active (battement il y a 0 s)
✅ documents : 1 ignore
```
- Le Trieur tourne sous le superviseur, avec le nouveau code (battement dès le premier tour).
- « Superviseur : ARRÊTÉ » dans `etat`, lancé juste après `redemarrer` : faux, il redémarrait (D-56).
- « 1 ignore » : un fichier laissé à sa place, écrit maintenant en clair (D-56).

## Ta demande : pas de dossier sur le Bureau (D-57)

« À trier » est maintenant `~/Documents/À trier`. L'installateur retire l'ancien dossier du Bureau s'il est vide,
sinon il le laisse et le dit. 2 tests de plus (`test_l_ancien_a_trier_du_bureau`,
`test_l_ancien_a_trier_rempli_entre_deux_n_est_pas_touche`).

## Sur ton Mac — après D-57 : ❌ 109 fichiers de ton propre « À trier » examinés → D-58

```
✅ dossier /Users/…/Documents/À trier          ← il existait déjà, avec tes fichiers
✅ ancien dossier /Users/…/Desktop/À trier retiré du Bureau (il était vide)
✅ documents : 109 erreur, 1 laissé à sa place (pas assez sûr pour le déplacer)
```
- Aucun fichier rangé (0 classé, 0 à vérifier) : les 109 sont tombés en erreur avant tout déplacement.
- Corrigé par D-58 : « À trier » doit être un dossier du Trieur ; nouveau nom `~/Documents/À trier par
  l'assistant` ; ce qui a été vu chez toi est oublié au redémarrage, seulement s'il n'y a aucune action au journal.
  L'installateur affiche cette preuve.
- 4 tests de plus (`tests/trieur/unitaires/test_dossier_a_toi.py`), dont ton cas : une vraie facture posée dans un
  « À trier » à toi n'est ni lue ni déplacée, et son contenu et sa date restent identiques.

