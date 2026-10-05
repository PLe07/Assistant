# Fixtures du Nettoyeur de démarrage

- `formats/` : sorties de commandes macOS **reconstruites** d'après leur format documenté (voir DECISIONS D-05),
  anonymisées par construction (compte `utilisateur`, UID 501), avec des pièges volontaires : colonnes décalées,
  espaces et accents dans les chemins, lignes cassées, plists binaires, cassées ou vides.
- `reelles/` : sorties **réelles** capturées sur ton Mac par
  `.venv/bin/python -m modules.demarrage.capturer`. Elles sont anonymisées, puis vérifiées : le capteur refuse
  d'écrire si ton nom de compte reste visible. Ce dossier n'est jamais envoyé sur GitHub (`.gitignore`), car il
  listerait tes logiciels. `tests/demarrage/unitaires/test_fixtures_reelles.py` analyse tout ce qu'il y trouve.
