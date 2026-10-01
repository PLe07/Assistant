# Tri automatique des mails : la fiche

## Comment ça marche

- **Toutes les 3 minutes**, tant que ta session Mac est ouverte, un service macOS (launchd)
  regarde les **nouveaux** mails de ta boîte de réception.
- Les cas évidents sont triés par des **règles gratuites** (R1 : promotions, R2 : réseaux sociaux).
  Les autres sont classés par **Claude Sonnet, via ton abonnement**.
- Chaque mail reçoit **une étiquette**. Les 🟢 et ⚫ sont **archivés** (jamais supprimés).
- Une mémoire locale (`memoire.db`) garantit qu'**un mail n'est traité qu'une fois**.
- **Confidentialité** : tout tourne sur ton Mac. Seuls l'expéditeur, l'objet et un extrait
  (1 500 caractères max, jamais les pièces jointes) partent chez Anthropic pour être classés.

| Étiquette | Pour quoi | Dans Gmail |
|---|---|---|
| 🔴 Important-Répondre | Un humain attend une réponse de toi, avec un enjeu | Reste dans la boîte |
| ⏰ Action-Deadline | Une échéance ou une tâche (payer, signer, envoyer…) | Reste dans la boîte |
| 🟡 À-lire | Intéressant, sans urgence | Reste dans la boîte |
| 🟢 Info-Auto | Confirmations, reçus, notifications | Archivé |
| ⚫ Poubelle | Pub, démarchage, spam déguisé | Archivé, jamais supprimé |

## Les commandes

Toujours d'abord, dans le Terminal :

```bash
cd ~/Assistant/tri-mails && source .venv/bin/activate
```

| Je veux… | Commande |
|---|---|
| Savoir si ça tourne | `python service.py etat` |
| Voir ce qui a été trié | `python service.py journal` |
| **Mettre en pause** | `python service.py pause` |
| Reprendre | `python service.py reprendre` |
| **Arrêter complètement** | `python service.py desinstaller` |
| Redémarrer après un arrêt | `python service.py installer` |
| Trier tout de suite, sans attendre | `python trier.py --reel` |
| Tester un réglage sans rien modifier | `python trier.py --test 20` |

## Réajuster les bacs

| Je veux… | Où |
|---|---|
| Corriger **un** mail mal classé | Dans Gmail : retire l'étiquette ou remets-le dans la boîte. Le tri n'y retouchera plus. |
| Une règle sur un expéditeur, une école, une personne | `open -e regles_perso.txt` (reste sur ton Mac, pris en compte au passage suivant) |
| Changer la définition d'un bac | `prompt_classification.md` |
| Couper une règle gratuite | `config.py` : `REGLE_R1_PROMOTIONS = False` (ou R2) |
| Changer de modèle | `.env` : `MODELE=opus` ou `MODELE=sonnet` |

Après chaque réglage, vérifie avec `python trier.py --test 20` : rien n'est modifié, tu vois juste le résultat.

## En cas de problème

`python service.py etat` affiche la dernière erreur. Puis :

| Message | Solution |
|---|---|
| « Jeton Claude refusé » (il expire au bout d'un an) | `python renouveler_jeton.py` |
| « Aucun jeton Gmail valide » ou « jeton expiré » | `python verifier_connexion.py` (rouvre le navigateur) |
| « Quota de l'abonnement atteint » | Rien à faire : le tri reprend tout seul |
| « non installé » | `python service.py installer` |
| Dossier déplacé ou Python mis à jour | `python service.py installer` |
| Après un `git pull` | Rien à faire : le passage suivant utilise la nouvelle version |

Le journal détaillé est dans `logs/tri.log`. Les plantages inattendus vont dans `logs/launchd.log`.

## Tout retirer proprement

1. `python service.py desinstaller`
2. Retirer l'accès Gmail : <https://myaccount.google.com/permissions> (ligne « Tri mails »)
3. Révoquer le jeton Claude : <https://claude.ai/settings/claude-code>
4. Supprimer le dossier `~/Assistant`. Les étiquettes restent dans Gmail : supprime-les dans
   *Paramètres → Libellés* (supprimer une étiquette ne supprime jamais les mails).

## Sécurité

- `.env`, `credentials.json`, `token.json`, `memoire.db`, `logs/` et `regles_perso.txt` restent
  **sur ton Mac** : ils sont exclus de GitHub. Ne les partage jamais.
- Le dépôt GitHub est **public** : n'y mets jamais de nom, d'adresse ni de secret.
