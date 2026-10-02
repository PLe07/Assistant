# La veille patrimoine + DCG : la fiche

**Elle ne fait rien toute seule** : pas d'horaire, pas de notification. Elle lit l'actu quand tu le lui demandes.

## Comment ça marche

1. Icône en haut à droite → **« 📰 Veille »** → **« Quoi de neuf ? »**.
2. L'Assistant lit les sites officiels (20 à 40 s), garde seulement ce que tu n'as **jamais vu** (publié il y a
   moins de 30 jours) et écarte sur ton Mac ce qui est sans rapport (nominations, météo, papiers d'identité…).
3. Claude choisit ce qui compte **pour toi** : futur conseiller en gestion de patrimoine (épargne, assurance-vie,
   retraite, immobilier, impôts des particuliers, succession) **et** étudiant en DCG (fiscalité des entreprises,
   droit des sociétés, droit social, comptabilité). Pour chaque point : ★★★ à ★, une phrase « pourquoi ça compte »,
   et l'UE du DCG concernée.
4. Une fenêtre s'ouvre toute seule. **« Ouvrir les liens »** : la page avec les liens vers les articles officiels,
   et ce qui a été retenu ces 30 derniers jours.

Les points retenus entrent dans ta mémoire : « qu'est-ce que la veille disait sur le PER ? » (✍️ Noter ou demander).

## Les sources

Réglées dans `reglages.json` → `"veille"` → `"sources"` (par défaut : Impôts BOFiP, Service-public particuliers
et professionnels). Pour en ajouter une : `{"nom": "Mon site", "adresse": "https://…/rss.xml"}`. L'adresse peut
aussi être une page web : l'Assistant y cherche le flux RSS qu'elle annonce.

Un **flux RSS** = la liste des nouveautés qu'un site publie pour les logiciels (titre, lien, date, début du texte).

## Les commandes

Toujours d'abord : `cd ~/Assistant && source .venv/bin/activate`

| Je veux… | Commande |
|---|---|
| Une veille (sans l'icône) | `python assistant.py veille` |
| Vérifier que chaque site se lit bien (sans Claude) | `python assistant.py veille sources` |
| Ouvrir la page de ma dernière veille | `python assistant.py veille page` ou icône → 📰 Veille → « 📄 Ouvrir la page… » |

## Confidentialité et coût

- L'Assistant va sur internet **seulement** pour lire ces sites publics. Il ne leur envoie rien de toi.
- Claude reçoit uniquement des titres et débuts d'articles publics : rien de personnel.
- Les articles vus restent sur ton Mac (`donnees/veille/`, lisible par toi seul), oubliés au bout de 90 jours.
- **1 appel par veille** (modèle rapide), **0** s'il n'y a rien de nouveau. Rien d'autre.
