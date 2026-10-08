# Intégration avec l'assistant (et les autres projets)

Le tableau de bord ne modifie le code d'aucun autre projet, et l'assistant n'a rien à changer pour être surveillé.
Si un jour l'assistant veut **montrer** l'état de tes modules (dans son icône, dans son brief), il peut le lire,
seulement par ces moyens, dans le dossier du tableau de bord :

## Ce que le tableau de bord écrit (à lire, jamais à modifier)

| Fichier | Contenu | Mis à jour |
|---|---|---|
| `~/Library/Application Support/TableauDeBord/etat.json` | `{"maj": 1791360000.0, "bandeau": "🟡 2 choses à regarder", "niveau": "jaune", "modules": [{"id": "trieur", "nom": "Trieur", "pastille": "rouge", "phrase": "Arrêté alors qu'il devrait tourner"}, …]}` | à chaque tour (toutes les minutes) |
| `iCloud Drive/Tableau/Etat.html` | la page de l'iPhone (états, compteurs, crédits) | toutes les 15 min et à chaque changement |
| `~/Library/Application Support/TableauDeBord/rapports/semaine-AAAA-MM-JJ.html` | le rapport de la semaine | le dimanche à 20 h |

`niveau` vaut `vert`, `jaune` ou `rouge` ; `pastille` vaut `vert`, `jaune`, `rouge` ou `gris`. Si `maj` a plus de
3 minutes, le démon ne tourne plus. Les phrases sont déjà caviardées (rien de personnel). Le fichier est lisible par
toi seul (`chmod 600`), comme tout le dossier.

Exemple : une ligne dans le brief de l'assistant, « Tableau de bord : 🟡 2 choses à regarder », se lit dans
`etat.json` → `bandeau`.

## Commandes utiles (Terminal, ou lancées par l'assistant)

```
tableau etat               l'état de chaque module, en une ligne chacun
tableau module trieur      le détail d'un module
tableau ouvrir             ouvre la page locale (avec son jeton)
tableau sourdine 1h        met les alertes en sourdine (fin : tableau sourdine fin)
tableau doctor             l'état du tableau de bord lui-même
```

## Ce qui n'est pas une interface

La page locale (`http://127.0.0.1:47615/?t=…`) est pour toi : son jeton est secret et ses adresses peuvent changer.
La base `tableau.db` n'est pas une interface non plus (son format peut évoluer). Le tableau de bord n'accepte aucune
commande d'un autre programme : les seules actions (nouvelle référence, sourdine, diagnostic) viennent de toi, sur la
page (avec le jeton) ou dans le Terminal.
