# Assistant

Un assistant personnel qui tourne en arrière-plan sur le Mac : un système nerveux **local**
(léger, gratuit, privé) qui ne réveille le cerveau (Claude, via l'abonnement) qu'aux bons moments.

| Dossier / fichier | Rôle |
|---|---|
| `core/` | Le cœur partagé : réglages, journal, état (SQLite), Claude, notifications |
| `modules/` | Un fichier par module, activable dans `reglages.json` |
| `superviseur.py` | Lance et surveille les modules activés, les relance s'ils tombent |
| `menubar.py` | L'icône de contrôle dans la barre du haut (pause et micro coupés en un clic, aides 💡) |
| `assistant.py` | Les commandes : `pause`, `reprendre`, `etat`, `journal`, `micro off/on`, `activer/desactiver <module>`… |
| `service.py` | Le démarrage automatique (launchd) |
| `modules/mails/` | Phase 1 · le tri automatique des mails (voir `modules/mails/README.md`) |
| `modules/oreilles/` | Phase 2 · l'écoute locale du micro (voir `modules/oreilles/README.md`) |
| `tri-mails/` | Ancienne version du tri, gardée en sauvegarde |

Restent **sur le Mac uniquement** (exclus de GitHub) : `.env`, `reglages.json`, `donnees/`, `logs/`.

La fiche d'utilisation complète arrivera en phase 6.
