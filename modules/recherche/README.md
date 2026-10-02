# La recherche sourcée : la fiche

Tu poses une question, Claude cherche sur le web et te répond **en 5 lignes**, avec **ses sources** (les sites
officiels d'abord : service-public, impots.gouv, BOFiP, Légifrance, AMF, Banque de France…).

## Trois façons de demander

1. Icône en haut à droite → **« 🌐 Rechercher sur le web… »** → ta question → « Rechercher ».
2. Icône → **« ✍️ Noter ou demander… »** : « **cherche sur internet** le plafond du PEA ».
3. À voix haute (micro allumé) : « **Assistant, cherche sur internet** le plafond du PEA ».
   La réponse t'attend dans « 💡 Aides » (une notification te prévient).

La réponse s'ouvre toute seule (20 à 90 s). **« Ouvrir les sources »** : la page de tes 20 dernières recherches,
avec les liens cliquables.

## Ce qui est vérifié

- Claude n'a que **deux outils** pour cet appel : chercher sur le web et lire une page. Rien d'autre.
- Ton Mac **ouvre chaque lien cité** pour vérifier qu'il existe : un lien introuvable est marqué ⚠️.
- La **fiabilité** est indiquée : ✅ solide (sources officielles concordantes), 🟡 partielle, ⚠️ incertaine.

## Les commandes

Toujours d'abord : `cd ~/Assistant && source .venv/bin/activate`

| Je veux… | Commande |
|---|---|
| Une recherche dans le Terminal (avec les adresses) | `python assistant.py recherche "ta question"` |
| La page de mes dernières recherches | `python assistant.py recherche page` |
| Retrouver une ancienne recherche | `python assistant.py memoire PEA` (elles sont dans ta mémoire) |

## Confidentialité et coût

- Ce qui quitte le Mac : **ta question** (vers Anthropic et son moteur de recherche). Rien d'autre.
- Tes recherches restent sur ton Mac : ta mémoire, et `donnees/recherche/` (les 20 dernières, lisibles par toi seul).
- **1 appel au modèle fort par question**, mais qui lit beaucoup (≈ 20 000 à 60 000 tokens) : il consomme plus de
  ton abonnement qu'une aide classique. Rien n'est lancé tout seul.
