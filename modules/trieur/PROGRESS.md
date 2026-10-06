# Avancement — Trieur unifié

| Phase | Statut | Preuve |
|---|---|---|
| P0 Reconnaissance, squelette, check.sh | ✅ | ci-dessous |
| P1 Corpus + vérité terrain | ✅ | 124 documents, 19 types, 11 pièges ; 5 tests |
| P2 Extraction | ⏳ | |
| P3 Classement, champs, nommage | ⏳ | |
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
