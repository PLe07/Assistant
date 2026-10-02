# Le coach DCG : la fiche

**Il ne fait rien tout seul** : pas d'horaire, pas de notification. Il t'interroge quand tu le lui demandes.

## Comment ça marche

1. Icône en haut à droite → **« 🎓 Coach »** → choisis une **UE du DCG** (UE1 à UE13).
2. Une petite fenêtre demande **combien de questions** (de 3 à 10).
3. Claude prépare les questions (10 à 30 s), puis elles s'ouvrent **une par une** : tu réponds, « Valider ».
   Pour un QCM, tape juste la lettre. « Plus tard » : tu reprendras là où tu t'es arrêté (même UE).
4. La **correction** s'ouvre toute seule : une note sur 5 par question, ce qui manquait, l'idée à retenir.
5. **Révisions espacées** : une question ratée revient à ta prochaine séance de cette UE ; une question réussie
   revient de plus en plus tard (2, 4, 8, 16 jours). Tes notions faibles sont visées en priorité.

Les questions viennent de **tes cours** si tu en as mis dans le dossier de l'UE, sinon du **programme officiel**
(la question le dit : ton prof peut avoir insisté sur autre chose).

## Tes cours

Dans `donnees/coach/cours/`, il y a un dossier par UE (créés pour toi). **Copie**-y tes cours : PDF, Word, RTF
ou texte. Ils sont lus **sur ton Mac** ; seul un extrait d'une page part à Claude pour préparer les questions.
Un fichier Pages : ouvre-le, puis Fichier → Exporter vers → Word (ou PDF).

## Les commandes

Toujours d'abord : `cd ~/Assistant && source .venv/bin/activate`

| Je veux… | Commande |
|---|---|
| Une séance (sans l'icône) | `python assistant.py coach` |
| Voir les cours trouvés, UE par UE | `python assistant.py coach cours` |
| Ouvrir le dossier des cours | icône → 🎓 Coach → « 📚 Ouvrir le dossier de mes cours » |
| Voir mes progrès et mes points faibles | `python assistant.py coach bilan` ou icône → 🎓 Coach → « 📊 Mon bilan » |
| Revoir ma dernière correction | icône → 🎓 Coach → « 📄 Revoir ma dernière correction » |

## Confidentialité et coût

- Tes cours, tes réponses et tes notes restent sur ton Mac (`donnees/coach/`, lisible par toi seul).
- Seul l'extrait d'une page part à Claude pour les questions, puis tes réponses rédigées pour la correction.
- **2 appels par séance** (1 pour les questions, 1 pour la correction ; 0 s'il n'y a que des QCM). Rien d'autre.
