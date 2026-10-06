# Recettes manuelles (si l'ajout des raccourcis ne marche pas)

À faire sur l'iPhone, dans l'app **Raccourcis**. Compte 3 minutes par raccourci.

## « Arnaque ? »

1. Onglet **Raccourcis** → **+** (en haut à droite). Touche le nom en haut → **Renommer** → `Arnaque ?`.
2. Touche **ⓘ** (Détails) → active **Afficher dans la feuille de partage** → OK.
   Dans « Types de partage », laisse Texte, Images, URL et Fichiers.
3. Ajoute **Nombre aléatoire** : minimum `1000`, maximum `9999`.
4. Ajoute **Texte** et écris : `arnaque-` puis la variable **Date actuelle** (touche-la → Format de date :
   Personnalisé → `yyyyMMdd-HHmmss`), un tiret `-`, puis la variable **Nombre aléatoire**.
5. Ajoute **Définir le nom** : élément = **Entrée du raccourci**, nom = la variable **Texte**.
6. Ajoute **Enregistrer le fichier** : élément = **Élément renommé** ; désactive « Demander où enregistrer » ;
   sous-chemin `Bouclier/entree/` ; « Remplacer si le fichier existe » désactivé.
7. Ajoute **Répéter** : `20` fois. À l'intérieur de la répétition :
   - **Attendre** : `3` secondes ;
   - **Obtenir le fichier** (de Fichiers) : désactive « Afficher le sélecteur de documents » ; chemin
     `Bouclier/reponses/` + la variable **Texte** + `.txt` ; désactive « Erreur si introuvable » ;
   - **Si** « Fichier » **a une valeur** :
     - **Afficher le résultat** : la variable **Fichier** ;
     - **Arrêter ce raccourci** ;
   - **Fin de si**.
8. Après **Fin de la répétition**, ajoute **Afficher le résultat** avec ce texte :

   ```
   Le Mac n'a pas répondu. Les 5 réflexes de base :
   1. Ne clique sur aucun lien et ne rappelle aucun numéro donné dans le message.
   2. Ne donne jamais un code reçu par SMS, ni les numéros de ta carte, à personne : ni au téléphone, ni sur un site.
   3. En cas de doute, va toi-même sur l'appli ou le site officiels, ou appelle le numéro que tu connais déjà.
   4. Transfère le SMS douteux au 33700 (gratuit), puis supprime-le.
   5. Si tu as déjà payé ou donné ta carte : fais opposition tout de suite (ta banque, ou le 0 892 705 705, payant), signale la fraude sur Perceval, puis porte plainte en ligne sur THESEE.
   ```
9. **OK**. Essai : dans Messages, appuie longuement sur un SMS → **Plus…** → partage → **Arnaque ?**
   (ou fais une capture d'écran → Partager → **Arnaque ?**).

## « Envoyer sans traces »

1. **+** → renomme en `Envoyer sans traces` → ⓘ → **Afficher dans la feuille de partage** (types : Images).
2. Ajoute **Convertir l'image** : en **JPEG**, qualité 90 %, et **désactive « Conserver les métadonnées »**.
3. Ajoute **Partager** : la variable **Image convertie**.
4. **OK**. Essai : dans Photos, Partager → **Envoyer sans traces** → choisis l'app (Messages, Mail…).
   Tout se passe sur l'iPhone : la photo n'est jamais envoyée au Mac.
