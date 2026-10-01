# Les oreilles : la fiche

## Comment ça marche

1. Le micro est lu **en mémoire**, phrase par phrase (15 secondes au maximum), puis le son est oublié.
2. Chaque phrase est transcrite **sur ton Mac** (faster-whisper, modèle « small ») : le son ne part jamais.
3. Un détecteur **local** cherche une intention : « il faut que je… », « c'est quoi déjà… »,
   « j'ai oublié… », « rappelle-moi… », ou le mot d'appel en début de phrase (« Assistant, … »).
   Tant qu'il ne trouve rien, **Claude n'est pas appelé** et rien n'est noté.
4. S'il trouve : Claude **Haiku** (léger) reçoit uniquement cette phrase (et la précédente pour le
   contexte) et répond juste « puis-je aider concrètement ? ».
5. Si oui : notification « 💡 … » et l'icône affiche 💡. Clique sur 💡 → l'aide, rédigée par
   Claude **Sonnet** seulement à ce moment-là, s'ouvre dans une fenêtre (bouton « Copier »).

| L'icône | Veut dire |
|---|---|
| 🎙 | Le micro est ouvert : l'écoute est en cours |
| 💡 | Une aide t'attend dans le menu |
| ⏸ | Tout est en pause |

## Confidentialité

- **Rien n'est enregistré** : ni son, ni texte. Le journal dit ce qui s'est passé (« déclencheur
  besoin → aide proposée »), jamais ce que tu as dit.
- La phrase envoyée à Claude reste **en mémoire vive** 30 min au plus (pour rédiger l'aide si tu
  cliques), puis elle est oubliée. Couper le micro l'efface aussitôt.
- Seuls le titre de l'aide et le texte écrit par Claude sont gardés, 2 heures au plus.

## Les commandes

Toujours d'abord : `cd ~/Assistant && source .venv/bin/activate`

| Je veux… | Commande |
|---|---|
| **Couper le micro tout de suite** (quelqu'un est là) | `python assistant.py micro off` ou icône → « 🎙 Couper le micro » |
| Le rallumer | `python assistant.py micro on` |
| Activer / désactiver l'écoute en fond | `python assistant.py activer oreilles` / `desactiver oreilles` |
| Tester une phrase écrite, sans micro | `python -m modules.oreilles --phrase "il faut que je…"` |
| Voir ce qui est entendu, sans rien déclencher | `python -m modules.oreilles --test` (Ctrl + C pour arrêter) |
| Idem, avec l'avis de Claude (consomme du quota) | `python -m modules.oreilles --test --avec-claude` |
| Lister les micros | `python -m modules.oreilles --micros` |

## Réglages (`reglages.json` → `modules` → `oreilles`)

| Réglage | Valeurs | Effet |
|---|---|---|
| `mode` | `"passif"` (défaut) ou `"mot_appel"` | `mot_appel` : seul « Assistant, … » déclenche |
| `mot_appel` | `"assistant"` | Le mot qui t'adresse à lui |
| `uniquement_sur_secteur` | `false` / `true` | `true` : pas d'écoute sur batterie |
| `micro` | `null` ou un numéro | Le micro à utiliser (voir `--micros`) |
| `modele_transcription` | `"small"` | `"base"` : plus léger, moins précis |

`niveau_proactivite` (en haut du fichier) règle l'exigence : 0 = aucune initiative (seul
« Assistant, … » est pris en compte), 1 = 2 vérifications/heure et confiance ≥ 90,
2 = 4/heure et ≥ 80, 3 = 8/heure et ≥ 70. « Assistant, … » passe toujours (sauf pause).

Tes propres déclencheurs : une phrase par ligne dans `donnees/oreilles/declencheurs.txt`
(ex. « déclaration d'impôts »).

## En cas de problème

| Symptôme | Solution |
|---|---|
| Notification « Le micro semble bloqué par macOS » | Réglages Système → Confidentialité et sécurité → Micro : autorise Python, puis `micro off` et `micro on` |
| Trop de 💡 | Baisse `niveau_proactivite`, ou passe `mode` à `"mot_appel"` |
| Il ne réagit jamais | `python -m modules.oreilles --test` : regarde ce qu'il entend |
