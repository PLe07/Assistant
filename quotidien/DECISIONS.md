# Décisions — Quotidien

Chaque choix ambigu, avec les alternatives écartées et la raison. Le plus récent en bas.

## 2026-10-07 · P0 — Reconnaissance et fondations

**D-01 · Quotidien vit dans le dossier `quotidien/` du dépôt de l'assistant, sans toucher un octet du reste.**
Cette session tourne dans un conteneur cloud dont le seul endroit qui survit est le dépôt GitHub de l'assistant
(branche de travail). Il n'y a pas de `~/Projets/quotidien` ici, et un `git init` séparé serait perdu (même constat
que Bouclier, D-01).
- Quotidien est un **projet autonome** : son `pyproject.toml`, son `.venv`, son `check.sh`, ses tests, son
  `.gitignore`, ses données (`~/Library/Application Support/Quotidien/`) et son LaunchAgent.
- **Aucun fichier existant n'est modifié** (ni l'assistant, ni `bouclier/`, ni le `.gitignore` racine) :
  l'empreinte d'intégrité le prouve à chaque `check.sh`.
- Sur ton Mac : `install.sh` fonctionne depuis `~/Assistant/quotidien` (après `git pull`) comme depuis une copie
  dans `~/Projets/quotidien`.
*Écarté :* un `git init` dans `quotidien/` (un dépôt dans le dépôt, que GitHub ne garderait pas) ; un module sous le
superviseur de l'assistant (il faudrait modifier son code et `reglages.json`, ce que la mission interdit).

**D-02 · Git : un commit par phase verte, sur la branche de travail du dépôt.**
`git rev-parse HEAD` du dépôt avance donc avec les commits de Quotidien. L'empreinte compare à la place l'**arbre
suivi hors `quotidien/`** (`git ls-tree -r HEAD`, filtré) et `git status` hors `quotidien/`, avec
`--no-optional-locks` (aucune écriture dans l'index d'un autre projet).

**D-03 · L'empreinte « avant » compare le code et les réglages, pas les données vivantes.**
Sur ton Mac, l'assistant, le Trieur et Bouclier tournent : ils écrivent sans cesse dans `donnees/`, `logs/`, leurs
bases `.db` et leurs caches. Sont comparés : chaque fichier de code et de réglages des projets (dont `bouclier/`),
l'arbre git, les plists des LaunchAgents et leur état launchd (chargé, en marche, dernier code de sortie — le numéro
de processus change à chaque démarrage du Mac et ne dit rien), les réglages dans
`~/Library/Application Support/<Projet>/`, `~/.zshrc`, `~/.zprofile`, `crontab -l`, la liste des dossiers iCloud
`BoiteMac/` et `Bouclier/`, `shortcuts list` (nos deux raccourcis exceptés), `docker ps -a` (nom, image, état — pas
la durée « Up 3 hours », qui change toute seule) et le nom et le nombre d'éléments de chaque liste de Rappels.
- Rappels : une liste de nom « Courses (menu) », « Anniversaires » (ou suffixée « (Quotidien) ») qui **n'existait
  pas** dans la référence est la nôtre et n'est pas comparée ; une liste de ce nom qui existait **avant** est celle
  de quelqu'un d'autre et reste comparée (élément par élément : son nombre).
- Ici : `integrite/etat_avant.json` (chemins du dépôt seulement, aucun nom personnel) est versionné.
- Sur ton Mac : `install.sh` prend `integrite/mac/etat_avant.json` **avant toute installation** (jamais sur GitHub :
  noms de LaunchAgents et de listes) et le compare à la fin. `verifier.sh` choisit le bon fichier.

**D-04 · Le dépôt est public : aucun prénom écrit dedans.**
Comme Bouclier (D-04), le label est construit à l'installation à partir de ton **nom de session macOS** :
`com.<session>.quotidien`, ce qui donne exactement `com.thibaut.quotidien` si ta session porte ton prénom. Réglable
dans `reglages.toml` (`[installation] prefixe_label`). `install.sh` vérifie que le label et la commande `quotidien`
sont libres avant d'installer.

**D-05 · Construit dans un conteneur Linux (constat du 2026-10-07).**
- Ici : Linux x86_64, Python 3.11.15, `docker` présent sans démon. Absents : `osascript`, `launchctl`, `shortcuts`,
  `plutil`, `security`, `brctl`, `sw_vers`, l'app Rappels, Contacts, iCloud.
- Ton Mac (relevé par les projets précédents) : MacBook Air arm64, macOS 27, Python 3.14 ; `install.sh` cherche
  `python3.14` … `python3.11` et refuse le `python3` 3.9 d'Apple (`tomllib` est dans Python 3.11+).
- Tout ce qui est natif (notifications, Rappels, Contacts, trousseau, presse-papiers, Messages, launchd, signature des
  raccourcis) passe par une seule interface (`quotidien/systeme.py`) : les tests vérifient les commandes construites ;
  `tests/e2e_mac` (marqués `reel`) les vérifient pour de vrai sur ton Mac, lancés par `install.sh`.

**D-06 · Le pare-feu du conteneur refuse Open-Meteo.**
`api.open-meteo.com` répond « 403 » au tunnel du conteneur de construction (politique réseau de l'environnement, pas
de Quotidien). Conséquences :
- le format de la réponse est relevé dans la documentation officielle d'Open-Meteo (paramètres, unités, et surtout :
  pluie et rafales d'une heure *h* = cumul et maximum **de l'heure précédente**) ; les fixtures du dépôt sont
  construites à ce format, y compris les jours de changement d'heure ;
- sur ton Mac, `install.sh` fait une **vraie** requête, en garde une capture anonymisée
  (`tests/meteo/fixtures/reelles/`, coordonnées arrondies) et rejoue toute la chaîne météo dessus
  (`tests/e2e_mac`) ; `quotidien doctor` affiche l'âge de la dernière prévision reçue.
- Quotidien demande `timeformat=unixtime` : chaque heure est un instant exact, converti en heure de Paris par
  `zoneinfo` ; aucune ambiguïté possible les nuits de changement d'heure.

**D-07 · Deux fichiers à toi, dans `~/Library/Application Support/Quotidien/`.**
`profil.toml` (le petit fichier : goûts, allergies, budget, jours chargés, trajets) et `reglages.toml` (ville,
heures, IA, listes de Rappels). Modèles commentés dans le projet : `profil.example.toml`, `reglages.example.toml`.
Un fichier illisible ou une valeur fausse est remplacé par la valeur par défaut, avec un message qui dit laquelle et
pourquoi (`quotidien doctor`). *Écarté :* les mettre dans iCloud (proches.toml contient des notes sur des personnes :
il reste dans le dossier privé du Mac).

**D-08 · Une allergie mal écrite n'est jamais ignorée.**
Une allergie hors des 14 allergènes réglementaires (« noix de pécan ») est signalée **et** ajoutée aux aliments
interdits (contrainte dure, comme une aversion) : une faute de frappe ne doit pas laisser passer un aliment dangereux.

## 2026-10-07 · P1 — Météo « habille-toi »

**D-09 · La pluie d'un trajet est comptée au prorata, et sur la bonne heure.**
Open-Meteo donne pour l'heure *h* la pluie tombée entre *h* − 1 h et *h*. L'aller de 8 h 00 à 8 h 30 est donc
couvert par la valeur de 9 h, pour moitié : 3 mm/h donnent 1,5 mm pendant le trajet (> 1 mm → équipement de pluie).
Même logique pour les rafales (maximum de l'heure précédente). Le texte annonce l'**épisode** de pluie entier qui
touche le trajet (« averses entre 7h et 10h »), pas seulement la demi-heure du trajet.

**D-10 · À vélo, le ressenti est diminué de 3 °C, et la tenue vise le trajet le plus froid.**
L'air de la vitesse (20 km/h environ) refroidit. Les couches sont choisies pour le moment le plus froid de tes
trajets ; si l'après-midi est bien plus chaud (8 °C ou plus), la bascule ajoute « une couche que tu peux enlever ».
Les seuils sont dans `regles_tenue.toml` (modifiable, recopiable dans Application Support pour le garder à toi).

**D-11 · Les lunettes de soleil regardent toute la journée dehors, de jour, au sec.**
Ton trajet de 8 h a rarement un UV de 3 ; ta pause de midi, si. La fenêtre va de ton départ à ton retour ; une heure ne
compte que si elle est de jour (entre lever et coucher), sans pluie et avec un UV ≥ 3. Jamais de lunettes un jour
dominé par la neige ou l'orage (« Il neige… lunettes de soleil » se contredirait) : trouvé par le test aléatoire.

**D-12 · Les jours sans cours : une journée de 9 h à 19 h, sans vélo.**
Le conseil est général (« lunettes de soleil si tu sors ») ; le parapluie y est permis ; le tram est formulé « si tu
sors, privilégie le tram ». Par grand vent (rafales > 50 km/h), le parapluie devient « imper à capuche ».

**D-13 · Les modèles de texte tournent avec la date.**
Chaque situation a 5 à 6 modèles ; le modèle du jour avance d'un cran chaque jour : deux jours qui se suivent n'ont
jamais le même modèle, donc jamais le même message 3 jours de suite. Le même jour, le texte reste stable.
*Écarté :* le hasard (deux jours identiques possibles) et une mémoire en base (inutile ici).

**D-14 · Dans le texte, la sécurité passe avant tout.**
« Prends plutôt le tram » et « casque et éclairage » sont toujours affichés, quitte à laisser tomber « Vélo OK » ou le
retour au sec. Défaut trouvé par le test de bout en bout sur la fixture de janvier (le rappel de nuit disparaissait
quand la ligne était pleine) ; la table exhaustive vérifie désormais « éclairage » dans le texte de chaque trajet de
nuit.

**D-15 · L'alerte de 21 h distingue le gel sec du verglas.**
Gel sec annoncé (−3 °C, air sec) : « gel au petit matin », sans parler de verglas ni de tram. Gel humide, pluie
verglaçante ou pluie la veille suivie de gel : « risque de verglas » et le tram, comme le moteur de règles du
lendemain. Défaut trouvé par les tests (l'alerte annonçait un verglas que les règles ne voyaient pas).

## 2026-10-07 · P2 — Base de recettes

**D-16 · Les recettes sont écrites dans un format source compact ; un générateur calcule tout ce qui ne doit jamais
être faux à la main.** `outils/sources/recettes/*.txt` (lisible, une recette = un en-tête, ses ingrédients, ses
étapes) → `outils/construire_recettes.py` → `quotidien/repas/recettes/*.json`. Le générateur refuse un ingrédient
inconnu, une unité fausse, un temps absurde, un « batch » qui ne se garde pas ; il calcule les **allergènes** (depuis
la table des ingrédients), les **régimes**, les **saisons**, le **coût**, les étiquettes (« rapide » = 20 min ou
moins au total, « au four », « végétarien »…), la **mention de sécurité** et la **conservation des restes**. Un test
vérifie que les JSON versionnés correspondent exactement aux sources.

**D-17 · Unités : g, ml ou pièces.** Les pièces (œuf, oignon, tranche de jambon, tortilla) ont un poids pour les
conversions ; les cuillères deviennent des ml ou des g (1 c. à soupe d'huile = 15 ml, 1 c. à café de cumin ≈ 2 g).

**D-18 · Ce qui compte comme « de saison ».** Calendrier France (ADEME, Interfel). Un produit importé (avocat, citron
vert) n'est jamais de saison. Les alliacées, les herbes, le citron et le gingembre ne comptent pas (on en met trop peu
pour que ce soit un choix de saison). Carotte, pomme de terre et champignon de Paris sont de saison toute l'année
(conservation et culture en France). Surgelés et conserves sont neutres. Une recette est « de saison » un mois donné si
tous ses fruits et légumes qui comptent le sont ; pour le critère « 40 recettes par mois », il faut au moins un fruit ou
légume qui compte (une recette sans légume ne compte pas).

**D-19 · Végétarien : le parmesan et le pesto n'en sont pas.** Le cahier des charges du Parmigiano Reggiano impose une
présure animale ; le pesto en contient. Les autres fromages sont considérés végétariens (convention courante en
France). Recettes végétariennes : 117 sur 228.

**D-20 · Restes : 3 jours au plus, moins pour ce qui est fragile.** Poisson, viande hachée : 2 jours ; crevettes,
moules : 1 jour ; riz mélangé au plat (riz cantonais, risotto, farce) : 1 jour. Riz servi à part : le plat se garde
3 jours et le riz se refait (mention « riz cuit : 24 h au frigo au plus »). Toujours : « au frigo moins de 2 h après
la cuisson », « réchauffe à cœur ».

**D-21 · Allergènes des produits transformés « selon les marques ».** Cube de bouillon (céleri, gluten), chorizo
(lait), pain de mie (lait, soja), pâte de curry thaï (crevette), pesto (lait, fruits à coque), curry en poudre
(moutarde) : présents dans la table par prudence. Mieux vaut écarter une recette de trop.

**D-22 · Pas de mixeur obligatoire pour les soupes.** Elles se font aussi au presse-purée (« soupe rustique ») ; seuls
le gaspacho, le houmous et les falafels exigent un mixeur (équipement vérifié par le planificateur).

**D-23 · Les crevettes sont achetées cuites et surgelées.** Moins chères, sans risque de cuisson insuffisante :
décongélation au réfrigérateur, consommation dans la journée (mention ajoutée).

**D-24 · Relecture de chef : 20 recettes tirées au hasard (graine 20261007), 8 corrections.**
Frittata (dés de pommes de terre pas cuits en 6 min → 10 min à couvert), phở (bœuf poché 1 min dans le bouillon
plutôt que cru sous le bouillon versé), cuisses de poulet au four (35 à 40 min, repère « cuit à cœur »), chowder
(temps du revenu, poisson décongelé au frigo), gratin de panais (repère de fin de cuisson), soupe d'hiver (le poireau
se lave, il ne s'épluche pas), nouilles égouttées et rincées, et « d'haricots » → « de haricots » (h aspiré).
Les tests de validation avaient déjà trouvé : 7 recettes où aucune étape ne disait quand la viande ou le poisson est
cuit, une mention de sécurité manquante pour les crevettes, et un bogue d'affichage (« 500 g » affiché « 5 g »).
