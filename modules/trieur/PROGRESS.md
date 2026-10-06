# Avancement — Trieur unifié

| Phase | Statut | Preuve |
|---|---|---|
| P0 Reconnaissance, squelette, check.sh | ✅ | ci-dessous |
| P1 Corpus + vérité terrain | ✅ | 124 documents, 19 types, 11 pièges ; 5 tests |
| P2 Extraction | ✅ | 18 tests ; temps mesurés ci-dessous |
| P3 Classement, champs, nommage | ✅ | corpus 1 : 100 % des types ; corpus 2 inédit : 97 % / 90 % |
| P4 File, doublons, déplacement sûr, annulation, apprentissage | ⏳ | |
| P5 Coffre à garanties, Rappels, rétractation, pages HTML | ⏳ | |
| P6 Couche IA | ⏳ | |
| P7 Entrées, action rapide, raccourcis | ⏳ | |
| P8 Démon, notifications, doctor, CLI | ⏳ | |
| P9 Bout en bout réel, performance | ⏳ | |
| P10 Installation réelle | ⏳ | |
| P11 Revue hostile | ⏳ | |

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
