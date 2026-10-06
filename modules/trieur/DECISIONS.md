# Décisions — Trieur unifié

Chaque choix ambigu, avec les alternatives écartées et la raison. Le plus récent en bas.

## 2026-10-06 · P0 — Reconnaissance

**D-01 · Un module de l'Assistant, pas un projet à part.**
Le projet de l'assistant existe : c'est ce dépôt (`~/Assistant` sur ton Mac). Son module de tri Gmail est
`modules/mails`. Comme les corvées et le Nettoyeur, le Trieur devient `modules/trieur` :
- il est lancé et relancé par le superviseur de l'Assistant (`com.assistant.superviseur`, RunAtLoad + KeepAlive) ;
- il partage `reglages.json`, le journal `logs/assistant.log` (préfixe `[trieur]`), les notifications et Claude.
*Écarté :*
- le LaunchAgent nommé dans la mission : il doublerait le superviseur, et son nom contient un prénom, qui ne doit pas
  apparaître dans ce dépôt public ;
- un projet `~/Projets/trieur` séparé.

**D-02 · Emplacements.**
- **Données** (base SQLite, journal des actions, archive) : `donnees/trieur/`, jamais versionné.
  `~/Library/Application Support/Trieur/` n'est pas utilisé, pour garder un seul endroit pour les données.
- **Réglages** : `reglages.json` → `modules.trieur` (valeurs par défaut dans `modules/trieur/config.py`).
- **Règles de reconnaissance** : `modules/trieur/regles.toml`. Les règles apprises de tes corrections vont en base.
- **Tes dossiers** : ceux de la mission (`~/Documents/Classés/`, `~/Desktop/À trier/`, `~/Pictures/Depuis
  l'iPhone/`, iCloud Drive `BoiteMac/`). Tous sont réglables : le mode test les met dans un bac à sable.

**D-03 · Claude via l'abonnement (`core.cerveau`), pas de clé API.**
L'Assistant passe par Claude Code (`claude -p`) avec le jeton de ton abonnement, lu dans `.env` par le programme
lui-même. launchd n'a donc pas besoin d'hériter du shell. Le Trieur réutilise ce canal, comme les corvées (D-03 des
corvées). Le coût est estimé (jetons × tarif de la config), et le plafond de 1 $ par mois s'applique à cette
estimation.
*Écarté :* le SDK `anthropic` avec `ANTHROPIC_API_KEY` ou le trousseau. Cela ferait un second secret à gérer sous
launchd, alors que la mission demande d'utiliser la clé de l'assistant s'il en a une.

**D-04 · Construit dans un conteneur Linux.**
Cette session tourne dans un conteneur cloud : Linux x86_64, Python 3.11.
- **Présent** : `pdftotext`, `zsh`.
- **Absent** : `sips`, `shortcuts`, `brctl`, `mdls`, `automator`, `plutil`, `tesseract`.
- **Ton Mac** (vu lors des modules précédents) : MacBook Air arm64, macOS 27.0.1, Python 3.14.4 dans `.venv`.
  `pyobjc-framework-Vision` y est déjà installé (module yeux).
- **Conséquence** : tout ce qui est natif est isolé derrière des interfaces, remplacées par des imitations dans les
  tests :
  - Vision, `sips`, les tags Finder, les alias, l'AppleScript des Rappels, `brctl`, `shortcuts`, `automator` ;
  - leur vrai fonctionnement est vérifié sur ton Mac par `tests/trieur/e2e_mac` (ACTIONS_HUMAINES.md).
- `trieur doctor` vérifie iCloud Drive et chaque commande sur le Mac.

**D-05 · L'OCR dans le conteneur : RapidOCR, seulement pour les tests.**
- **Sur ton Mac** : Apple Vision (`VNRecognizeTextRequest`, fr-FR et en-US, précision maximale). En repli :
  `tesseract` s'il est installé, sinon mode dégradé (le document va dans « À vérifier »).
- **Ici** : il n'y a pas de Vision. Pour mesurer honnêtement les scans et les photos (§10.1), les tests utilisent
  un vrai moteur d'OCR installable par pip, RapidOCR (ONNX).
  - Essai sur une facture tournée de 5° : tout est lu en 1,1 s, mais il perd le « € » et les accents
    (« Regle par carte bancaire », « Facture n? »).
  - Il est donc plus sévère que Vision : un score atteint avec lui devrait l'être sur ton Mac.
- Ce n'est **pas** une dépendance du Trieur (`requirements-dev.txt` seulement).
*Écarté :* simuler les erreurs d'OCR à partir du texte connu. On aurait mesuré le classifieur sur un bruit inventé.

**D-06 · Dépendances.**
- **Au fonctionnement** :
  - `pymupdf` : texte des PDF, PDF cherchable avec le texte reconnu en calque invisible, rendu des pages ;
  - `Pillow` : images, orientation EXIF, recadrage simple.
  - `watchdog` et `jsonschema` sont déjà là (corvées).
- **Pour les tests seulement** : `reportlab` (le corpus), `pillow-heif` (des HEIC dans le conteneur ; sur le Mac, le
  Trieur convertit avec `sips`), `rapidocr_onnxruntime` (D-05).
*Écarté :*
- `pdfplumber` en repli de PyMuPDF : `pdftotext` (Poppler) sert de repli s'il est présent ;
- `pydantic` : le schéma de la réponse de Claude est vérifié avec `jsonschema`, déjà utilisé par les corvées ;
- `python-docx` : un `.docx` est un zip, son texte se lit avec la bibliothèque standard.

**D-07 · Git : le dépôt existe déjà.**
Pas de `git init`. Un commit par phase verte, sur la branche de travail.

**D-08 · Éteint par défaut, allumé par l'installation.**
Le Trieur agit sur des fichiers. Il s'allume avec `python trieur.py installer`, qui :
- crée les dossiers ;
- prépare l'action rapide du Finder et les raccourcis ;
- active le module, que le superviseur lance alors.
Les commandes (`ajouter`, `coffre`, `doctor`…) marchent aussi le module éteint.

**D-09 · La commande `trieur`.**
`python trieur.py <commande>`, `python -m modules.trieur <commande>` ou `python assistant.py trieur <commande>`.
Ton `.zshrc` n'est pas modifié : un alias `trieur` est proposé dans ACTIONS_HUMAINES.md.

**D-10 · Les dossiers de `~/Documents`.**
Depuis le conteneur, je ne vois pas ton Mac. `trieur arborescence` lit seulement les **noms** des dossiers de
`~/Documents`, jamais leur contenu. Il propose de s'aligner sur ceux qui correspondent (« Factures », « Banque »,
« Impôts »…), et l'écrit dans les réglages avec `--appliquer`. Rien n'est jamais déplacé. Par défaut, tout est
rangé sous `~/Documents/Classés/`.

**D-11 · L'API Python pour les autres modules.**
`modules.trieur.ajouter(chemin, source, note=None)`, réexportée par le paquet, met le fichier dans la file et le
traite. Le tri des mails pourra y envoyer ses pièces jointes.

**D-12 · Deux dossiers BoiteMac surveillés.**
- `iCloud Drive/BoiteMac/` : celui de la mission.
- `iCloud Drive/Shortcuts/BoiteMac/` : c'est là qu'un raccourci dépose un fichier quand l'action « Enregistrer le
  fichier » n'a pas de dossier choisi.
Le raccourci généré vise le premier. Le format des dossiers iCloud dans un `.shortcut` ne peut pas être vérifié
sans Mac, donc la surveillance des deux évite une panne silencieuse si l'import le ramène au dossier par défaut.
La recette manuelle vise le premier.

## 2026-10-06 · P2-P3 — Extraction et classement

**D-13 · La durée d'une garantie.**
- La note envoyée avec le document l'emporte (« garantie 3 ans ») : c'est toi qui sais.
- Sinon, la plus longue entre la mention du document et la garantie légale de conformité : 24 mois neuf, 12 mois
  d'occasion chez un professionnel. La garantie légale s'applique toujours : une « garantie constructeur 12 mois »
  ne la raccourcit pas.
- Elle part de la date du document (achat, sinon facture), pas de la livraison : le rappel arrive un peu plus tôt,
  jamais trop tard.
- Seuls les achats (facture d'achat, ticket) créent une garantie, pour un bien durable d'au moins 30 €.

**D-14 · Comment le juge compte (§10.1).**
- Type : juste si le type final est le bon. « À vérifier » compte faux, sauf pour un document « autre » (il n'y a
  rien à reconnaître) et pour le piège santé illisible.
- Date et montant : égaux à la vérité, absence comprise (un relevé n'a pas de montant : en trouver un est faux).
- Garantie : les dates de fin trouvées = celles attendues ; une garantie sur un document qui n'en a pas est une
  « fausse garantie » (il en faut 0).

**D-15 · Achat en ligne.**
La date du document est celle de la facture. Le rappel de rétractation tombe 11 jours après la livraison (sinon
après la commande) : il reste 3 jours sur les 14.

**D-16 · Un classeur à règles pondérées, lisibles.**
- Chaque type a des indices (expression, poids) dans `regles.toml` ; l'émetteur ajoute des points selon sa
  catégorie (une banque → relevé) ; tes corrections en ajoutent (P4).
- Confiance = (1 − e^(−avance/4)) × min(1, score/7) : deux types proches donnent une confiance basse.
- Un espace dans un indice accepte zéro espace (l'OCR en perd : « BULLETINDEPAIE ») ; les étiquettes de date sont
  comparées sans espaces (« FaitaLyon,le »).
*Écarté :* un modèle appris (bayésien, etc.) : il faudrait des centaines d'exemples réels, et on ne pourrait plus
lire ni corriger une règle.

**D-17 · La base des émetteurs.**
- 166 émetteurs français, avec leur catégorie et leurs sites.
- Un nom courant (« orange », « free », « but ») ne compte qu'en haut du document ou par son site.
- « République française » ne gagne que s'il n'y a rien d'autre.
- Tu peux en ajouter dans `donnees/trieur/emetteurs_perso.json` (même format).
- Sans émetteur connu : la première ligne du haut qui ressemble à un nom (pas un titre, une adresse, une date).

**D-18 · L'OCR des tests : RapidOCR sans retournement, et pages redressées.**
- Le classifieur d'orientation de RapidOCR lisait « 699,00 » à l'envers (« 00'669 »). Il est coupé : les images
  arrivent déjà droites (EXIF appliqué), et Vision ne fait pas cette erreur.
- Sur un scan de travers, les morceaux de deux lignes se mélangeaient. L'inclinaison est mesurée sur les boîtes
  (RapidOCR et Vision donnent les coins) et chaque morceau est redressé avant de former les lignes.
- Le cache de l'OCR est versionné : un réglage changé n'est jamais relu depuis un ancien cache.

**D-19 · Le logo d'un PDF texte est lu par l'OCR.**
Beaucoup de factures n'écrivent le nom de l'émetteur que dans leur logo. Les images du haut de la 1re page (le
tiers supérieur) sont lues par l'OCR (≈ 0,2 s) et placées en tête du texte.

**D-20 · Les colonnes sont gardées pour lire les prix.**
« Qté 1 », puis « 249,99 € » dans la colonne suivante, devenaient « 1 249,99 ». Deux espaces ou plus marquent
une colonne : un groupe de milliers n'a qu'un espace.

**D-21 · Une correction du générateur du corpus 1.**
Le logo dessiné avait une largeur fixe : les noms longs étaient coupés dans l'image (« Société Exemple S »), ce
qu'aucun vrai logo ne fait. Sa largeur suit maintenant le nom. La vérité terrain ne change pas.

**D-22 · Le 2e corpus, écrit après le réglage.**
- 60 documents, une autre graine ; émetteurs nouveaux, dont 4 absents de la base ; mises en page en colonnes,
  compacte, à empattements ; d'autres titres.
- Pour cela, le contenu accepte d'autres émetteurs (reconditionneur, transporteurs) ; le corpus 1 reste identique
  (`verite.json` comparé octet par octet).
- Sa 1re mesure est la mesure officielle : les règles n'ont pas été retouchées après.

**D-23 · Dossiers et noms.**
- Les devis vont dans `Devis/{annee}` : ce sont surtout des devis reçus (artisans), pas ceux de ta micro-entreprise.
- Sans date : « sans-date » en tête du nom. Les accents restent (forme NFC) ; « & » devient « et » ; espaces et
  apostrophes deviennent « - ».

**D-24 · Le corpus et l'OCR des tests sont gardés en cache.**
`tests/trieur/.cache-corpus/` et `.cache-ocr/` (non versionnés) : le check passe de ≈ 6 à ≈ 2 minutes. Le corpus
est refait dès qu'un fichier du générateur change (empreinte).

**D-25 · L'organisation du module diffère un peu du §11.**
`classement/` (texte, dates, montants, émetteurs, règles, champs, nommage), `extraction/`, `garanties/` ;
`regles.toml` est à la racine du module, pour être facile à trouver et à modifier.
