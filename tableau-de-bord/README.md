# Tableau de bord

D'un coup d'œil : tes modules tournent-ils, ont-ils fait leur travail, combien te coûtent-ils (crédits Claude,
batterie), et leur code a-t-il changé ? Le tableau de bord **observe seulement** : il ne modifie, n'arrête, ne relance
et ne ralentit jamais un autre module.

- **Page locale** : `tableau ouvrir` (ou l'icône de la barre des menus → « Ouvrir le tableau de bord »).
- **Barre des menus** : un point 🟢 tout va bien, 🟠 quelque chose à regarder, 🔴 un module ne fait plus son travail.
- **iPhone** : `iCloud Drive/Tableau/Etat.html` dans l'app Fichiers (états, compteurs, crédits ; mis à jour toutes
  les 15 min et à chaque changement).
- **Terminal** : `tableau etat`, `tableau module <nom>`, `tableau credits`, `tableau integrite`, `tableau doctor`…

Installation : `./install.sh` (voir ACTIONS_HUMAINES.md). Rien d'autre à faire ensuite.

## Lire le tableau de bord

En haut, un **bandeau** : « ✅ Tout va bien » ou « 🟡 2 choses à regarder ». Dessous, **une carte par module** :

| Sur la carte | Ce que ça veut dire |
|---|---|
| La pastille et la phrase | l'état du module, en une phrase (« Tourne depuis 3 j », « « brief » : pas fait ») |
| Dernière activité | la dernière chose utile qu'il a faite (« dernière facture classée il y a 2 h ») |
| Erreurs sur 24 h | les erreurs écrites dans son journal |
| Processeur, mémoire | ce qu'il consomme en ce moment |
| Crédits du mois | dépensé sur son plafond, avec une petite barre (« estimé » : calculé, pas facturé) |
| Prochaine tâche | ce qu'il doit faire bientôt (« brief demain à 7h15 ») |

Un clic sur une carte ouvre le **détail** : historique sur 7 et 30 jours (temps en bonne santé, erreurs, processeur,
mémoire ; « Voir les chiffres » sous chaque graphique), ses attentes tenues ou manquées, ses derniers messages
d'erreur (sans rien de personnel), l'état de son code, et le bouton « Lancer le diagnostic ».

Les onglets du haut : **Crédits** (total du mois, par module, projection à la fin du mois), **Ressources** (« Mon
assistant me coûte-t-il de la batterie ? » en une phrase), **Intégrité** (le code de chaque projet), **Journal** (ce
qui s'est passé, filtrable par module). La page se met à jour toute seule.

## Comprendre chaque pastille

| Pastille | Veut dire | Exemples |
|---|---|---|
| 🟢 | tout va bien | il tourne, il a fait son travail à l'heure |
| 🟡 | quelque chose à regarder | une file qui attend depuis 30 min, un pic d'erreurs, 80 % du budget, un code changé, état inconnu (launchd ne répond pas) |
| 🔴 | il ne fait plus son travail | arrêté alors qu'il devrait tourner, plantages en boucle, figé, budget dépassé, n8n injoignable |
| ⚪ | pas installé, éteint ou en pause | Corvées en pause, un module que tu as désinstallé |

Un Mac qui dort n'est pas une panne : les retards se comptent en temps éveillé, et un travail prévu pendant la veille
est attendu au réveil.

## Gérer une alerte

Les notifications sont rares : une seule par problème (un rappel au bout de 24 h s'il dure), **3 par jour au plus**
(regroupées), **rien entre 23 h et 8 h** sauf une boucle de plantages qui consomme. Quand c'est réglé, tu reçois
« ✅ … tourne de nouveau ».

1. Lis la notification : elle dit quoi faire (« Tape bouclier doctor pour voir pourquoi »).
2. Ouvre la carte du module (`tableau module bouclier`, ou un clic sur la carte) : le détail dit depuis quand,
   les derniers messages d'erreur, et propose « Lancer le diagnostic » (la commande du module, seulement sur ton
   clic, avec confirmation).
3. Besoin de calme ? « Mettre les alertes en sourdine 1 h » dans la barre des menus, ou `tableau sourdine 2h`
   (`tableau sourdine fin` pour la lever). Ce qui est encore vrai à la fin te sera dit.

## Valider une nouvelle référence d'intégrité

Le tableau de bord garde l'empreinte du code et des réglages de chaque projet. Si un fichier change, tu reçois
« ⚠️ Le code du Trieur a changé : 3 fichiers modifiés. C'était voulu ? ».

- **C'était toi** (une mise à jour, un réglage) : bouton « C'était moi, nouvelle référence » sur la page, ou
  `tableau integrite accepter trieur`. L'alerte se ferme sans autre message.
- **Pas normal** : bouton « Pas normal ». La page affiche la liste des fichiers et la commande `git diff` à lancer
  toi-même. Le tableau de bord **ne restaure jamais rien**.

## Ajouter un futur module

Rien à faire dans la plupart des cas : un nouveau LaunchAgent `com.<ta session>.<module>` est découvert tout seul
(toutes les 10 min) et ajouté à la fin de `~/Library/Application Support/TableauDeBord/modules.toml`, avec l'état
launchd, le processeur, la mémoire et son journal.

Pour en savoir plus sur lui, complète son bloc dans `modules.toml` (le fichier est à toi, il n'est jamais réécrit) :

```toml
[[module]]
id = "jardin"
nom = "Jardin"
emoji = "🌱"
adaptateur = "tolerant"          # lit, s'ils existent : battement, coûts, preuves des attentes
labels = ["com.<ta session>.jardin"]
dossier_projet = "~/Projets/jardin"
dossier_donnees = "~/Library/Application Support/Jardin"   # ses bases *.db (copiées, jamais ouvertes)
dossier_logs = "~/Library/Logs/Jardin"
perimetre_code = ["."]           # ce que le gardien d'intégrité surveille
plafond_usd = 1.0                # son budget Claude du mois
aide = "jardin doctor"           # la commande citée dans les alertes

[[module.attente]]
id = "arrosage"
genre = "quotidienne"
libelle = "arrosage chaque jour vers 7h"
heure = "07:00"
tolerance_min = 30
```

L'adaptateur `tolerant` lit dans ses bases (tables `meta` ou `etat`, colonnes `cle`/`valeur`) : `battement` (date),
`preuve:arrosage` (date du dernier arrosage) ; et ses dépenses dans une table `depenses_ia` ou `couts` avec une
colonne `cout_usd`. Tout ce qui manque reste « inconnu », sans fausse alerte. `actif = false` fait ignorer un module.
Voir aussi `modules.example.toml`.

## Désinstaller

```
cd ~/Assistant/tableau-de-bord
./uninstall.sh
```

Il retire l'agent, la commande `tableau`, les données, les journaux, l'instantané iCloud et l'environnement Python ;
il demande avant de retirer ta clé Admin facultative. Aucun autre module n'est touché (empreinte comparée avant et
après). Seul ce dossier reste.

## En cas de souci

`tableau doctor` dit tout : le démon tourne-t-il, la page, les réglages, chaque module et ce qu'on n'arrive pas à
lire chez lui (« inconnu : base (table absente) »). Journal : `~/Library/Logs/TableauDeBord/tableau.log` (sans rien de
personnel). Réglages facultatifs : `~/Library/Application Support/TableauDeBord/reglages.toml` (une valeur fausse
est remplacée par sa valeur par défaut, et `tableau doctor` le dit).
