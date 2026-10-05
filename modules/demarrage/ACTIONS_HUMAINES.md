# Ce qu'il te reste à faire toi-même — Nettoyeur de démarrage

Tout le reste est automatique. Les commandes se tapent dans le Terminal, depuis `~/Assistant`.

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
