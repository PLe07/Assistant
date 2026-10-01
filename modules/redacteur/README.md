# Le rédacteur dans ta voix : la fiche

Mails délicats, lettres de motivation d'alternance, posts : **écrits dans ton style**. Rien n'est envoyé :
ce sont des brouillons, que tu copies en un clic.

## 1. Une fois : ta fiche de style

Icône → **✒️ Rédacteur** → **« 🎨 Faire ma fiche de style »** (ou `python assistant.py rediger style`).

- Ton Mac lit tes **25 derniers mails envoyés** (lecture seule) et n'en garde que **ton** texte.
- Tu peux ajouter d'autres textes à toi (posts, lettres) dans `donnees/redacteur/mes_textes/`.
- Environ 6 000 caractères partent **une fois** à Claude, qui décrit ta manière d'écrire et te montre un
  **échantillon**. La fiche (`donnees/redacteur/style.md`) ne contient aucun nom ni info perso ; retouche-la à la main
  si besoin.

Pour les **lettres de motivation** : complète ton profil (icône → ✒️ Rédacteur → « 👤 Mon profil », ou
`python assistant.py rediger profil`). Le rédacteur n'invente rien : une info absente devient **[À COMPLÉTER]**.

## 2. Rédiger

- Icône → **✒️ Rédacteur → « ✒️ Rédiger dans mon style… »** : dis quoi écrire (« mail à mon prof pour demander un délai
  d'une semaine », « lettre de motivation pour l'alternance chargé de clientèle chez … + colle l'annonce »,
  « post LinkedIn : j'ai validé l'UE11 »). Le brouillon s'ouvre tout seul : **« Copier »**.
- Ou dans ✍️ Noter ou demander : « **rédige un mail** à… », « **écris un post**… ».
- Ou à voix haute : « **Assistant, rédige un mail** à… » (le brouillon t'attend dans 💡 Aides).
- Ou : `python assistant.py rediger "mail à mon prof pour…"`.

Chaque brouillon est gardé dans `donnees/redacteur/brouillons/` et dans ta mémoire.

## Confidentialité et coût

- Tes textes et ton profil restent sur ton Mac (lisibles par toi seul).
- La fiche : 1 appel au modèle fort, une fois. Chaque brouillon : 1 appel (ta demande + ta fiche, + ton profil
  pour une lettre).
