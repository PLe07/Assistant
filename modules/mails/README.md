# Module « mails » : la fiche

## Comment ça marche

- **Toutes les 3 minutes**, tant que ta session Mac est ouverte, le superviseur de l'assistant
  lance un passage sur les **nouveaux** mails de ta boîte de réception.
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
cd ~/Assistant && source .venv/bin/activate
```

| Je veux… | Commande |
|---|---|
| Savoir si le tri tourne | `python -m modules.mails --etat` (et `python assistant.py etat`) |
| Voir ce qui a été trié | `python assistant.py journal` (lignes `[mails]`) |
| **Mettre tout l’assistant en pause** | Icône → *Tout mettre en pause*, ou `python assistant.py pause` |
| Arrêter seulement le tri | `python assistant.py desactiver mails` (et `activer mails` pour le relancer) |
| Trier tout de suite, sans attendre | `python -m modules.mails --reel` |
| Tester un réglage sans rien modifier | `python -m modules.mails --test 20` |

## Réajuster les bacs

| Je veux… | Où |
|---|---|
| Corriger **un** mail mal classé | Dans Gmail : retire l'étiquette ou remets-le dans la boîte. Le tri n'y retouchera plus. |
| Une règle sur un expéditeur, une école, une personne | `open -e donnees/mails/regles_perso.txt` (pris en compte au passage suivant) |
| Qu'un expéditeur ne soit **jamais archivé** (écoles…) | `open -e donnees/mails/jamais_archiver.txt` : un domaine ou une adresse par ligne |
| Changer la définition d'un bac | `modules/mails/prompt_classification.md` |
| Couper une règle gratuite, changer l'intervalle ou le modèle | `reglages.json` → `modules.mails` (`regle_r1_promotions`, `toutes_les_secondes`, `modele`) |

Après chaque réglage, vérifie avec `python -m modules.mails --test 20` : rien n'est modifié, tu vois juste le résultat.

## En cas de problème

`python -m modules.mails --etat` affiche la dernière erreur. Si le tri est bloqué, tu reçois aussi
**une** notification (au plus une toutes les 6 heures). Puis :

| Message | Solution |
|---|---|
| « Jeton Claude refusé » (il expire au bout d'un an) | `python assistant.py renouveler-jeton`, puis `python service.py redemarrer` |
| « Aucun jeton Gmail valide » ou « jeton expiré » | `python -m modules.mails --verifier-connexion` (rouvre le navigateur) |
| « Quota de l'abonnement atteint » ou « plafond » | Rien à faire : le tri reprend tout seul |
| Après un `git pull` | `python service.py redemarrer` |

Le journal détaillé est dans `logs/assistant.log` (lignes `[mails]`).

## Tout retirer proprement

1. `python assistant.py desactiver mails` (ou `python service.py desinstaller` pour tout l'assistant)
2. Retirer l'accès Gmail : <https://myaccount.google.com/permissions> (ligne « Tri mails »)
3. Révoquer le jeton Claude : <https://claude.ai/settings/claude-code>
4. Les étiquettes restent dans Gmail : supprime-les dans *Paramètres → Libellés*
   (supprimer une étiquette ne supprime jamais les mails).

## Sécurité

- Tes données du tri sont dans `donnees/mails/` (jetons Gmail, mémoire, règles perso) et l'adresse
  de la boîte dans `.env` : ils restent **sur ton Mac**, exclus de GitHub. Ne les partage jamais.
- Le dépôt GitHub est **public** : n'y mets jamais de nom, d'adresse ni de secret.
