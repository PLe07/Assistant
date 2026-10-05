# Le détecteur de corvées répétées : la fiche

**Il propose, tu décides.** Il observe discrètement ce que tu refais à la main sur ton Mac. Une fois par jour, il te
propose des automatisations concrètes, avec le temps que tu gagnerais. Il n'automatise jamais rien tout seul.

## À quoi ça sert

Exemples de ce qu'il repère :
- « Tu déplaces les fichiers « Facture_*.pdf » de ~/Downloads vers ~/Documents/Factures : 12 fois en 4 semaines. »
- « Tu ouvres Safari, puis vas sur mail.google.com, calendar.google.com et notion.so vers 08:34 : 20 fois en 4
  semaines. »
- « Tu tapes « cd ~/Projets/assistant && git pull && python main.py » dans le terminal : 28 fois en 4 semaines. »

Pour chacune, il propose une solution : un raccourci de terminal, une tâche automatique, une règle de dossier,
un raccourci de l'app Raccourcis… Il fournit un script prêt à l'emploi, contrôlé, et le pas à pas. Un exemple
complet, fait sur un mois inventé : [demo/rapport_demo.html](demo/rapport_demo.html).

## Comment ça marche

1. **Il observe** (sans jamais lire tes documents ni tes mails, sans clavier, sans écran, sans micro) :
   - l'appli au premier plan ;
   - les titres de fenêtres (caviardés) ;
   - les fichiers déplacés ou renommés dans Téléchargements, Bureau et Documents ;
   - les commandes du terminal (zsh) ;
   - les sites visités (le domaine et le chemin, sans les paramètres) ;
   - les copier-coller (seulement d'où vers où, jamais le contenu) ;
   - l'inactivité.
2. **Chaque soir à 21 h** (au réveil si ton Mac dormait), il cherche ce qui se répète, sur ton Mac, sans
   internet.
3. **Claude** reçoit au plus 8 corvées, résumées et caviardées, une fois par jour. Il les décrit en français et
   propose une solution. Sans Claude (budget atteint, pas de réseau), les descriptions sont faites sur place.
4. **Une notification**, seulement s'il y a du nouveau, jamais entre 23 h et 8 h : « 🔁 3 corvées repérées —
   environ 45 min/mois à récupérer. »

## Les commandes

Toujours d'abord : `cd ~/Assistant && source .venv/bin/activate`. Ensuite `python assistant.py corvees …`, ou
simplement `corvees …` avec l'alias de [ACTIONS_HUMAINES.md](ACTIONS_HUMAINES.md).

| Je veux… | Commande |
|---|---|
| Voir mes corvées repérées | `corvees rapport` |
| Savoir s'il tourne | `corvees status` |
| Accepter une proposition (étapes et script) | `corvees accept ID` |
| …et la faire installer pour moi (alias, tâche automatique) | `corvees accept ID --installer` |
| Défaire une installation | `corvees desinstaller ID` |
| Ne plus jamais la voir | `corvees reject ID` (elle revient seulement si elle devient 3 fois plus fréquente) |
| La revoir plus tard | `corvees snooze ID 7` (dans 7 jours) |
| Analyser tout de suite | `corvees analyser --maintenant` |
| Faire le point (capteurs, autorisations, coût) | `corvees doctor` |

L'**ID** est le petit code à 6 caractères affiché à côté de chaque corvée dans le rapport.

## Pause, purge, désinstallation

- **Pause** : `corvees pause` coupe tous les capteurs dans la seconde, jusqu'à `corvees resume`.
  `corvees pause 2` coupe pendant 2 heures. La pause générale de l'Assistant (`python assistant.py pause`)
  l'arrête aussi.
- **Purge** : `corvees purge` efface tout, après confirmation : événements, corvées, décisions, propositions,
  rapport. Ce que tu avais installé avec `--installer` est d'abord désinstallé.
- **Désinstallation** : `python assistant.py desactiver corvees` arrête le module, puis `corvees purge` efface ses
  données. Ton `~/.zshrc` n'a jamais été touché : retire seulement les lignes que tu y avais ajoutées toi-même.

## Confidentialité et coût

- **Tout reste sur ton Mac**, dans `~/Assistant/donnees/corvees/`, lisible par toi seul (600).
- **Jamais noté** :
  - les applis de mots de passe, Messages, FaceTime et les applis bancaires ;
  - les sites des banques, impots.gouv, ameli, doctolib et caf ;
  - les fenêtres de navigation privée ;
  - les dossiers que tu exclus.
- **Caviardé avant d'être écrit** : e-mails, téléphones, IBAN, cartes, clés et jetons, mots de passe dans les
  commandes, paramètres d'adresse.
- **30 jours** d'événements, puis seulement des comptes par jour. La purge est automatique.
- **Claude** ne reçoit que des corvées résumées et caviardées (jamais un événement brut, une date, un fichier) :
  au plus une demande par jour, et un plafond de 2 $ par mois en équivalent API. Avec ton abonnement, cela ne
  coûte rien de plus.
- **Ressources** mesurées (dans l'environnement de construction ; à confirmer sur ton Mac, voir
  ACTIONS_HUMAINES) : le démon utilise 0,2 % de CPU et 30 Mo de mémoire. L'analyse du soir tourne à part, en
  quelques secondes.

## Réglages

Dans `reglages.json` → `"modules"` → `"corvees"`. Tous les seuils sont dans `modules/corvees/config.py` (valeurs
par défaut). Exemples :

```json
"corvees": {
  "actif": true,
  "fichiers": {"dossiers": ["~/Downloads", "~/Desktop", "~/Documents"]},
  "exclusions": {"applis": ["Notion"], "domaines": ["monentreprise.fr"], "dossiers": ["~/Documents/Perso"]},
  "analyse": {"heure": "21:00"},
  "ia": {"modele": "rapide", "budget_mensuel_usd": 2.0}
}
```

## Quand ça ne va pas

| Ce que je vois | Quoi faire |
|---|---|
| `doctor` : « Démon arrêté alors que le module est allumé » | `python service.py installer`, puis attends 1 minute |
| `doctor` : « Capteur fenetres désactivé » | Réglages Système → Confidentialité et sécurité → Accessibilité → « Python » |
| `doctor` : « Capteur navigateur dégradé : Accès complet au disque » (Safari) | Réglages Système → Confidentialité et sécurité → Accès complet au disque → « Python » (facultatif) |
| « Claude : jeton absent » | `python assistant.py renouveler-jeton` (en attendant, descriptions faites sur place) |
| Rien dans le rapport après quelques jours | normal au début : il faut une même action sur plusieurs jours. `corvees status` pour voir les événements |

Pour les curieux : les choix techniques sont dans [DECISIONS.md](DECISIONS.md), et les preuves de chaque étape
dans [PROGRESS.md](PROGRESS.md) et [RAPPORT_FINAL.md](RAPPORT_FINAL.md).
