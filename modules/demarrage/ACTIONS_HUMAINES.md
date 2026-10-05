# Ce qu'il te reste à faire toi-même — Nettoyeur de démarrage

Tout le reste est automatique. Il n'y a ici que ce qui exige ton Mac (le vrai launchd, tes autorisations) :
le Nettoyeur a été construit et vérifié dans un conteneur Linux, sur un faux Mac.

Les commandes se tapent dans le Terminal. Copie chaque bloc tel quel.

**Où tu en es (5 octobre au soir)** : § 1, § 2, § 3 et § 5 faits ; la relance après un plantage est prouvée.
Il reste seulement le § 9, une mesure de 10 minutes après le dernier allègement (D-47). Les § 4, 6, 7 et 8 sont
facultatifs.

## 1. Mettre à jour et faire le point (1 minute)

```zsh
cd ~/Assistant
git pull
.venv/bin/python demarrage.py doctor
```

Résultat attendu : `macOS 26… · arm64` coché, et les commandes `launchctl`, `ps`, `top`, `pmset`, `codesign`,
`mdls`… cochées. `sfltool` peut être marqué « réservé à l'administrateur » : c'est normal, et le Nettoyeur passe
par System Events (§ 4).

## 2. Le test de bout en bout et les mesures (5 minutes de ton temps, 15 minutes de mesure)

Le test crée deux éléments de test à lui (`com.assistant.nettoyeur.test.charge` et `…test.orphelin`), mesure,
désactive puis restaure l'élément de charge, et nettoie tout, même en cas d'échec. Il ne touche à aucun de tes
vrais éléments, et tes vraies données ne sont pas utilisées (dossier temporaire).

```zsh
cd ~/Assistant
.venv/bin/python -m pytest tests/demarrage/e2e_mac -q -s
.venv/bin/python tests/demarrage/e2e_mac/mesure_demon.py 600
```

Résultat attendu :
- `1 passed`, avec le temps du scan (moins de 15 s, puis moins de 5 s avec le cache) et « en tête :
  com.assistant.nettoyeur.test.charge … empêche la veille » ;
- `✅ dans les budgets` (processeur moyen sous 0,3 %, mémoire sous 40 Mo), suivi du détail par commande
  (`ps`, `launchctl list`, `pmset`, `top`…) : si le budget n'est pas tenu, ce détail dit pourquoi.

Colle-moi les deux sorties : elles vont dans RAPPORT_FINAL.md.

## 3. Allumer la surveillance et vérifier qu'elle se relance (2 minutes)

```zsh
cd ~/Assistant
.venv/bin/python demarrage.py surveiller on
.venv/bin/python service.py redemarrer
sleep 20
launchctl print gui/$(id -u)/com.assistant.superviseur | head -5
.venv/bin/python assistant.py etat | grep Démarrage
pkill -9 -f 'modules\.demarrage$'
sleep 70
.venv/bin/python assistant.py etat | grep Démarrage
.venv/bin/python demarrage.py doctor
```

Résultat attendu :
- `state = running` pour le superviseur ;
- deux fois une ligne « 🧹 Démarrage : surveille » : le module est relancé dans la minute après le `kill` ;
- doctor sans ❌.

Note : la surveillance n'a pas son propre LaunchAgent. C'est le superviseur de l'Assistant
(`com.assistant.superviseur`, avec RunAtLoad et KeepAlive) qui la lance et la relance (DECISIONS D-03).

## 4. Facultatif : l'autorisation « Automatisation » pour System Events

Sans les droits d'administrateur, macOS ne laisse pas lire la liste complète des éléments d'ouverture
(`sfltool dumpbtm`). Le Nettoyeur lit alors la liste « Ouvrir à la connexion » par System Events. La première fois,
macOS te demande : « Terminal (ou Python) souhaite contrôler System Events ». Réponds **OK**.

Si tu as refusé : Réglages Système → Confidentialité et sécurité → Automatisation → Terminal (ou Python) → coche
« System Events ».

Ce que ça débloque : la liste des apps qui s'ouvrent à ta connexion, et leur retrait par
`demarrage desactiver … --confirmer`.
Sans elle : le Nettoyeur les devine à partir des apps lancées juste après ton ouverture de session (dès que la
surveillance a vu une connexion), et il te donne le chemin dans les Réglages pour les retirer à la main.

## 5. Le diagnostic de ton Mac (12 minutes, sans rien désactiver)

```zsh
cd ~/Assistant
.venv/bin/python demarrage.py scan
.venv/bin/python demarrage.py mesurer --minutes 10
.venv/bin/python demarrage.py rapport
.venv/bin/python demarrage.py top
```

Le rapport s'ouvre dans ton navigateur. La dernière commande affiche le top 10 en texte, sans aucun chemin
personnel : colle-la-moi, et je l'ajoute à RAPPORT_FINAL.md.

Les vraies données d'ouverture de session (la courbe) viendront à ta prochaine connexion, si la surveillance est
allumée (§ 3).

## 6. Facultatif mais pratique : le raccourci « demarrage »

Le rapport et les messages écrivent `demarrage …`. Pour que ça marche tel quel, ajoute une fois ce raccourci
(le Nettoyeur ne touche jamais à tes fichiers zsh) :

```zsh
echo 'alias demarrage="$HOME/Assistant/.venv/bin/python $HOME/Assistant/demarrage.py"' >> ~/.zshrc
source ~/.zshrc
```

Sans lui : `cd ~/Assistant`, puis `.venv/bin/python demarrage.py …` (même suite).

## 7. Facultatif : capturer les vraies sorties de ton Mac pour les tests

Lecture seule. Les sorties sont anonymisées (ton nom de compte, ton nom, le nom du Mac, les e-mails disparaissent)
et restent sur ton Mac : le dossier n'est jamais envoyé sur GitHub.

```zsh
cd ~/Assistant
.venv/bin/python -m modules.demarrage.capturer
.venv/bin/python -m pytest tests/demarrage/unitaires/test_fixtures_reelles.py -q
```

Résultat attendu : `✅ … sortie(s) anonymisée(s)`, puis `passed`.

## 8. Les deux fichiers Google « sans Label » (2 minutes, lecture seule)

Le diagnostic a trouvé deux fichiers de lancement Google que launchd ne peut pas utiliser (« pas de Label »). Ils
ne lancent rien, mais je ne sais pas d'où ils viennent. Ces commandes ne font que lire : la première affiche, en
simulation, où est chaque fichier et la commande `plutil -p` qui montre son contenu.

```zsh
cd ~/Assistant
.venv/bin/python demarrage.py desactiver ebf8a226
.venv/bin/python demarrage.py desactiver 14140c57
```

Copie la ligne « Pour voir son contenu : plutil -p … » de chacun, lance-la, et colle-moi les sorties : je saurai
s'ils sont à ranger avec le 👻 Google Updater.

## 9. La mesure finale (10 minutes)

Elle mesure la surveillance après le dernier allègement (D-47) : processeur en moyenne sur une journée, et mémoire
maximale, scan quotidien compris.

```zsh
cd ~/Assistant
git pull
.venv/bin/python service.py redemarrer
.venv/bin/python tests/demarrage/e2e_mac/mesure_demon.py 600
```

Résultat attendu : « → moyenne sur une journée : … % » sous 0,3 %, une mémoire sous 40 Mo, puis
`✅ dans les budgets`. La ligne « fenêtre brute » donne le chiffre des 10 minutes, lancement compris.
