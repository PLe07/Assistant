# Ce qu'il te reste à faire

Seulement ce que Bouclier ne peut pas faire à ta place. Compte 15 minutes en tout.

## 1. Installer sur le Mac (2 minutes)

Dans le Terminal :

```
cd ~/Assistant
git pull origin claude/auto-email-sorting-module-g4cfa4
cd bouclier
./install.sh
```

À la fin, tu dois lire `✅ Bouclier est installé et surveille.` Si macOS te demande si « python » peut accéder à
iCloud Drive ou envoyer des notifications : **Autoriser**. Le Nettoyeur de démarrage te signalera une fois le nouvel
élément `com.<ta session>.bouclier` : c'est normal, garde-le.

## 2. Ajouter les 2 raccourcis sur l'iPhone (3 minutes)

1. Sur l'iPhone, ouvre l'app **Fichiers** → **iCloud Drive** → dossier **Bouclier**.
2. Touche **Arnaque ?** → **Ajouter le raccourci**.
3. Touche **Envoyer sans traces** → **Ajouter le raccourci**.
4. Vérifie : fais une capture d'écran, touche la miniature → **Partager** → **Arnaque ?** doit apparaître (sinon :
   **Modifier les actions** en bas de la feuille de partage, puis active-le).

Si les fichiers n'apparaissent pas ou refusent de s'ajouter (`install.sh` a affiché « non signé ») : crée-les à la
main en suivant **bouclier/raccourcis/recettes_manuelles.md** (3 minutes chacun).

## 3. Relier Gmail en lecture seule (5 minutes, conseillé)

Sans ça, les mails piégés ne sont pas vérifiés tout seuls et l'inventaire ne voit que tes navigateurs.

1. Va sur <https://myaccount.google.com/apppasswords> (la validation en deux étapes doit être activée sur ton compte
   Google ; sinon, active-la d'abord dans **Sécurité**).
2. Nom de l'application : `Bouclier` → **Créer**. Copie les 16 lettres affichées.
3. Dans le Terminal, en remplaçant `ADRESSE` par ton adresse Gmail complète :

```
bouclier gmail-relier ADRESSE
```

4. Colle les 16 lettres quand le Mac les demande, puis Entrée. Tu dois lire `✅ Gmail relié en lecture seule`.

Le mot de passe est rangé dans ton trousseau (élément `bouclier-gmail`), jamais dans un fichier. Bouclier n'utilise
pas l'accès du module de tri de l'assistant et ne touche jamais à ta boîte.

## 4. Remplir ta fiche urgence (5 minutes, facultatif)

```
bouclier urgence editer
bouclier urgence
```

Note tes contacts d'urgence, ton opérateur et le numéro au dos de ta carte bancaire, enregistre, puis lance la
deuxième commande. **Pas de données de santé** ici : mets-les dans l'app **Santé** → ta photo → **Fiche médicale** →
active **Afficher si verrouillé**.

Puis, **sur l'iPhone**, garde la fiche lisible sans réseau : app **Fichiers** → **iCloud Drive** → **Bouclier** →
appui long sur **Fiche urgence.pdf** → **Conserver le téléchargement** (ou **Télécharger** selon ta version d'iOS).
Le nuage ☁︎ à côté du nom doit disparaître.

## 5. L'avis de Claude (facultatif)

Rien à faire si **Claude Code** est installé et connecté sur ce Mac (`claude` dans le Terminal) : Bouclier s'en sert,
avec un plafond de 2 $ par mois. Sinon, avec une clé API Anthropic (Terminal, puis colle la clé quand il la demande) :

```
security add-generic-password -s bouclier-anthropic -a bouclier -w
```

Sans l'un ni l'autre, l'analyse locale marche seule (`bouclier doctor` l'indique).

## 6. La vérification réelle sur ton Mac (2 minutes, une fois tout le reste fait)

```
cd ~/Assistant/bouclier
.venv/bin/python -m pytest -m reel tests/e2e_mac tests/e2e/test_ia_reelle.py -s
```

Elle vérifie pour de vrai la lecture des captures d'écran, les actions rapides, la signature des raccourcis, et
que Gmail ressort **intact** (drapeaux et libellés identiques avant et après). Coût de l'IA : moins de 0,03 $.
Un test « skipped » veut dire qu'une étape ci-dessus n'est pas encore faite.

## Ton premier SMS douteux

Capture d'écran du SMS → touche la miniature → **Partager** → **Arnaque ?** → la réponse s'affiche en quelques
secondes. Sur le Mac : copie le texte, puis `bouclier verifier --presse-papiers`.
