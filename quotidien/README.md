# Quotidien

Ton brief du matin, en une notification à 7 h 15 :

```
☀️ 14 °C → 19 °C, sec : veste légère, lunettes. Vélo OK.
🍽️ Ce soir : curry de pois chiches (20 min) — reste pour demain midi.
🎂 Demain : anniversaire de Léa → message prêt.
```

Quatre fonctions, sur ton Mac, sans abonnement :

| | Ce que ça fait | Quand |
|---|---|---|
| ☀️ Météo « habille-toi » | quoi mettre et comment te déplacer, selon la météo réelle de tes trajets | chaque matin ; alerte à 21 h si demain change beaucoup |
| 🍽️ Menu de la semaine | 7 dîners selon tes goûts, la saison, ton budget et tes journées chargées, la liste de courses par rayon | le dimanche à 17 h |
| 🧊 Vide-frigo | tu dis ce que tu as (photo, liste ou dictée), il te propose 3 recettes faisables tout de suite | quand tu veux, depuis l'iPhone ou le Mac |
| 🎂 Anniversaires | les rappels à l'avance et 3 messages prêts, que tu envoies toi-même | J-7 pour les proches, la veille, le jour J |

Installation : voir **ACTIONS_HUMAINES.md** (5 minutes).

## Lire le brief

- La notification de 7 h 15 (rien entre 23 h et 7 h, jamais).
- La page **Ma journée** : app Fichiers de l'iPhone → iCloud Drive → Quotidien → `Ma journée.html`.
- Tout de suite, sur le Mac : `quotidien brief`.

Une ligne n'apparaît que si elle a quelque chose à dire. Si le Mac dormait à 7 h 15, le brief part au réveil, mais
seulement avant 11 h (pas de « brief du matin » l'après-midi).

## Régler tes trajets, tes goûts et ton budget

Ouvre `~/Library/Application Support/Quotidien/profil.toml` avec TextEdit (Finder → Aller → Aller au dossier…).
Tout est expliqué dedans : régime, allergies, ce que tu détestes, budget de la semaine, jours chargés, jour des
courses, heures de départ et de retour, vélo ou tram. Le démon relit le fichier tout seul. Une faute de frappe est
signalée par `quotidien doctor`, jamais ignorée en silence.

Les heures (brief, menu, silence de la nuit…) et ta ville sont dans `reglages.toml`, au même endroit.

## Le menu de la semaine

- Le dimanche à 17 h, une notification ; la page `Menu de la semaine.html` dans iCloud Drive/Quotidien (recettes
  dépliables, quantités pour toi, liste de courses par rayon) ; la liste dans Rappels, « Courses (menu) ».
- `quotidien menu` : le menu, tout de suite. `quotidien menu --regenerer` : un autre menu.
- `quotidien menu remplacer jeudi` : un autre plat pour jeudi (les restes qui en dépendent suivent).
- `quotidien envie "mexicain et léger"` (ou le raccourci « Envie de… » sur l'iPhone) : pour le prochain menu.

### Noter un repas

```
quotidien noter jeudi 👍
quotidien noter hier 👎
```

👍 : il reviendra plus souvent. 👎 : il ne reviendra plus. Ajoute `--midi` pour le déjeuner.

## Le vide-frigo depuis l'iPhone

1. Lance le raccourci **Mon frigo** (ou dis « Dis Siri, Mon frigo »).
2. Choisis : **📷 Prendre une photo**, **🖼️ Choisir une photo** ou **✍️ Écrire ou dicter** (« 2 courgettes, feta, un
   reste de riz »).
3. En quelques secondes : ce que le Mac a compris, puis 3 recettes avec leur temps, ce qui manque et comment
   remplacer (« pas de crème ? un yaourt grec fait l'affaire »).

Le texte est compris sur le Mac, sans IA (gratuit). Une photo passe par l'IA (sur le budget de 2 $ par mois), après
avoir été réduite et vidée de toutes ses métadonnées (position, appareil). Si le Mac est éteint : « Mac injoignable,
réessaie plus tard ».

Sur le Mac : `quotidien frigo "2 courgettes, feta"` ou `quotidien frigo photo.jpg`, puis
`quotidien frigo ce-soir 2` pour mettre la recette n°2 au menu de ce soir. `--creatif` : une idée originale par l'IA
si rien ne va (vérifiée : allergènes, régime, cuisson à cœur).

## Les anniversaires

- Lus dans tes **Contacts** (lecture seule, jamais modifiés) et dans `proches.toml` (copie `proches.example.toml`
  dans `~/Library/Application Support/Quotidien/`) pour ajouter quelqu'un ou donner une relation, un ton et des
  notes (« souvenir : voyage à Lisbonne »).
- La veille au soir, une notification ; le jour J à 9 h, une fenêtre avec 3 messages : choisis-en un, **Ouvrir dans
  Messages**, relis, et c'est toi qui appuies sur Envoyer. Les messages sont aussi dans ta liste de Rappels
  « Anniversaires » (pour les copier depuis l'iPhone).
- `quotidien anniversaires` : les prochains. `quotidien anniversaires message Léa` : ses 3 messages.
  `quotidien anniversaires ouvrir Léa 2` : ouvre Messages avec le n°2.
- L'IA ne reçoit que le prénom, la relation, le ton, l'âge et tes notes : jamais le nom de famille, le numéro ou
  l'adresse. Sans IA, des modèles variés prennent le relais. Quotidien ne peut envoyer aucun message.

## Vérifier que tout va bien

```
quotidien doctor
```

L'état de chaque brique (démon, météo, menu, Contacts, Rappels, iCloud, IA et budget du mois), et la prochaine
exécution de chaque tâche.

## Désinstaller

```
cd ~/Assistant/quotidien
./uninstall.sh
```

Il arrête le démon, retire la commande, et te demande si tu veux supprimer tes listes de Rappels créées par
Quotidien (et seulement elles). Tes données restent (`./uninstall.sh --tout` pour les retirer aussi).

## Pour aller plus loin

- `INTEGRATION.md` : comment l'assistant (ou un autre outil) lit le brief et dépose une envie.
- `DECISIONS.md` : chaque choix et sa raison. `PROGRESS.md` : les preuves de chaque étape.
- `./check.sh` : la vérification complète (tests, style, couverture, intégrité des autres projets).
