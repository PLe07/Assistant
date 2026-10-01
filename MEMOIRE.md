# La mémoire, les rappels et le second cerveau : la fiche

## Ce que ça fait

| Tu dis ou tapes… | L'Assistant… | Appels à Claude |
|---|---|---|
| « Assistant, **note que** le portail c'est 4521 » | le garde dans ta mémoire · notification « 📝 Noté » | 0 |
| « Assistant, **rappelle-moi** demain à 9 h d'appeler la banque » | comprend quoi et quand · l'ajoute à l'app Rappels (liste « Assistant ») · notification qui confirme | 1 rapide |
| « Assistant, **qu'est-ce que je t'avais dit** sur le PEA ? » | cherche dans ta mémoire, puis Claude répond avec ce qu'il a trouvé · la réponse t'attend dans « 💡 Aides » | 1 (0 si rien trouvé) |
| « **pense à** acheter du pain » (sans « Assistant ») | ne crée rien : une 💡 te **propose** le rappel, ton clic le crée | 1 rapide |

Par écrit, c'est pareil : icône → **« ✍️ Noter ou demander… »**, ou `python assistant.py noter "…"`.
Une question tapée (« où est garé mon vélo ? ») va à ton second cerveau ; le reste est noté.

## Ce qui entre dans ta mémoire (et ce qui n'y entre jamais)

- **Oui** : ce que tu adresses à l'Assistant (« Assistant, … »), ce que tu tapes, les aides 💡 que tu
  ouvres (titre + réponse de Claude), les rappels, les questions à ton second cerveau et leurs réponses.
- **Jamais** : les conversations entendues autour de toi, le texte de ton écran, le son.
- Elle reste sur ton Mac (`donnees/memoire.db`, lisible par toi seul), **jusqu'à ce que tu l'effaces**.
  Le journal n'en contient rien : les notifications de notes et de rappels y sont masquées.
- Tes **habitudes** ne gardent aucun contenu : quand, d'où (oreilles, yeux), quel type, quelle appli,
  et si tu as ouvert la 💡. `python assistant.py habitudes` te montre le bilan.

## Les rappels Apple

- **Mode test au départ** : rien n'est créé, une notification « 🧪 Essai : j'aurais créé … » te montre
  ce qui a été compris. Passe en vrai quand tu es prêt : `python assistant.py rappels reel`.
- La première fois en mode réel, macOS demande : « Python souhaite contrôler Rappels » → **Autoriser**.
  Refusé par erreur ? Réglages Système → Confidentialité et sécurité → Automatisation → Python → coche « Rappels ».
- L'Assistant **ajoute** des rappels : il ne modifie ni n'efface jamais ceux qui existent.
- Claude indisponible (quota, panne) : le rappel est quand même créé, sans date. Rien ne se perd.

## Les commandes

Toujours d'abord : `cd ~/Assistant && source .venv/bin/activate`

| Je veux… | Commande |
|---|---|
| Noter, créer un rappel ou poser une question | `python assistant.py noter "…"` ou icône → « ✍️ Noter ou demander… » |
| Poser une question à mon second cerveau | `python assistant.py demander "qu'est-ce que j'avais noté sur … ?"` |
| Chercher dans ma mémoire | `python assistant.py memoire dentiste` ou icône → « 🔎 Chercher dans ma mémoire… » |
| Voir mes derniers souvenirs | `python assistant.py memoire` |
| Effacer un souvenir | `python assistant.py oublier 12` (le n° vient de `memoire`) |
| **Tout effacer** (souvenirs et habitudes) | `python assistant.py oublier tout` (il faut taper OUI) |
| Voir mes rappels, passer en réel / en test | `python assistant.py rappels` · `rappels reel` · `rappels test` |
| Voir mes habitudes | `python assistant.py habitudes` |
| Essai guidé, en vrai | `python assistant.py essai-memoire` (ou `--etape 3` pour une seule étape) |

## Réglages (`reglages.json`)

| Réglage | Par défaut | Rôle |
|---|---|---|
| `rappels.mode` | `"test"` | `"test"` : rien n'est créé · `"reel"` : ajouté à l'app Rappels |
| `rappels.liste` | `"Assistant"` | la liste de l'app Rappels (créée au besoin) |
