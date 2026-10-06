# Rapport final — Trieur unifié

Construit le 6 octobre 2026, phases P0 à P11. Chaque preuve ci-dessous est la sortie réelle d'une commande. Le
détail est dans [PROGRESS.md](PROGRESS.md), les choix dans [DECISIONS.md](DECISIONS.md) (D-01 à D-53), ce qui te
reste dans [ACTIONS_HUMAINES.md](ACTIONS_HUMAINES.md).

Légende : ✅ fait et prouvé ; ⏳ prouvé dans l'environnement de construction (conteneur Linux, Mac imité), à
confirmer sur ton Mac par les commandes d'ACTIONS_HUMAINES.md.

## Critères (§10)

| Critère | Seuil | Corpus 1 (réglage) | Corpus 2 (inédit, 1re mesure) |
|---|---|---|---|
| Type, PDF texte | ≥ 95 % (2e : 85 %) | ✅ 100 % (82/82) | ✅ 97,4 % (38/39) |
| Type, scans et photos | ≥ 85 % (2e : 75 %) | ✅ 100 % (35/35) | ✅ 90,5 % (19/21) |
| Date | ≥ 95 % (2e : 85 %) | ✅ 99,1 % | ✅ 96,7 % |
| Montant | ≥ 90 % (2e : 80 %) | ✅ 100 % | ✅ 96,7 % |
| Fin de garantie | 100 % (2e : 90 %) | ✅ 100 % (33/33) | ✅ 100 % (14/14) |
| Fausses garanties | 0 | ✅ 0 | ✅ 0 |
| Fichiers perdus | 0 | ✅ 0 (bout en bout : 124 déposés, tous retrouvés, puis tous rendus intacts) | |
| Écrasements | 0 | ✅ 0 (fichiers placés d'avance aux noms visés : intacts) | |
| Fuites vers Claude | 0 | ✅ 0 sur 89 messages espionnés ; 18 documents sensibles jamais envoyés | |
| PDF texte | < 3 s | ✅ 0,81 s max (RapidOCR) · ✅ 0,02 s avec Vision sur ton Mac | |
| Photo de ticket | < 8 s | ✅ 1,64 s max (RapidOCR) · ✅ 0,22 s avec Vision sur ton Mac | |
| Démon | < 0,5 % CPU, < 150 Mo | ✅ 0,34 % (400 fichiers dans Téléchargements), 64 Mo, pic 70 Mo · ⏳ Mac | |
| Tags, alias, Rappels, iCloud, HEIC, raccourcis signés | | ✅ sur ton Mac (`e2e_mac`, 2e passage : 10/10 types, 16 rappels, signature ✅, rien ne reste) | |

## 1. check.sh

```
$ PYTHON=…/venv/bin/python modules/trieur/check.sh
All checks passed!
  ✅ ruff check
87 files already formatted
  ✅ ruff format
Success: no issues found in 40 source files
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
(Le test « deselected » est l'appel réel à Claude, lancé à la main : D-36.)

## 2. Ce qui marche

- **Entrées** : boîte iCloud (y compris les fichiers pas encore téléchargés), « À trier », action rapide du Finder,
  commande et API, Téléchargements (PDF sûrs, arrivés après l'installation), AirDrop ; note de l'iPhone.
- **Lecture** : PDF (protégés, abîmés, vides, 300 pages), scans, photos (orientation, recadrage, HEIC), logo lu par
  l'OCR, .docx, texte, liens, courriels et leurs pièces jointes.
- **Classement local** : 19 types, 166 émetteurs, dates et montants français, nom `AAAA-MM-JJ_Emetteur_Type_
  Detail_Montant.pdf`, dossiers, tags ; Claude seulement si les règles hésitent, sur un texte caviardé.
- **Sûreté** : copie vérifiée avant suppression, jamais d'écrasement, `annuler` complet, `corriger` qui apprend.
- **Coffre** : garanties (note > mention > légale), alias, rappels à 30 et 7 jours, rétractation, pages HTML.

## 3. Ce qui tourne en mode dégradé, et pourquoi

- **Ici, l'OCR est RapidOCR**, pas Vision (pas de Mac dans le conteneur, D-05) : il perd des espaces et des accents.
  Les scores ci-dessus sont donc prudents ; Vision est mesuré par `e2e_mac` et par `check.sh` sur ton Mac.
- **Les tags, alias, Rappels, brctl, sips, shortcuts** sont imités ici ; sur ton Mac, `tests/trieur/e2e_mac` les a
  vérifiés pour de vrai au 2e passage (le 1er avait trouvé le mot réservé `note` dans le script des Rappels, D-54).
- **Le format des raccourcis** (`.shortcut`) n'a pas pu être importé sur un iPhone : la recette manuelle en 6 étapes
  est prête si l'import échoue (D-41).
- Sur le 2e corpus, 4 documents vont dans « À vérifier » au lieu d'être rangés (titre collé par l'OCR, notice d'une
  marque qui vend aussi en ligne) : Claude les reprend quand il est permis.

## 4. La revue hostile (P11)

Relu en cherchant ce qui perdrait un fichier, écraserait, fuirait ou tournerait en boucle. Trouvé et corrigé, chacun
avec un test (`tests/trieur/unitaires/test_revue.py`) :
- une photo de facture dont l'archive échouait laissait un PDF de plus à chaque essai → retiré (D-49) ;
- une garantie ou des tags en échec après le rangement remettaient le document en file (fichier déjà parti)
  → l'état « rangé » est écrit d'abord (D-49) ;
- sans OCR, une photo de facture partait dans Photos → « À vérifier » (D-50) ;
- un fichier iCloud pas encore téléchargé sur le Bureau (« À trier ») n'était pas demandé → il l'est (D-50) ;
- un .docx piégé (texte décompressé énorme) → refusé (D-50) ;
- `annuler` après un déplacement à la main ne retrouvait pas le fichier → il suit le fichier (D-51) ;
- la réponse à tes envois pouvait être bloquée par la limite horaire de l'Assistant → elle passe, sauf la nuit
  (D-52) ;
- un fichier en erreur pouvait être repris en boucle → seulement s'il change (D-38).
Recherche dans le code : ni `sudo`, ni réseau, ni shell, ni `rm -rf` (`tests/trieur/securite/test_code.py`).

## 5. Ce qui te reste

Voir ACTIONS_HUMAINES.md : `git pull` et les bibliothèques, le test sur le Mac (5 min, à me coller), l'installation
(1 min), les deux raccourcis sur l'iPhone (2 min), et ton nom de micro-entreprise (facultatif).
