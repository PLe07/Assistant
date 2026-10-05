# Ce qu'il te reste à faire toi-même — Nettoyeur de démarrage

Tout le reste est automatique. Les commandes se tapent dans le Terminal, depuis `~/Assistant`.

## 0. Facultatif mais pratique : le raccourci « demarrage »

Le rapport et les messages écrivent `demarrage …`. Pour que ça marche tel quel, ajoute une fois ce raccourci
(le Nettoyeur ne touche jamais à tes fichiers zsh) :

```zsh
echo 'alias demarrage="$HOME/Assistant/.venv/bin/python $HOME/Assistant/demarrage.py"' >> ~/.zshrc
source ~/.zshrc
```

Sans lui : `cd ~/Assistant`, puis `.venv/bin/python demarrage.py …` (même suite).

## 1. Facultatif : capturer les vraies sorties de ton Mac pour les tests

Lecture seule. Les sorties sont anonymisées (ton nom de compte, ton nom, le nom du Mac, les e-mails disparaissent)
et restent sur ton Mac : le dossier n'est jamais envoyé sur GitHub.

```zsh
cd ~/Assistant
git pull
.venv/bin/python -m modules.demarrage.capturer
.venv/bin/python -m pytest tests/demarrage/unitaires/test_fixtures_reelles.py -q
```

Résultat attendu : `✅ … sortie(s) anonymisée(s)`, puis `passed`.

## 3. Facultatif : l'autorisation « Automatisation » pour System Events

Sans les droits d'administrateur, macOS ne laisse pas lire la liste complète des éléments d'ouverture
(`sfltool dumpbtm`). Le Nettoyeur lit alors la liste « Ouvrir à la connexion » par System Events. La première fois,
macOS te demande : « Terminal (ou Python) souhaite contrôler System Events ». Réponds **OK**.

Si tu as refusé : Réglages Système → Confidentialité et sécurité → Automatisation → Terminal (ou Python) → coche
« System Events ».

Ce que ça débloque : la liste des apps qui s'ouvrent à ta connexion, et leur retrait par `demarrage desactiver`.
Sans elle : le Nettoyeur les devine à partir des apps lancées juste après ton ouverture de session, et il te donne
le chemin dans les Réglages pour les retirer à la main.
