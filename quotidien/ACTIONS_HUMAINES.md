# Ce qu'il te reste à faire

Seulement ce que Quotidien ne peut pas faire à ta place. Compte 10 minutes en tout.

## 1. Installer sur le Mac (3 minutes)

Dans le Terminal :

```
cd ~/Assistant
git pull origin claude/auto-email-sorting-module-g4cfa4
cd quotidien
./install.sh
```

À la fin, tu dois lire `✅ Quotidien est installé.` Pendant l'installation (et au premier tour du démon), macOS
ouvre quelques fenêtres. Réponds **Autoriser** / **OK** à chacune :

- « Terminal » puis « python3 » **souhaitent accéder à tes contacts** : lecture seule, pour les anniversaires ;
- « Terminal » puis « python3 » **souhaitent contrôler Rappels** : pour tes listes « Courses (menu) » et
  « Anniversaires », et seulement elles ;
- un accès à **iCloud Drive** ou aux **notifications**.

Refusé par erreur ? Réglages Système → Confidentialité et sécurité → **Contacts** (ou **Automatisation**) → coche
Terminal et python3. `quotidien doctor` dit ce qui manque. Le Nettoyeur de démarrage te signalera une fois le nouvel
élément `com.<ta session>.quotidien` : c'est normal, garde-le.

## 2. Ajouter les 2 raccourcis sur l'iPhone (2 minutes)

1. App **Fichiers** → **iCloud Drive** → **Quotidien**.
2. Touche **Mon frigo** → **Ajouter le raccourci**.
3. Touche **Envie de…** → **Ajouter le raccourci**.

Au premier lancement, autorise l'accès à iCloud Drive et à l'appareil photo.

Si les fichiers n'apparaissent pas ou refusent de s'ajouter (`install.sh` a affiché « non signé »), crée « Mon
frigo » à la main dans l'app **Raccourcis** → **+**, avec ces actions dans l'ordre :

1. **Choisir dans le menu**, 3 options : `📷 Prendre une photo`, `🖼️ Choisir une photo`, `✍️ Écrire ou dicter` ;
   sous la 1re : **Prendre une photo** ; sous la 2e : **Sélectionner des photos** ; sous la 3e : **Demander une
   entrée** (Texte, « Qu'as-tu dans ton frigo ? ») ;
2. **Nombre aléatoire** entre 1000 et 9999 ;
3. **Texte** : `frigo-`, puis **Date actuelle** (format personnalisé `yyyyMMdd-HHmmss`), `-`, puis **Nombre
   aléatoire** ;
4. **Définir le nom** de **Résultat du menu** sur **Texte** ;
5. **Enregistrer le fichier** : décoche « Demander où enregistrer », chemin `Quotidien/entree/` ;
6. **Répéter** 20 fois : **Attendre** 3 s ; **Obtenir le fichier** `Quotidien/reponses/` + **Texte** + `.txt`
   (décoche « Erreur si introuvable ») ; **Si** **Fichier** a une valeur : **Afficher le résultat** **Fichier**, puis
   **Arrêter ce raccourci** ;
7. après la boucle : **Afficher le résultat** « Mac injoignable, réessaie plus tard. »

« Envie de… » : pareil, avec seulement **Demander une entrée** (« Envie de quoi pour le prochain menu ? ») au début,
et `envie-` au lieu de `frigo-`.

## 3. Facultatif

- Tes goûts, ton budget, tes trajets : `~/Library/Application Support/Quotidien/profil.toml` (TextEdit suffit).
- Une fiche pour tes proches (relation, ton, souvenirs) ou quelqu'un absent de tes Contacts :
  `cp proches.example.toml ~/Library/Application\ Support/Quotidien/proches.toml`, puis remplis-le.
- L'IA : rien à faire si **Claude Code** est connecté sur ce Mac (`claude` dans le Terminal). Sinon, avec une clé
  API Anthropic (colle-la quand il la demande) :

```
security add-generic-password -s quotidien-anthropic -a quotidien -w
```

Sans l'un ni l'autre, tout marche en local (sauf la lecture d'une photo du frigo : envoie la liste en texte).

## 4. La vérification réelle (2 minutes, une fois le reste fait)

```
cd ~/Assistant/quotidien
.venv/bin/python -m pytest -m reel tests/e2e_mac tests/frigo/test_vision.py -s
```

Elle vérifie pour de vrai : une liste de Rappels `Quotidien-TEST` créée, relue puis supprimée (tes autres listes
identiques), un aller-retour iCloud dans `Quotidien-TEST/` supprimé ensuite, le nombre d'anniversaires lus dans tes
Contacts (aucun nom affiché), la signature des raccourcis, un message d'anniversaire et une photo lus par l'IA
(moins de 0,04 $ en tout). Un test « skipped » veut dire qu'un accès ci-dessus n'est pas encore accordé.

## Ton premier vide-frigo depuis l'iPhone

Lance **Mon frigo** → **✍️ Écrire ou dicter** → « 2 courgettes, feta, un reste de riz » → en quelques secondes,
3 recettes faisables tout de suite.
