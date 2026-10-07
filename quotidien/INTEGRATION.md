# Intégration avec l'assistant (et les autres projets)

Quotidien ne modifie le code d'aucun autre projet. L'assistant (ou n'importe quel outil) peut s'en servir seulement
par des **fichiers**, dans les dossiers de Quotidien :

## Ce que Quotidien écrit (à lire, jamais à modifier)

| Fichier | Contenu | Mis à jour |
|---|---|---|
| `~/Library/Application Support/Quotidien/brief.json` | `{"date": "2026-10-08", "lignes": ["☀️ …", "🍽️ …", "🎂 …"]}` | chaque matin, à l'heure du brief |
| `iCloud Drive/Quotidien/Ma journée.html` | la page du jour | chaque matin |
| `iCloud Drive/Quotidien/Menu de la semaine.html` | le menu, les recettes, la liste de courses | le dimanche, et à chaque `quotidien menu` |

Exemple : pour reprendre le brief de Quotidien dans un autre brief, lire `brief.json` et afficher `lignes` (une
ligne absente veut dire « rien à dire »). Si `date` n'est pas aujourd'hui, le brief n'est pas encore sorti.

## Ce que l'assistant peut déposer (comme les raccourcis de l'iPhone)

| Déposer dans `iCloud Drive/Quotidien/entree/` | Effet | Réponse |
|---|---|---|
| `envie-<identifiant>.txt` (« mexicain et léger ») | une envie pour le prochain menu | `reponses/envie-<identifiant>.txt` |
| `frigo-<identifiant>.txt` (« 2 courgettes, feta ») ou `.jpg` | 3 recettes réalisables tout de suite | `reponses/frigo-<identifiant>.txt` |

`<identifiant>` : 4 à 60 caractères parmi lettres, chiffres, `-` et `_` (par exemple la date et un nombre). La
réponse arrive en quelques secondes si le Mac est allumé ; la demande est effacée une fois traitée.

## Commandes utiles

```
quotidien brief           le brief du jour, tout de suite
quotidien menu            le menu de la semaine
quotidien frigo "…"       le vide-frigo
quotidien doctor          l'état de chaque brique
```

Rien d'autre n'est partagé : la base SQLite de Quotidien n'est pas une interface (son format peut changer).
