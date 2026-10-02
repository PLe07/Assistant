# Assistant

Un assistant personnel qui tourne en arrière-plan sur le Mac : un système nerveux **local**
(léger, gratuit, privé) qui ne réveille le cerveau (Claude, via l'abonnement) qu'aux bons moments.

👉 **Mode d'emploi en une page : [`FICHE.md`](FICHE.md)** (démarrer, mettre en pause, voir le journal,
activer un module, régler la proactivité, ajouter un module, tout arrêter).

| Dossier / fichier | Rôle |
|---|---|
| `core/` | Le cœur partagé : réglages, journal, état (SQLite), Claude, notifications |
| `modules/` | Un dossier par module ; chacun s'active ou se désactive dans `reglages.json` (`python assistant.py activer/desactiver <module>`) |
| `superviseur.py` | Lance et surveille les modules activés, les relance s'ils tombent |
| `menubar.py` | L'icône de contrôle dans la barre du haut (pause, micro et écran coupés en un clic, aides 💡) |
| `assistant.py` | Les commandes : `pause`, `reprendre`, `etat`, `journal`, `micro off/on`, `ecran off/on`, `activer/desactiver <module>`, `proactivite 0-3`… |
| `service.py` | Le démarrage automatique (launchd) |
| `modules/mails/` | Phase 1 · le tri automatique des mails (voir `modules/mails/README.md`) |
| `modules/oreilles/` | Phase 2 · l'écoute locale du micro (voir `modules/oreilles/README.md`) |
| `modules/yeux/` | Phase 3 · la conscience de l'écran (voir `modules/yeux/README.md`) |
| `core/memoire.py`, `core/rappels.py`, `core/consignes.py` | Phase 4 · mémoire, rappels Apple, second cerveau (voir `MEMOIRE.md`) |
| `modules/coach/` | Phase 5 · le coach DCG, à la demande (voir `modules/coach/README.md`) |
| `modules/veille/` | Phase 5 · la veille patrimoine + DCG, à la demande (voir `modules/veille/README.md`) |
| `modules/recherche/` | Phase 5 · la recherche sourcée sur le web (voir `modules/recherche/README.md`) |
| `modules/redacteur/` | Phase 5 · le rédacteur dans ta voix (voir `modules/redacteur/README.md`) |
| `modules/depenses/` | Phase 5 · le traqueur de dépenses (voir `modules/depenses/README.md`) |
| `modules/cine/` | Phase 5 · le concierge ciné : « je regarde quoi ce soir ? » (voir `modules/cine/README.md`) |
| `modules/revue/` | Phase 5 · la revue du dimanche : le bilan de ta semaine (voir `modules/revue/README.md`) |
| `modules/brief/` | Phase 5 · le brief du jour : agenda, mails à traiter, rappels (voir `modules/brief/README.md`) |
| `tri-mails/` | Ancienne version du tri, gardée en sauvegarde |

Restent **sur le Mac uniquement** (exclus de GitHub) : `.env`, `reglages.json`, `donnees/`, `logs/`.

La fiche d'utilisation complète arrivera en phase 6.
