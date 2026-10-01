# Le coach DCG / AMF : la fiche

## Comment ça marche

1. Tu **copies tes cours** dans `donnees/coach/cours/`, un dossier par matière (PDF, Word, RTF, texte).
   Ils sont lus **sur ton Mac** et découpés en morceaux d'environ une page.
2. Chaque jour à **18:30**, le coach prépare **3 questions** : d'abord celles à revoir, puis des nouvelles
   que Claude tire d'**un seul morceau** de tes cours (jamais le cours entier). Une notification discrète te le dit.
3. Tu réponds quand tu veux : icône → **« 🎓 Coach »**, `python assistant.py coach`, ou « Assistant, interroge-moi ».
4. **Correction** : les QCM sur ton Mac ; les questions rédigées par Claude (note sur 5, ce qui manquait, l'idée à retenir).
5. **Révisions espacées** : une question ratée revient dès le lendemain ; une question réussie revient
   de plus en plus tard (2, 4, 8, 16 jours). Tes notions faibles sont visées en priorité.

Pas de cours pour une matière (par défaut : « Certification AMF ») ? Claude t'interroge sur le
programme général, et la question est marquée « à vérifier ».

## Les commandes

Toujours d'abord : `cd ~/Assistant && source .venv/bin/activate`

| Je veux… | Commande |
|---|---|
| Voir les cours trouvés (et ouvrir le dossier) | `python assistant.py coach cours` · `open ~/Assistant/donnees/coach/cours` |
| Répondre à mes questions du jour | `python assistant.py coach` ou icône → « 🎓 Coach » |
| Voir mes progrès et mes points faibles | `python assistant.py coach bilan` |
| Recevoir les questions chaque jour à l'heure dite | `python assistant.py activer coach` |
| Arrêter | `python assistant.py desactiver coach` |

## Réglages (`reglages.json` → `modules.coach`)

| Réglage | Par défaut | Rôle |
|---|---|---|
| `heure` | `"18:30"` | heure des questions du jour |
| `questions` | `3` | nombre de questions par jour (1 à 10) |
| `matieres_sans_support` | `["Certification AMF"]` | matières interrogées sans cours (programme général) |

## Confidentialité et coût

- Tes cours, tes réponses et tes notes restent sur ton Mac (`donnees/coach/`, lisible par toi seul).
- Seul l'extrait du jour (une page) part à Claude pour les questions, et tes réponses rédigées pour la correction.
- Environ **2 appels par jour** (1 pour les questions, 1 pour la correction ; 0 si tout est en QCM).
