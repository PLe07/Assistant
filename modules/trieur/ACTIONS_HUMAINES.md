# Ce qu'il te reste à faire toi-même — Trieur

Tout ce qui pouvait être fait sans ton Mac l'est. Il reste ce qui demande ton Mac, ton iPhone ou ton accord.
Les commandes se collent telles quelles dans le Terminal (sans les lignes de texte autour).

## 1. Récupérer le Trieur et ses bibliothèques (2 min)

```
cd ~/Assistant && git pull
.venv/bin/pip install -r requirements-dev.txt
```
(`requirements-dev.txt` contient aussi `requirements.txt` : PyMuPDF et Pillow pour le Trieur, reportlab pour les
tests.)

## 2. Le test de bout en bout sur ton Mac (5 min) — colle-moi la sortie

```
cd ~/Assistant && .venv/bin/python -m pytest tests/trieur/e2e_mac -q -s
```
- Il travaille dans `~/TrieurSandbox`, `iCloud Drive/BoiteMac-TEST` et la liste de Rappels « Trieur-TEST », puis les
  supprime (même en cas d'échec) et vérifie qu'il ne reste rien.
- La première fois, macOS demande si le Terminal peut **contrôler Rappels** : réponds **OK**. (Sinon : Réglages
  Système → Confidentialité et sécurité → Automatisation → Terminal → coche Rappels.)
- Il mesure Vision (PDF < 3 s, photo < 8 s), les tags du Finder, les alias, les rappels, le HEIC, l'action rapide et
  la signature d'un raccourci.

Facultatif (10 min) : les deux corpus mesurés avec Vision, la vraie OCR de ton Mac :
```
cd ~/Assistant && PYTHON=.venv/bin/python modules/trieur/check.sh
```

## 3. L'installation (1 min)

```
cd ~/Assistant && .venv/bin/python trieur.py installer
```
Elle crée `~/Documents/Classés`, `~/Desktop/À trier`, `~/Pictures/Depuis l'iPhone`, `iCloud Drive/BoiteMac`,
l'action rapide du Finder, signe les deux raccourcis dans `BoiteMac/Raccourcis`, et allume la surveillance.
Vérifie ensuite :
```
cd ~/Assistant && .venv/bin/python trieur.py doctor
```
et `.venv/bin/python assistant.py etat` doit montrer une ligne 🗂 Trieur.

## 4. Ta micro-entreprise (30 s, facultatif)

Pour que tes propres factures aillent dans « Micro-entreprise/Factures émises », remplace le nom et le SIRET :
```
cd ~/Assistant && .venv/bin/python -c 'from core import config; config.regler_module("trieur", "identite", {"nom": "NOM DE TA MICRO-ENTREPRISE", "siret": "TON SIRET"})'
```

## 5. Les raccourcis sur l'iPhone (2 min)

1. Sur l'iPhone : app **Fichiers** → iCloud Drive → **BoiteMac** → **Raccourcis**.
2. Touche **« Envoie au Mac.shortcut »** → **Ajouter le raccourci**.
3. Pareil pour **« Envoie au Mac + note.shortcut »** (il demande une note, par exemple « garantie 3 ans »).

Si l'installation a dit « non signé », crée-le à la main :
1. App Raccourcis → onglet Raccourcis → « + » en haut à droite.
2. Touche le nom en haut → Renommer → « Envoie au Mac ».
3. Touche le « i » (Détails) → active « Afficher dans la feuille de partage » → OK.
4. Ajoute l'action « Enregistrer le fichier » (recherche « Enregistrer »).
5. Dans cette action : désactive « Demander où enregistrer », choisis iCloud Drive › BoiteMac, laisse « Remplacer »
   désactivé.
6. Touche « OK ».

## 6. Le premier envoi depuis l'iPhone

Dans Photos, Fichiers ou Safari (une facture en PDF) : **Partager → Envoie au Mac**. Quelques secondes après
qu'iCloud l'a copié, le Mac affiche « 🗂 Rangé » et le fichier est dans `~/Documents/Classés`. Tes garanties :
`BoiteMac/Mon coffre.html`, lisible sur l'iPhone dans Fichiers.

## 7. Facultatif

- Le raccourci de commande `trieur` dans le Terminal (ajoute une ligne à ton `~/.zshrc`) :
  ```
  echo "alias trieur='~/Assistant/.venv/bin/python ~/Assistant/trieur.py'" >> ~/.zshrc
  ```
- Ranger dans tes dossiers existants de `~/Documents` plutôt que dans `Classés` :
  ```
  cd ~/Assistant && .venv/bin/python trieur.py arborescence
  ```
  (il montre la proposition ; `--appliquer` l'adopte ; rien n'est déplacé).
- Un vieux dossier en vrac : `trieur ranger-existant ~/Desktop/Papiers` montre le plan ; `--confirmer` le fait.
- Un appel réel à Claude (moins d'un centime) pour vérifier le format de la réponse :
  ```
  cd ~/Assistant && .venv/bin/python -m pytest -m live tests/trieur/ia/test_ia.py -q
  ```
