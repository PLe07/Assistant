# Assistant

Un assistant personnel qui tourne en arrière-plan sur le Mac : un système nerveux **local**
(léger, gratuit, privé) qui ne réveille le cerveau (Claude, via l'abonnement) qu'aux bons moments.

| Dossier / fichier | Rôle |
|---|---|
| `core/` | Le cœur partagé : réglages, journal, état (SQLite), Claude, notifications |
| `modules/` | Un fichier par module, activable dans `reglages.json` |
| `superviseur.py` | Lance et surveille les modules activés, les relance s'ils tombent |
| `menubar.py` | L'icône de contrôle dans la barre du haut (pause en un clic) |
| `assistant.py` | Les commandes : `pause`, `reprendre`, `etat`, `journal`, `test-notif`, `test-claude`, `test-plantage` |
| `tri-mails/` | Le tri automatique des mails (voir `tri-mails/README.md`) |

Restent **sur le Mac uniquement** (exclus de GitHub) : `.env`, `reglages.json`, `donnees/`, `logs/`.

La fiche d'utilisation complète arrivera en phase 6.
