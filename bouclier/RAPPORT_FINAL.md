# Rapport final — Bouclier

Construit et vérifié dans un conteneur Linux (D-05) ; tout ce qui demande ton Mac est fait par `./install.sh` et
`tests/e2e_mac`, qui affichent leurs propres preuves (ACTIONS_HUMAINES.md, étapes 1 et 6).

## Définition de « terminé » (§13)

| | Critère | État | Preuve |
|---|---|---|---|
| ✅ | Intégrité des autres projets identique | ici : identique au début et à la fin de chaque `check.sh` ; sur le Mac : `install.sh` compare avant/après | ci-dessous, §1 |
| ✅ | Gmail intact | boîte imitée : drapeaux identiques, 0 commande interdite ; Gmail réel : test prêt (`tests/e2e_mac`), à lancer sur ton Mac | §2 |
| ✅ | `check.sh` vert, critères des deux corpus atteints | 100 % des arnaques en 🟠/🔴, 0 vrai message en 🟠/🔴 | §3 |
| ✅ | Liste blanche, 0 lien ouvert, 0 mot de passe lu | réseau coupé et espionné dans chaque test et dans le démon lancé pour de vrai | §4 |
| ✅ | Métadonnées, fiche urgence, fuites validées | SSIM ≥ 0,99, ICC gardé, original intact ; numéros sourcés ; une notification par fuite | §5 |
| ✅ | Démon actif, relancé après un `kill`, `doctor` clair | Mac imité : relancé en 2 s, réponse iCloud en 4 s ; sur ton Mac : étape 7 de `install.sh` | §6 |
| ✅ | README en français | vérifier (iPhone, Mac, Gmail), inventaire, fuite, photo, fiche urgence, désinstaller | README.md |
| ✅ | ACTIONS_HUMAINES.md : l'indispensable, étapes exactes | 6 étapes, dont 3 facultatives | ACTIONS_HUMAINES.md |

## 1. Les autres projets n'ont pas bougé

```
$ ./check.sh   (début et fin)
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)

$ git diff --stat <parent du premier commit de Bouclier> HEAD -- . ':!bouclier'
(rien : 0 fichier modifié hors de bouclier/)
```

Sur ton Mac, `install.sh` prend l'empreinte (dépôt de l'assistant hors `bouclier/`, `~/Projets/*`, LaunchAgents des
autres projets : plist, chargé, en marche ; réglages d'Application Support de Corvées, Nettoyeur, Trieur, Ambiance,
Assistant ; `.zshrc`, `.zprofile`, crontab, liste de `BoiteMac/`, `shortcuts list`) avant d'installer, et la compare
à la fin. Les agents `com.<ta session>.*` des autres projets y sont comparés ; seul `com.<ta session>.bouclier` est
exclu.

## 2. Gmail intact

- Boîte imitée (141 messages de 60 services, personnes et lettres d'information) : drapeaux de 20 témoins identiques avant et après
  l'inventaire et la surveillance ; une arnaque arrivée reste non lue ; 0 commande `STORE`, `COPY`, `MOVE`,
  `EXPUNGE`, `SELECT` (seulement `EXAMINE`, `UID SEARCH`, `UID FETCH … BODY.PEEK`, `LOGOUT`).
- Le code : aucune commande d'écriture IMAP n'existe dans `bouclier/` (test qui lit le code).
- Gmail réel : `tests/e2e_mac/test_mac_reel.py::test_gmail_reel_lecture_seule` (20 témoins, 3 messages analysés,
  en-têtes lus, drapeaux et libellés comparés). Sans mot de passe d'application : mode dégradé (navigateurs seuls,
  pas de surveillance des mails), signalé par `bouclier doctor`.

## 3. Le détecteur d'arnaque

| Corpus | Arnaques 🔴 | Arnaques 🟠 | Arnaques 🟡/⚪ | Vrais messages 🔴/🟠 | Vrais messages 🟡 | Vrais messages ⚪ |
|---|---|---|---|---|---|---|
| Principal (145 arnaques dont 10 injections, 80 vrais) | 125 | 20 | **0** | **0** | 0 | 80 |
| Inédit, jamais vu pendant le réglage (48 + 32) | 32 | 16 | **0** | **0** | 0 | 32 |
| Revue hostile (39 pièges + 15 vrais) | — | — | **0** | **0** | 0 | 15 |

- Veto de l'IA, avis imités contradictoires : 305 messages × 4 avis = 1 220 cas, 0 violation (jamais en dessous
  de 🟠 avec un signe critique, jamais « sûr »).
- Caviardage de bout en bout : nom, téléphone, adresse, e-mail, IBAN, carte plantés → absents de la demande à l'IA,
  du journal et de l'historique.
- IA réelle : `tests/e2e/test_ia_reelle.py` sur ton Mac (6 messages dont 2 injections, coût < 0,03 $).

```
$ ./check.sh
  ✅ intégrité des autres projets (début)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
147 passed  ✅ pytest : unitaires et intégrité
69 passed   ✅ corpus d'arnaques (principal + 2e corpus inédit)
35 passed   ✅ inventaire des comptes et fuites
25 passed   ✅ métadonnées et fiche urgence
30 passed   ✅ sécurité, réseau, vie privée
16 passed   ✅ bout en bout (démon, doctor, installation)
TOTAL 5206 instructions, 96 %   ✅ couverture ≥ 90 % sur bouclier/
  ✅ intégrité des autres projets (fin)
CHECK OK
```

## 4. Réseau, liens, mots de passe

- Chaque test tourne réseau coupé et espionné : un hôte hors liste blanche fait échouer le test, même tenté. Sur les
  305 messages des deux corpus et les 54 de la revue hostile, aucun hôte de lien n'a été contacté.
- Le démon lancé pour de vrai par `install.sh` (Mac imité) n'a tenté que : openphish.com, urlhaus.abuse.ch,
  haveibeenpwned.com et des sites officiels (gouv.fr, service-public.fr, chu-bordeaux.fr, centres-antipoison.net,
  ars.sante.fr). Tous permis.
- Mots de passe : la colonne `password_value` n'est jamais nommée (chaque requête SQL est espionnée) ; Firefox : tout
  champ « password » écarté à la lecture ; trousseau : seuls les éléments `bouclier-*` sont lus.

## 5. Les autres fonctions

- **Inventaire** : précision 100 %, rappel 100 % sur 60 services imités ; 2 814 services connus (JustDeleteMe,
  2factorauth, licence MIT) dont 163 français avec lien de suppression. **Nombre de tes comptes** : compté sur ton Mac
  au premier passage du démon (`bouclier comptes`, ou `comptes` dans `etat.json`) ; ce conteneur n'a pas accès à ta
  boîte ni à tes navigateurs.
- **Fuites** : liste publique Have I Been Pwned, croisement par domaine et date, une notification par fuite, copie
  de la veille gardée si la liste est injoignable. **Nombre de fuites qui te concernent** : calculé sur ton Mac après
  l'inventaire (`bouclier fuites`) ; le pare-feu de ce conteneur bloque haveibeenpwned.com (D-06).
- **Métadonnées** : JPEG, PNG, WebP sans perte ; photo tournée remise à l'endroit (SSIM ≥ 0,99) ; HEIC, TIFF, PDF,
  Office ; vidéo avec ffmpeg ; profil couleur gardé ; original intact (empreinte).
- **Fiche urgence** : 11 numéros, chacun relevé sur un site officiel (registre `sources.json`, revérifié tous les 6
  mois sur ton Mac) ; PDF A4, carte A6 d'une page, écran verrouillé ; aucune donnée de santé.

## 6. Le démon et l'installation

```
$ ./install.sh   (Mac imité : faux launchctl qui lance vraiment le démon)
▶ 7/8 Vérification : arrêt brutal puis relance, demande déposée dans iCloud
  ✅ launchctl print : com.<session>.bouclier tourne (pid 1948)
  ✅ kill 1948 : relancé par launchd en 2 s (pid 1962)
  ✅ texte déposé dans iCloud : réponse du démon en 4 s (⚪ Pas de signe d'arnaque détecté)
  ✅ fichiers de test retirés d'iCloud
▶ 8/8 Bilan
✅ démon : com.<session>.bouclier tourne (pid 1962), dernier tour il y a 0 s
INTÉGRITÉ OK : identique à avant_installation.json
✅ Bouclier est installé et surveille.
```

- `install.sh` et `uninstall.sh` lancés deux fois chacun (puis `--tout`) : aucun effet de bord ; `sudo` refusé.
- Un inventaire interminable ne retarde pas la réponse au raccourci (fil à part, D-29).
- Au repos : ≤ 10 écritures disque pour 100 tours de 3 s (D-33).
- Sur le vrai launchd, la relance après `kill` prend jusqu'à 30 s (ThrottleInterval) : `install.sh` attend 90 s.

## 7. Ce qui reste à faire par toi

ACTIONS_HUMAINES.md : installer (1 commande), ajouter les 2 raccourcis, relier Gmail (mot de passe d'application),
et, si tu veux, remplir la fiche urgence, donner une clé IA, lancer la vérification réelle.

## 8. Limites connues

- La structure interne des raccourcis iPhone ne peut pas être vérifiée sans iPhone : la recette manuelle est le
  plan B, et `shortcuts sign` les valide sur ton Mac.
- Le détecteur ne peut rien contre une arnaque sans lien, sans numéro et sans demande (un simple « Salut, ça va ? »
  qui prépare le terrain) : il le dit (⚪ n'est pas une garantie).
- Les numéros officiels ont été relevés le 06/10/2026 par recherche limitée aux domaines officiels ; la première
  revérification en lisant les pages elles-mêmes se fait sur ton Mac.
