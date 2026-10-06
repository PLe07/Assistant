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

## 2026-10-06 · P4-P6 — File, coffre, Claude

**D-26 · La file d'attente.**
- SQLite dans `donnees/trieur/trieur.db` : les éléments, le journal des actions, ce qui a été appris, le coffre et
  les dépenses de Claude.
- Un même fichier ajouté deux fois (pas encore traité) reste un seul élément.
- Un élément est « pris » par une mise à jour conditionnelle : le démon et une commande ne le traitent jamais à deux.
- En cas d'erreur, l'original ne bouge pas ; 3 essais, puis « erreur ». Au démarrage, ce qui était « en cours »
  (Mac éteint en route) repart dans la file.

**D-27 · Les doublons (même empreinte SHA-256 qu'un document déjà rangé).**
- Arrivé par la boîte iCloud ou « À trier » : il va dans `À vérifier/Doublons` (jamais effacé).
- Pièce jointe d'un courriel (une copie faite par le Trieur) : effacée.
- Donné à la main (Finder, commande, API) ou dans Téléchargements : il ne bouge pas, le journal dit où est l'autre.

**D-28 · Le déplacement sûr et l'annulation.**
- Copie en mode exclusif (O_EXCL : jamais sur un fichier existant, même pris entre-temps), empreinte vérifiée,
  puis suppression de l'original seulement s'il n'a pas changé.
- `annuler` défait dans l'ordre inverse : fichier remis à sa place (ou « -2 » à côté si la place est prise), PDF
  fabriqué retiré (s'il n'a pas été modifié), fiche, alias et rappels retirés.
- Un fichier revenu dans la boîte par une annulation n'est pas repris tout seul (même empreinte qu'un élément
  annulé) ; le redonner à la main reste possible.

**D-29 · Une photo de document devient un PDF cherchable.**
L'image recadrée (en JPEG, plus léger) avec le texte reconnu en calque invisible. La photo d'origine est gardée dans
`Classés/Originaux/AAAA`. Une photo sans texte de document (moins de 12 mots, ni date ni montant) va dans
`~/Pictures/Depuis l'iPhone`.

**D-30 · Ce que le Trieur apprend.**
- Une correction (`trieur corriger`) ou un déplacement à la main vers le dossier d'un autre type donne +8 points à
  ce type pour cet émetteur (plafond 20).
- Pas de points en moins pour l'ancien type : un même émetteur envoie souvent plusieurs types (factures et
  courriers d'EDF).
- `--emetteur` retient le nom corrigé dans `emetteurs_perso.json` (avec ce qui avait été lu en haut).
- Un dossier partagé par plusieurs types (« Factures/AAAA ») n'apprend rien : il est ambigu.

**D-31 · Téléchargements : seuil 0,85 (au lieu de 0,9).**
Une facture nette obtient entre 0,85 et 0,95 de confiance ; à 0,9, la moitié des factures téléchargées seraient
restées dans Téléchargements. En dessous du seuil, le fichier ne bouge pas.

**D-32 · Les autres destinations.**
Liens (`.url`, `.webloc`, adresse seule) → `Classés/Liens` (aucune page n'est téléchargée : pas de réseau) ;
format inconnu → `Classés/Fichiers/<extension>` ; une note texte → `Classés/Notes reçues`.

**D-33 · Le coffre à garanties.**
- Une fiche par bien durable ; un alias du Finder de la facture dans `Classés/Garanties` (un lien symbolique si
  l'alias échoue).
- Deux rappels dans l'app Rappels (30 et 7 jours avant la fin, à 9 h), liste « Garanties » (« Trieur-TEST » en mode
  test) ; une échéance déjà passée ne crée pas de rappel.
- Achat en ligne : un rappel de rétractation (livraison + 11 jours, 3 jours avant la fin des 14).
- Le Trieur crée et supprime ses rappels lui-même (AppleScript, valeurs passées en arguments) : `core.rappels` ne
  sait qu'en ajouter.
- `trieur garantie ajouter|modifier|supprimer` pour un bien sans facture passée par le Trieur.

**D-34 · Les pages HTML de la boîte.**
`Mon coffre.html` et `Derniers classements.html` : autonomes (pas de script ni de ressource externe), mode sombre
automatique, lisibles sur l'iPhone. Une page n'est remplacée que si elle porte la marque du Trieur ; un fichier à
toi du même nom n'est jamais touché (la page s'appelle alors « … (Trieur).html »).

**D-35 · Ce qui part chez Claude.**
- Seulement si le classement local hésite (< 0,75), seulement le texte, caviardé, 3000 caractères au plus.
- Caviardés : courriels, IBAN, cartes (Luhn), n° de sécurité sociale, tout numéro de 9 chiffres ou plus (fiscal,
  client, contrat), téléphones, rues, codes postaux et villes, la valeur après « Titulaire : », « Patient : »…, la
  ligne au-dessus d'une adresse si elle ressemble à un nom, ton nom de session macOS (lu sur le Mac, jamais écrit
  dans le dépôt) et les mots de `ia.mots_masques`.
- Jamais envoyé : un type sensible (santé, identité, impôts, paie) ou le moindre indice sérieux de l'un d'eux
  (2 points de règles, n° de sécurité sociale, « patient », « numéro fiscal »…). Ces documents vont dans
  « À vérifier » si les règles hésitent.
- Réponse en JSON vérifiée par un schéma ; une relance si elle ne colle pas ; 3 essais sur panne passagère
  (attente 2 s puis 4 s) ; budget de 1 $ par mois sur une estimation prudente du coût.
- Les dates, montants et garanties restent lus sur place pour le type donné par Claude : Claude ne fait que
  compléter ce que le texte ne donne pas.

**D-36 · Le test réel de Claude.**
Comme pour les corvées : `@pytest.mark.live`, écarté par défaut (`-m 'not live'` dans pyproject), lancé à la main
sur le Mac : `python -m pytest -m live tests/trieur/ia/test_ia.py` (moins d'un centime).

## 2026-10-06 · P7-P8 — Entrées, raccourcis, démon, commandes

**D-37 · Les entrées sont relues toutes les 2 secondes, pas surveillées par FSEvents.**
Les fichiers fantômes d'iCloud et les fichiers écrits par morceaux se gèrent mieux en relisant les dossiers (une
liste rapide de 4 dossiers). Mesuré avec 400 fichiers dans Téléchargements : 0,26 à 0,34 % de processeur.
FSEvents (watchdog) ne sert qu'à suivre tes déplacements à la main dans « Classés » (D-30).

**D-38 · Un fichier laissé n'est pas repris en boucle.**
Pas assez sûr (Téléchargements), doublon ou en erreur : il n'est réexaminé que s'il change de taille.

**D-39 · La note de l'iPhone.**
Le raccourci écrit `<nom>.meta.json` ({"note": …}) AVANT le document, pour qu'elle soit là quand le Mac le voit.
Elle est effacée quand son document est rangé ; restée seule plus de 10 minutes, elle est traitée comme un document.

**D-40 · AirDrop.**
Un fichier de Téléchargements dont la quarantaine dit « sharingd » vient d'AirDrop : c'est un envoi voulu, il est
traité comme ceux de la boîte (tout format, seuil normal). Les autres téléchargements : PDF seulement, confiance
≥ 0,85 (D-31), arrivés après l'installation.

**D-41 · Les raccourcis de l'iPhone.**
Deux raccourcis de la feuille de partage, écrits en plist par le Trieur, signés à l'installation
(`shortcuts sign --mode anyone`) et déposés dans `BoiteMac/Raccourcis/` : ce sous-dossier n'est pas surveillé (seuls
les fichiers du haut de la boîte le sont). Un raccourci déjà là n'est jamais remplacé. Sans signature possible,
la recette manuelle (6 étapes) est dans ACTIONS_HUMAINES.md.

**D-42 · L'action rapide du Finder.**
Un paquet Automator « Trier avec l'assistant » dans `~/Library/Services`, marqué comme celui du Trieur : une
nouvelle installation ne remplace que le sien, jamais un paquet étranger du même nom.

**D-43 · Les notifications.**
5 secondes d'attente pour regrouper une rafale ; au-delà de 3 documents, un seul résumé. Heures silencieuses et
limite par heure : celles de l'Assistant (`core.notifications`). En mode test, le journal seulement.

**D-44 · Chaque matin à 9 h.**
Une notification pour chaque garantie qui finit dans 30 ou 7 jours (en plus des rappels de l'app Rappels), une
fois par jour, et les pages HTML refaites.

**D-45 · `ranger-existant`.**
Sans `--confirmer`, le plan seul : rien ne bouge. Avec, chaque fichier passe par la chaîne normale (un doublon d'un
document déjà rangé reste à sa place).

**D-46 · Les logos très allongés sont complétés de blanc (2:1) avant l'OCR.**
RapidOCR agrandit le petit côté jusqu'à 736 pixels : un bandeau de 600 × 120 devenait 3 200 × 736 (2,5 s). Avec la
marge : 0,5 à 0,9 s, même texte. Sans effet gênant pour Vision.

**D-47 · Mesurer la mémoire du démon.**
Sous Linux, `ru_maxrss` d'un programme lancé par pytest garde le pic de pytest d'avant le lancement (l'OCR chargé :
668 Mo). Le test lit `VmHWM`, propre au programme mesuré : 64 Mo au repos, 70 Mo en rangeant un PDF.

**D-48 · Branchement dans l'Assistant.**
`trieur` est déclaré (éteint) dans les réglages par défaut de l'Assistant, pour que le superviseur le connaisse ;
`python assistant.py etat` affiche une ligne 🗂 ; `python assistant.py trieur …` lance la commande.

## 2026-10-06 · P9-P11 — Bout en bout, installation, revue hostile

**D-49 · Après le rangement, plus rien ne peut défaire l'état « rangé ».**
- L'état est écrit dès que le fichier est en place ; les tags et la garantie viennent après, et leur échec est
  seulement noté (le document reste rangé, il n'est pas remis en file).
- Une photo de facture dont l'archive de l'original échoue : le PDF fabriqué est retiré aussitôt (sinon chaque
  nouvel essai en ajoutait un).

**D-50 · Trois garde-fous de plus.**
- Sans OCR (ou OCR en panne), une image va dans « À vérifier », jamais dans Photos : on ne peut pas savoir si c'est
  une facture.
- Les fichiers iCloud pas encore téléchargés sont aussi demandés dans « À trier » (le Bureau est souvent dans
  iCloud).
- Un .docx dont le texte décompressé dépasse 50 Mo est refusé (archive piégée).

**D-51 · `annuler` suit un fichier déplacé à la main.**
Si le fichier rangé a été déplacé depuis (et suivi, D-30), l'annulation le prend à sa nouvelle place, après avoir
vérifié son empreinte.

**D-52 · La réponse à tes envois passe la limite horaire de l'Assistant, pas les heures silencieuses.**
Tu viens d'envoyer un document : savoir qu'il est rangé fait partie de la demande. Les notifications du matin
(garanties) suivent, elles, la règle commune.

**D-53 · Le bout en bout du Mac.**
`tests/trieur/e2e_mac` travaille dans `~/TrieurSandbox`, `iCloud Drive/BoiteMac-TEST` et la liste « Trieur-TEST »,
qui ne doivent pas exister avant (sinon il s'arrête sans rien toucher), et les supprime dans un `finally`, puis
vérifie qu'il ne reste rien. Il n'est pas dans check.sh (il faut le vrai Mac) ; ailleurs, il échoue franchement.

## 2026-10-06 · Sur ton Mac — 1er passage

**D-54 · Les variables AppleScript des Rappels commencent par « v ».**
Sur ton Mac, chaque création de rappel échouait : « Il est impossible de régler note à item 3 of argv. Accès non
autorisé (-10003) ». En AppleScript, `note` est un mot réservé (l'icône « note » des boîtes de dialogue), tout comme
`an` (un article). Toutes les variables des deux scripts s'appellent maintenant `vListe`, `vTitre`, `vCorps`… ; un
test l'impose. Les fiches de garantie, elles, étaient bien créées (D-33 : Rappels en panne, la fiche reste).

## 2026-10-06 · Sur ton Mac — l'installation

**D-55 · Le battement dès le premier tour, et un doctor qui dit pourquoi la surveillance se tait.**
Sur ton Mac, doctor lancé juste après l'installation a dit « ❌ surveillance allumée mais muette » : le superviseur
n'avait pas encore lancé le Trieur, et le battement n'était écrit qu'à la fin du premier tour.
- Le démon bat au début de chaque tour (le premier dès son lancement) et après chaque document d'une longue file :
  un gros envoi ne le fait plus passer pour muet.
- Sans battement, doctor lit ce que le superviseur de l'Assistant écrit dans `donnees/etat.db` (il ne modifie
  rien) : ⏳ « en train de démarrer » si le Trieur vient d'être lancé ou va l'être, ❌ « superviseur arrêté »
  avec la commande qui le relance, ❌ « elle plante » avec le nombre de relances et la commande du journal,
  ⚠️ en pause globale. ⏳ ne compte pas comme une erreur.

**D-56 · « redemarrer » attend le nouveau superviseur ; doctor parle français pour les fichiers laissés.**
- Sur ton Mac, `assistant.py etat` lancé juste après `service.py redemarrer` affichait « Superviseur : ARRÊTÉ »
  alors que tout tournait : l'ancien superviseur efface son battement en partant, le nouveau ne l'avait pas encore
  écrit. `redemarrer` attend maintenant ce battement (15 s au plus) avant de rendre la main.
- doctor affichait « 1 ignore » : c'est un fichier que le Trieur a laissé à sa place (un PDF de Téléchargements pas
  assez sûr pour être déplacé, D-31). Il écrit maintenant « 1 laissé à sa place (pas assez sûr pour le déplacer) »
  et donne la commande qui montre lequel et pourquoi.

