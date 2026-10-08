# Crédits

Le tableau de bord ne charge rien depuis Internet : la page, ses graphiques (dessinés en SVG par
`tableau/web/graphiques.py`), sa feuille de style et son script sont écrits ici. Aucune bibliothèque de graphiques.

## Paquets Python utilisés par le tableau de bord

| Paquet | Licence | Pour quoi |
|---|---|---|
| [psutil](https://github.com/giampaolo/psutil) | BSD-3-Clause | processeur et mémoire des modules, charge du Mac (lecture seule) |
| [watchdog](https://github.com/gorakhargosh/watchdog) | Apache-2.0 | FSEvents : prévenu quand le code d'un projet change |
| [rumps](https://github.com/jaredks/rumps) | BSD-3-Clause | l'icône de la barre des menus (Mac seulement) |

## Outils de développement et de test (jamais installés pour faire tourner le tableau de bord)

| Paquet | Licence |
|---|---|
| pytest, pytest-cov | MIT |
| ruff | MIT |
| mypy, types-psutil | MIT / Apache-2.0 |
| hypothesis | MPL-2.0 |
| Playwright (Chromium sans fenêtre, tests de la page) | Apache-2.0 |

## Données

Tarifs publics des modèles Claude (pour estimer le coût de l'assistant, qui passe par ton abonnement) : documentation
d'Anthropic, relevés le 2026-10-06 (`tableau/analyse/credits.py`). Endpoint du rapport de coûts officiel (option
facultative) : documentation de l'API Admin d'Anthropic, vérifiée le 2026-10-07 (`tableau/analyse/credits_reels.py`).
