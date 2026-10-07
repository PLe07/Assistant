# Brancher Bouclier sur l'assistant (quelques lignes, à ajouter toi-même)

Bouclier ne touche pas au code de l'assistant. Il lui offre deux portes, utilisables depuis n'importe quel Python,
sans importer Bouclier (l'assistant garde son propre environnement) :

| Porte | Quoi | Où |
|---|---|---|
| `etat.json` | Résumé tenu à jour par le démon : score d'hygiène, 3 actions, arnaques des 7 derniers jours, nombre de comptes et de fuites, état de la fiche urgence | `~/Library/Application Support/Bouclier/etat.json` |
| `bouclier verifier --json` | Vérifier un texte : une ligne JSON par message (`niveau`, `pastille`, `score`, `titre`, `raisons`, `gestes`) | `~/.local/bin/bouclier` |

Exemple de `etat.json` :

```json
{
  "mis_a_jour": "2026-10-07T08:00:00",
  "hygiene": {"score": 72, "actions": ["Change le mot de passe de …", "Active la double authentification …"]},
  "arnaques_7_jours": 2,
  "comptes": 48,
  "fuites": 1,
  "fiche_urgence": "a_jour"
}
```

`fiche_urgence` vaut `a_jour`, `a_relire` (plus de 6 mois) ou `absente`.

## 1. Une ligne dans le brief du matin

Dans `modules/brief/brief.py`, là où le brief assemble ses lignes :

```python
import json
from pathlib import Path

def ligne_bouclier() -> str | None:
    fichier = Path.home() / "Library" / "Application Support" / "Bouclier" / "etat.json"
    try:
        e = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    morceaux = [f"🛡️ Hygiène numérique {e['hygiene']['score']}/100"]
    if e["arnaques_7_jours"]:
        morceaux.append(f"{e['arnaques_7_jours']} arnaque(s) repérée(s) cette semaine")
    if e["hygiene"]["actions"]:
        morceaux.append("à faire : " + e["hygiene"]["actions"][0])
    return " · ".join(morceaux)
```

## 2. Un bouton « Est-ce une arnaque ? » dans le menu de l'assistant

Dans `menubar.py`, à côté des autres `rumps.MenuItem` :

```python
import subprocess
from pathlib import Path

def verifier_presse_papiers(_):
    subprocess.Popen([str(Path.home() / ".local" / "bin" / "bouclier"), "verifier", "--presse-papiers", "--fenetre"])

rumps.MenuItem("🛡️ Est-ce une arnaque ? (texte copié)", callback=verifier_presse_papiers)
```

La réponse s'affiche dans une petite fenêtre, comme l'action rapide du Finder.

## 3. Vérifier un texte depuis le code de l'assistant

```python
import json
import subprocess
from pathlib import Path

def est_une_arnaque(texte: str) -> dict:
    r = subprocess.run([str(Path.home() / ".local" / "bin" / "bouclier"), "verifier", "--json", "--stdin"],
                       input=texte, capture_output=True, text=True, timeout=90)
    return json.loads(r.stdout.splitlines()[0])
```

`niveau` vaut `pas_de_signe`, `prudence`, `tres_suspect` ou `arnaque`. Le texte est caviardé avant tout envoi à
Claude, et la vérification compte dans le plafond de 2 $ par mois de Bouclier.

## Ce qu'il ne faut pas faire

- Lire ou écrire la base de Bouclier (`bouclier.db`) : son format peut changer, `etat.json` non.
- Utiliser le mot de passe Gmail de Bouclier (`bouclier-gmail`) pour autre chose que la lecture seule.
