# 📋 Fiche de L'ASSISTANT

Tout se fait **depuis l'icône** en haut à droite de l'écran (près de l'heure), ou **dans le Terminal**.
Pour le Terminal, ouvre-le et tape d'abord (une fois par fenêtre) :

```
cd ~/Assistant && source .venv/bin/activate
```

> `.venv` = la boîte où sont rangés les outils Python de l'Assistant ; `source …` l'ouvre pour cette fenêtre.

---

## 1. ▶️ Démarrer

| Quoi | Comment |
|---|---|
| Démarrer (et à chaque allumage du Mac) | `python service.py installer` |
| Vérifier que tout tourne | `python service.py etat` puis `python assistant.py etat` |
| Après une mise à jour (`git pull`) | `python service.py installer` (relance tout avec le nouveau code) |

> **launchd** = le planificateur intégré à macOS. `installer` lui confie deux programmes :
> le **superviseur** (il lance les modules et les relance s'ils tombent) et l'**icône**.
> Ils redémarrent tout seuls à chaque ouverture de session.

Ce que tu dois voir : `✅ superviseur : en marche` et `✅ icone : en marche`, puis l'icône 🟢 (ou 🎙 / 👁) en haut de l'écran.

---

## 2. ⏸ Mettre en pause

| Couper | Icône | Terminal | Effet |
|---|---|---|---|
| **Le micro** | « 🎙 Couper le micro » | `python assistant.py micro off` | le micro se ferme tout de suite ; 🎙 disparaît de l'icône |
| **L'écran** | « 👁 Couper l'écran » | `python assistant.py ecran off` | plus aucune capture ; 👁 disparaît de l'icône |
| **La traduction** 🇬🇧 | « 🇬🇧 Arrêter la traduction » | `python assistant.py traduction off` | plus rien n'est traduit ; 🇬🇧 disparaît de l'icône |
| **Tout** (interrupteur maître) | « ⏸ Tout mettre en pause » | `python assistant.py pause` | tout s'arrête : micro, écran, traduction, mails, aides ; l'icône affiche ⏸ |

Pour rallumer : le même bouton (« Rallumer… », « Reprendre », « 🇬🇧 Traduire mes phrases en anglais »), ou
`micro on`, `ecran on`, `traduction on`, `python assistant.py reprendre`.

> 🎙, 👁 et 🇬🇧 dans l'icône = le micro, l'écran ou la traduction sont **en marche en ce moment**.
> Pas de symbole = rien n'écoute, rien ne regarde, rien n'est traduit.

---

## 3. 📜 Voir les logs (le journal)

| Quoi | Comment |
|---|---|
| Les 30 dernières lignes | `python assistant.py journal` (ou icône → « Ouvrir le journal ») |
| Seulement un module | `grep "\[yeux\]" logs/assistant.log \| tail -20` (remplace `yeux` par `mails`, `oreilles`…) |
| Seulement les erreurs | `grep -E "ERROR\|Plantage" logs/assistant.log \| tail -20` |
| Le résumé du jour | `python assistant.py etat` (modules, notifications, appels à Claude) |

> Le **journal** (`logs/assistant.log`) note ce que fait l'Assistant (« Déclencheur », « Aide rédigée »…),
> **jamais** ce qu'il entend, ce qu'il voit, ni le texte de tes mails.

---

## 4. 🎛 Activer / désactiver un module · régler la proactivité

| Quoi | Comment |
|---|---|
| Activer un module | `python assistant.py activer yeux` |
| Le désactiver | `python assistant.py desactiver yeux` |
| Voir lesquels sont actifs | `python assistant.py etat` (rubriques « Modules » et « Au bouton ») |
| Régler la proactivité | icône → « 🔔 Proactivité » , ou `python assistant.py proactivite 2` |

**Les modules**

| En fond (tournent tout seuls) | Au bouton (seulement quand tu les demandes) |
|---|---|
| `mails` · tri de ta boîte toutes les 3 min | `coach` · 🎓 révisions DCG |
| `oreilles` · le micro et le mot « Assistant » | `veille` · 📰 patrimoine + DCG |
| `yeux` · l'écran, quand tu bloques | `recherche` · 🌐 recherche sourcée |
| `depenses` · surveille le dossier ~/Reçus | `redacteur` · ✒️ dans ton style |
| `battement` · prouve que tout tourne | `brief` · ☀️ ton brief |
| `traduction` · 🇬🇧 tes phrases en anglais (au point) | `cine` · 🎬 je regarde quoi ce soir |
| | `revue` · 🗓 la revue de la semaine |

Un module « au bouton » désactivé ne fait plus rien : son bouton, sa commande et la voix répondent
« … est désactivé » avec la commande pour le réactiver. (Pour `depenses`, désactiver arrête seulement
la surveillance du dossier : le bouton « Ajouter un reçu » reste.)

**La proactivité** (ce que l'Assistant ose faire de lui-même, sans que tu demandes) :

| Niveau | Nom | Il te propose une aide 💡 si… | Notifications par heure |
|---|---|---|---|
| 0 | muet | jamais (il ne prend aucune initiative) | 0 (sauf alertes) |
| 1 | discret | Claude est sûr à 90 % et plus | 1 |
| 2 | normal (réglage actuel) | sûr à 80 % et plus | 3 |
| 3 | présent | sûr à 70 % et plus | 6 |

Quand **tu** demandes (bouton, « Assistant, … », commande), il répond toujours, quel que soit le niveau.

> Tout cela est écrit dans **`reglages.json`** (le fichier des réglages, à la racine de ~/Assistant) :
> `"niveau_proactivite": 2` et, pour chaque module, `"modules": {"cine": {"actif": true}, …}`.
> Tu peux aussi le modifier à la main (TextEdit) : c'est relu toutes les 2 secondes ;
> une valeur fausse est signalée dans le journal et remplacée par la valeur par défaut.

---

## 5. ➕ Ajouter un module

**Un module en fond** (il tourne tout seul, le superviseur le surveille) :

1. Crée `modules/monmodule.py` sur le modèle de `modules/battement.py` (le plus simple) :

   ```python
   from core.module import executer

   def boucle(ctx):
       while not ctx.attendre(60):          # toutes les 60 s, jusqu'à l'arrêt
           ctx.log.info("Je travaille")      # → logs/assistant.log
           # ctx.notifier(...), ctx.demander_a_claude(...), ctx.reglage("cle")

   if __name__ == "__main__":
       executer("monmodule", boucle)
   ```

2. Active-le : `python assistant.py activer monmodule` (il démarre dans les 2 secondes).
3. Vérifie : `python assistant.py etat` puis `python assistant.py journal`.

S'il plante, le superviseur le relance tout seul (après 1 min) et l'icône affiche ⚠️ :
la cause est dans le journal (`grep -A20 Plantage logs/assistant.log`).

**Un module au bouton** (comme le ciné) : c'est plus long (bouton dans l'icône, commande, tests) :
demande-le à Claude en décrivant ce que tu veux ; il suivra la même méthode (plan → ton ok → code → tests → essai réel).

---

## 6. ⏹ Tout arrêter

| Quoi | Comment | Tes données |
|---|---|---|
| Pause (reprise en 1 clic) | icône → « ⏸ Tout mettre en pause » | intactes |
| Arrêter pour de bon (plus de démarrage automatique) | `python service.py desinstaller` | intactes |
| Le remettre plus tard | `python service.py installer` | — |
| Juste fermer l'icône (l'Assistant continue) | icône → « Quitter l'icône » | intactes |

`desinstaller` arrête le superviseur, tous les modules et l'icône, et les retire de launchd.
**Rien n'est effacé** : ni tes mails, ni ta mémoire (`donnees/`), ni tes réglages.

---

## 🆘 En cas de souci

| Ce que tu vois | Quoi faire |
|---|---|
| ⚠️ dans l'icône | `python assistant.py etat` dit quel module et pourquoi |
| Un module « relance » en boucle | `grep -A20 Plantage logs/assistant.log \| tail -40` et colle-le à Claude |
| Pas de notification | `python assistant.py test-notif` (il dit quoi régler dans macOS) |
| Claude ne répond plus | `python assistant.py test-claude` ; jeton expiré : `python assistant.py renouveler-jeton` |
| Micro muet / écran non autorisé | Réglages Système → Confidentialité et sécurité → Micro / Enregistrement de l'écran → « Python » |

Toutes les commandes : `python assistant.py --help` · Le détail de chaque module : `modules/<nom>/README.md`.
