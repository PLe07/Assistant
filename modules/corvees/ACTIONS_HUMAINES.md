# Ce qu'il te reste à faire (sur ton Mac)

Seulement ce qu'aucun programme ne peut faire à ta place. Le détecteur marche déjà sans les autorisations :
il voit simplement moins de choses, et `corvees doctor` te dit lesquelles.

## 1. Mettre à jour et allumer (obligatoire, 1 minute)

Dans le Terminal :

```zsh
cd ~/Assistant
git pull
.venv/bin/pip install -r requirements.txt        # ajoute watchdog et jsonschema
.venv/bin/python service.py installer            # relance l'Assistant avec le nouveau code
.venv/bin/python assistant.py activer corvees    # le détecteur est éteint au départ : c'est toi qui l'allumes
```

Ce que ça débloque : le démon démarre dans les 2 secondes, sous le superviseur de l'Assistant (qui le relance s'il
tombe). Vérifie avec `.venv/bin/python assistant.py corvees doctor` : tu dois lire « ✅ Démon vivant ».

## 2. Les autorisations macOS

| Autorisation | Où | Quoi autoriser | Ce que ça débloque | Sans elle |
|---|---|---|---|---|
| **Accessibilité** | Réglages Système → Confidentialité et sécurité → Accessibilité | « Python » (déjà fait si la traduction 🇬🇧 marche chez toi : c'est le même) | les titres de fenêtres (capteur C2), caviardés avant d'être écrits | capteur « fenetres » désactivé, le reste marche |
| **Accès complet au disque** (facultatif) | Réglages Système → Confidentialité et sécurité → Accès complet au disque → « + » | « Python » (s'il n'est pas dans la liste : « + », puis ⌘⇧G et colle `~/Assistant/.venv/bin/python`) | l'historique des navigateurs (C5) : Safari, et Chrome sur les macOS récents | les sites visités ne sont pas lus ; le reste marche |

Après un changement d'autorisation : `.venv/bin/python service.py redemarrer`.

## 3. Vérifier sur ton Mac (5 minutes de ton temps, 10 minutes de mesure)

Ces vérifications ont été faites dans le conteneur de construction (Linux). Elles doivent être refaites sur ton
Mac, parce que seul le Mac a les vraies applis et l'Apple Silicon.

Bout en bout (de vrais fichiers dans ~/CorveesSandbox, un historique zsh de test, puis TextEdit et Calculette
ouvertes à tour de rôle et refermées ; le bac à sable est effacé à la fin) :

```zsh
cd ~/Assistant
CORVEES_E2E_MAC=1 .venv/bin/python -m pytest tests/corvees/e2e -q -s
```

CPU, mémoire et taille de la base pendant 10 minutes (le démon doit tourner, utilise ton Mac normalement) :

```zsh
.venv/bin/python tests/corvees/perf/mesure_demon.py 600
```

Relance après un plantage (le superviseur relance le module dans la minute) :

```zsh
pkill -9 -f 'modules\.corvees$'; sleep 70; .venv/bin/python assistant.py corvees status
```

Résultat attendu : `2 passed`, puis `✅ dans les budgets`, puis « démon : vivant ».

## 4. Facultatif : le confort

À ajouter toi-même à ton `~/.zshrc` (le détecteur n'y touche jamais) :

```zsh
# Taper « corvees rapport » au lieu de « .venv/bin/python assistant.py corvees rapport »
alias corvees="$HOME/Assistant/.venv/bin/python $HOME/Assistant/corvees.py"
# Les commandes arrivent tout de suite dans l'historique, avec leur heure : le détecteur les voit mieux
setopt INC_APPEND_HISTORY EXTENDED_HISTORY
# Seulement si tu installes un alias proposé (corvees accept ID --installer) :
source "$HOME/Assistant/donnees/corvees/alias.zsh"
```

Puis ouvre un nouveau Terminal.

## Ce qui n'est PAS à faire

- Pas de clé API : Claude passe par ton abonnement, avec le jeton déjà rangé dans `.env`.
- Pas de LaunchAgent à part : le détecteur est un module de l'Assistant, lancé par son superviseur.
