# 🗓 La revue du dimanche

Le bilan de ta semaine (les 7 derniers jours ; un dimanche soir, du lundi au dimanche), **au bouton** :
icône → « 🗓 Ma revue de la semaine », ou `python assistant.py revue`.

| Rubrique | D'où ça vient (lu sur ton Mac) |
|---|---|
| ✅ Fait | rappels cochés (app Rappels, en lecture), mails triés par bac, brouillons du rédacteur, notes et rappels confiés, aides 💡 |
| 📚 Appris | séances du coach (réponses et moyenne par UE), recherches, points de veille |
| 💶 Dépensé | ton tableur des dépenses : total, catégories, comparé aux 7 jours d'avant |
| 📅 À venir | agenda et rappels des 7 prochains jours (+ rappels en retard) |

Puis **1 appel à Claude** (fort) : ta semaine en 3 phrases + 2 conseils pour la suivante.
À Claude ne partent que des **chiffres et des titres** (UE, recherches, veille, agenda, rappels) :
jamais tes mails, tes notes, tes réponses au coach, tes brouillons ni tes reçus.

Gardée : un fichier par semaine dans `donnees/revue/` (lisible par toi seul) et une ligne dans ta mémoire.
Relire la dernière sans Claude : `python assistant.py revue derniere`.

Une rubrique dont l'outil n'est pas prêt dit pourquoi (ex. accès au Calendrier) sans bloquer les autres.
