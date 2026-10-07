# Rapport final — Quotidien

Construit et vérifié dans un conteneur Linux ; tout ce qui demande ton Mac (launchd, Contacts, Rappels, iCloud,
signature des raccourcis, IA réelle) est fait par `./install.sh` et `tests/e2e_mac`, qui affichent leurs propres
preuves (ACTIONS_HUMAINES.md, étapes 1 et 4).

## Définition de « terminé » (§12)

| | Critère | État | Preuve |
|---|---|---|---|
| ✅ | Intégrité des autres projets identique | ici : à chaque `check.sh` (début et fin) ; **sur ton Mac** : `install.sh` compare avant/après (agents `com.<session>.*`, Docker, listes de Rappels tierces) | §1 |
| ✅ | `check.sh` vert, 0 violation d'allergie (propriétés) | 1 200 profils + 150 × 4 semaines (planificateur), 300 frigos × profils (vide-frigo) : 0 violation | §2 |
| ✅ | 0 capacité d'envoi, liste blanche respectée | recherche automatique dans tout le code livré ; réseau coupé et espionné dans chaque test | §3 |
| ⏳ | Premier brief et premier menu réels | générés par `install.sh` (étape 7) ; aperçus ici, §4 | §4 |
| ⏳ | Démon actif, relancé après un `kill`, `doctor` clair | `install.sh` (étape 8) le vérifie et l'affiche ; testé ici avec un faux launchd | §5 |
| ✅ | README en français | brief, trajets, goûts, budget, vide-frigo iPhone, noter, anniversaires, désinstaller | README.md |
| ✅ | ACTIONS_HUMAINES.md : l'indispensable | installer, ajouter 2 raccourcis, accepter les accès ; le reste facultatif | ACTIONS_HUMAINES.md |

## 1. Les autres projets n'ont pas bougé

```
$ ./check.sh   (début et fin)
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 593 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 7 élément(s) divers, listes de Rappels : indisponibles)
```

L'empreinte « avant » a été prise en P0, avant toute ligne de Quotidien : le dépôt hôte hors `quotidien/` (dont
tout `bouclier/`, l'assistant, Corvées, le Trieur…). Aucun fichier hors `quotidien/` n'a été modifié depuis
(`git diff --stat` hors `quotidien/` : vide). Sur ton Mac, `install.sh` prend l'empreinte des agents
`com.<session>.*` des autres projets, de Docker et de tes listes de Rappels (noms et nombres) et la compare à la fin.

## 2. Allergies, régime, menus, courses, vide-frigo

- Planificateur : 1 200 profils aléatoires et 150 séries de 4 semaines (hypothesis) : 0 violation d'allergie, de
  régime ou d'aliment refusé ; 0 recette lente un jour chargé ; 0 répétition sur 14 jours ; budget ± 10 % ou alerte.
- Base : 228 recettes originales (73 rapides, 117 végétariennes, 81 à 170 de saison selon le mois), allergènes
  recalculés depuis la table des ingrédients, sécurité alimentaire vérifiée, relecture de chef (8 corrections).
- Courses : additions et conversions exactes, frigo et placard déduits, format vendu, aucun ingrédient perdu.
- Vide-frigo : 203 formulations (100 %), 60 frigos (60/60 avec une recette pertinente dans le top 3), 0 violation.

## 3. Rien ne part sans toi

- Aucune capacité d'envoi : `tests/securite/test_aucun_envoi.py` cherche `send`, `smtplib`, un `osascript` vers
  Messages, l'action d'envoi des Raccourcis dans tout le code livré (et prouve qu'il trouverait chacun) : 0 trouvé.
  Le seul chemin vers Messages : ouvrir `sms:…&body=…` (texte prérempli) ; c'est toi qui appuies sur Envoyer.
- Contacts en lecture seule (0 requête d'écriture dans le code) ; Rappels : nos 2 listes seulement.
- IA : prénom, relation, ton, âge, notes caviardées — espion : 0 nom de famille, 0 numéro, 0 adresse ; photo :
  0 métadonnée (GPS, appareil, profil couleur, commentaire) ; plafond de 2 $ par mois pour tout le pack.
- Réseau : `api.anthropic.com`, `api.open-meteo.com`, `geocoding-api.open-meteo.com`, rien d'autre.

## 4. Premier brief et premier menu

Générés pour de vrai par `install.sh` sur ton Mac. Aperçu ici (sans réseau vers Open-Meteo) :

```
🌡️ Météo indisponible : pas de réseau et aucune prévision gardée. Regarde le ciel avant de partir.
🍽️ Ce soir : riz sauté au chou et à l'œuf (kimchi doux) (20 min).
🎂 Demain : anniversaire de Camille → message prêt.
```

## 5. Le démon

LaunchAgent `com.<ta session>.quotidien` (RunAtLoad, KeepAlive, ThrottleInterval 30 s). Testé ici sur 5 jours
d'horloge simulée ; sur ton Mac, `install.sh` vérifie `launchctl print`, envoie un `kill`, attend la relance par
launchd et fait un aller-retour de vide-frigo par iCloud, puis affiche `quotidien doctor`.

## 6. Revue hostile (deux passes)

Relu comme quelqu'un qui veut le casser : une allergie violée, un message envoyé sans toi, un conseil météo absurde,
une liste de courses fausse, un double brief, une liste de Rappels d'un autre projet touchée, un effet sur les
autres projets.

Pendant la construction, les tests ont déjà trouvé et fait corriger : « sans fromage » qui perdait sa négation
(D-25), « plus de lait » compté comme présent (D-33), des restes de la semaine suivante mal nommés (D-30), le menu du
dimanche qui visait la mauvaise semaine selon le fuseau du Mac (D-47), des mots genrés dans les messages (D-40), un
réglage mal orthographié ignoré en silence (D-37).

**Première passe — 6 corrections (D-53)** : la liste de courses de Rappels ne suivait pas un menu régénéré ou un plat
remplacé ; une liste à nous supprimée à la main n'était plus remplie ; les rappels d'anniversaire passés
s'accumulaient ; le message mis dans Rappels n'utilisait pas le trousseau ; le démon ouvrait la base toutes les 3 s
pour rien ; une image piégée faisait planter `quotidien frigo photo.jpg`.

**Deuxième passe — 1 correction (D-54)** : l'accès aux Contacts accordé au Terminal pendant l'installation ne vaut
pas pour le démon lancé par launchd (macOS l'accorde programme par programme) : le démon serait resté en mode
dégradé sans le dire. Il demande maintenant l'accès lui-même, une seule fois, et ACTIONS_HUMAINES.md le dit.

Vérifié et rien trouvé : aucune allergie violée (propriétés), aucun envoi possible (recherche dans le code),
aucune autre liste de Rappels touchée (toutes les commandes envoyées au faux Mac sont inspectées), pas de double
brief (une échéance notée une fois, redémarrage compris), pas de brief à 15 h, pas de notification la nuit, aucun
fichier hors de `quotidien/` modifié.

## 7. Le dernier `check.sh`

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 593 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 7 élément(s) divers, listes de Rappels : indisponibles)
All checks passed!
55 passed (socle) · 77 passed (météo) · 1686 passed in 595.31s (recettes, menu, courses) · 44 passed (vide-frigo) · 46 passed (anniversaires) · 32 passed (brief, Rappels, iCloud, raccourcis) · 29 passed (sécurité) · 17 passed (bout en bout)
TOTAL                                 5030    110    98%
INTÉGRITÉ OK : identique à etat_avant.json (…)
CHECK OK

$ git diff --stat 46e10c0 HEAD -- . ':!quotidien'
(rien : 0 fichier modifié hors de quotidien/)
```
