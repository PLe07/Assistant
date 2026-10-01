# Le traqueur de dépenses : la fiche

Une photo de reçu → le montant est extrait → une ligne s'ajoute à ton tableur (`donnees/depenses/depenses.csv`,
il s'ouvre dans Numbers ou Excel).

## Donner un reçu

- **Le dossier « Reçus »** (dans ton dossier personnel : `~/Reçus`) : dépose-y une photo ou un PDF (glisser-déposer,
  ou AirDrop depuis l'iPhone puis glisser depuis Téléchargements). Il est traité dans la minute, une notification
  te dit ce qui a été ajouté. Pour l'activer : `python assistant.py activer depenses`.
- **Le bouton** : icône → **🧾 Dépenses → « Ajouter un reçu… »** → choisis la photo.
- **Le Terminal** : `python assistant.py depenses ajouter ~/Downloads/ticket.jpg`.

**Mode test d'abord** (par défaut) : rien n'est écrit, la notification dit « 🧪 Essai : j'aurais ajouté … ».
Quand c'est juste : `python assistant.py depenses reel`.

## Ce qui se passe

1. Le texte du reçu est lu **sur ton Mac** (Vision, comme les yeux). **L'image ne quitte jamais le Mac.**
2. Ce texte part à Claude (modèle rapide) : date, commerçant, montant TTC, TVA, catégorie, moyen de paiement.
3. Mode réel : une ligne est **ajoutée** au tableur, et une **copie** de la photo est rangée dans
   `donnees/depenses/recus/AAAA-MM/`. Ta photo d'origine n'est jamais déplacée ni supprimée.
4. Jamais compté deux fois : une photo déjà traitée est reconnue à son empreinte ; un reçu déjà dans le tableur
   (même jour, même montant, même commerçant) est signalé « déjà dans ton tableur ».

Le tableur t'appartient : corrige une ligne à la main si besoin, l'Assistant n'ajoute qu'à la fin.

## Les commandes

| Je veux… | Commande |
|---|---|
| Le total du mois, par catégorie | `python assistant.py depenses` (ou icône → 🧾 Dépenses → 📊) |
| Un autre mois | `python assistant.py depenses 2026-09` |
| Passer en mode réel / test | `python assistant.py depenses reel` · `depenses test` |
| Ouvrir le tableur / le dossier Reçus | `python assistant.py depenses tableur` · `depenses dossier` |
| Surveiller le dossier (ou arrêter) | `python assistant.py activer depenses` · `desactiver depenses` |

Changer de dossier surveillé : `reglages.json` → `modules` → `depenses` → `"dossier"`.

## Coût

**1 appel au modèle rapide par reçu.** Rien d'autre.
