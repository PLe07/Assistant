# Le concierge ciné : la fiche

« **Je regarde quoi ce soir ?** » : dis ton humeur et ton temps, Claude te propose **3 choix** (films ou séries),
avec la durée et pourquoi ça colle à ton humeur.

- Icône → **🎬 Je regarde quoi ce soir ?** → « envie de rire, 1h30 », « série prenante, 2 épisodes »…
- Ou dans ✍️ Noter ou demander : « je regarde quoi ce soir ? envie de frissons ».
- Ou à voix haute : « **Assistant, je regarde quoi ce soir ?** » (la réponse t'attend dans 💡 Aides).
- Ou : `python assistant.py cine "envie de rire, 1h30"`.

**Ton temps est respecté** : ton Mac lit « 1h30 », « deux heures », « 2 épisodes de 45 min »… et écarte ce qui
dépasse. S'il manque des idées, il complète en dernier avec celles qui dépassent de 20 min au plus
(« ⚠️ dépasse ton temps de N min »), puis avec celles déjà proposées ces 30 derniers jours (signalées), et il dit
combien il en a écarté. La proposition du jour apparaît aussi dans ton **☀️ brief**.

**Coût** : 1 appel au modèle fort par demande (2 si les premières idées étaient trop longues), en effort moyen
(20 à 40 s) : en effort faible, Claude bâclait cette tâche. Rien n'est vérifié sur les plateformes.
Tes propositions restent sur ton Mac (`donnees/cine/`).
