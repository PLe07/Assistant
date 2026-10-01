# Les yeux : la fiche

## Comment ça marche

1. Toutes les 30 secondes, le module regarde **quelle fenêtre est devant toi**. Si c'est une appli
   ou un site **exclus**, il ne capture rien.
2. Sinon, il capture **cette fenêtre seulement**, en mémoire, et lit son texte **sur ton Mac**
   (Vision, la reconnaissance de texte de macOS). L'image est jetée aussitôt : jamais de fichier.
3. Un détecteur **local** cherche un signe de blocage qui **reste affiché** :

   | Signal | Exemple | Délai |
   |---|---|---|
   | Erreur | « Error », « échec », « command not found », « 404 » | 3 min |
   | Formulaire / démarche | « Cerfa », « champ obligatoire », « date de naissance »… (3 indices) | 5 min |
   | Question / exercice | une question ou un énoncé qui reste à l'écran | 3 min |
   | Tes mots | une ligne de `donnees/yeux/declencheurs.txt` | aussitôt |

   Tant qu'il ne trouve rien, **Claude n'est pas appelé** et rien n'est noté.
4. S'il trouve : Claude **Haiku** reçoit un extrait (1 500 caractères au plus, données sensibles
   masquées) et répond « puis-je aider ? ». Si oui : 💡 dans le menu et notification. Clique →
   Claude **Sonnet** rédige l'aide.
5. **« 👁 M'aider avec cet écran »** (menu de l'icône) : la fenêtre que tu as devant toi est lue
   tout de suite, et l'aide s'ouvre toute seule.

**Mode journal** (au départ) : le module note seulement « aurait déclenché… » dans le journal, sans
appeler Claude. Quand le journal te convient : `python -m modules.yeux --mode reel`.

## Confidentialité

- **Jamais capturées** : Mots de passe, Trousseaux d'accès, 1Password, Bitwarden, Dashlane,
  KeePassXC, LastPass, Messages, WhatsApp, Signal, Telegram, Messenger, et toute fenêtre dont le
  titre contient une banque (Revolut, BNP, Boursorama, Crédit Agricole…), impots.gouv, ameli,
  Doctolib, « navigation privée » ou « mot de passe ».
- **Pas regardée non plus** : l'appli Claude elle-même. Tu y parles déjà à Claude, et nos échanges
  (pleins de mots comme « erreur ») déclencheraient des vérifications pour rien.
- **Masqués avant l'envoi à Claude** : IBAN, numéros (carte, sécu, fiscal…), téléphones, e-mails,
  mots de passe et clés (`sk-ant-…`).
- **Rien n'est capturé** quand l'écran est verrouillé ou que tu es absent depuis 5 minutes.
- Le **journal** note le type de signal et le nom de l'appli, jamais le texte lu.

## Les commandes

Toujours d'abord : `cd ~/Assistant && source .venv/bin/activate`

| Je veux… | Commande |
|---|---|
| **Couper l'écran tout de suite** | `python assistant.py ecran off` ou icône → « 👁 Couper l'écran » |
| Le rallumer | `python assistant.py ecran on` |
| Activer / désactiver les yeux | `python assistant.py activer yeux` / `desactiver yeux` |
| Vérifier l'autorisation et la capture | `python -m modules.yeux --diagnostic` |
| Voir ce qu'il lit dans une fenêtre | `python -m modules.yeux --une-fois` (5 s pour changer de fenêtre) |
| Voir en direct ce qui déclencherait | `python -m modules.yeux --test --rapide` (Ctrl + C pour arrêter) |
| Tester un texte, sans capture | `python -m modules.yeux --texte "Erreur : fichier introuvable"` |
| Passer en vraies aides / revenir au journal | `python -m modules.yeux --mode reel` / `--mode journal` |
| Voir ce qui aurait déclenché | `grep "Aurait déclenché" logs/assistant.log` |

## Réglages (`reglages.json` → `modules` → `yeux`)

| Réglage | Valeurs | Effet |
|---|---|---|
| `mode` | `"journal"` (défaut) ou `"reel"` | `journal` : rien n'est proposé, tout est noté |
| `toutes_les_secondes` | `30` (10 minimum) | Un coup d'œil toutes les N secondes |
| `applis_exclues` | `["Mail", …]` | Applis à ne jamais capturer, **en plus** de la liste de base |
| `titres_exclus` | `["ma banque", …]` | Mots du titre de fenêtre à ne jamais capturer, en plus de la base |
| `uniquement_sur_secteur` | `false` / `true` | `true` : rien sur batterie |

Le niveau de proactivité est le même que pour les oreilles (`niveau_proactivite`). Le bouton
« M'aider avec cet écran » passe toujours (sauf pause), c'est toi qui demandes.

## En cas de problème

| Symptôme | Solution |
|---|---|
| Notification « Les yeux n'ont pas l'autorisation de voir l'écran » | Réglages Système → Confidentialité et sécurité → Enregistrement de l'écran : active Python, puis icône → « Couper l'écran » et « Rallumer » |
| `etat` dit « en veille » | Normal si tu étais absent, écran verrouillé, ou sur une appli exclue |
| Trop de 💡 | Baisse `niveau_proactivite`, ou repasse en `--mode journal` |
| macOS redemande l'autorisation chaque mois | Voulu par Apple depuis macOS 15 : clique « Autoriser » |
