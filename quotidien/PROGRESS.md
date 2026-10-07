# Avancement — Quotidien

Reprise après coupure : lire ce fichier et `DECISIONS.md`, puis reprendre à la première phase non cochée.
Chaque phase se termine par `./check.sh` vert, l'intégrité identique, un commit.

| Phase | État | Commit |
|---|---|---|
| P0 — environnement, intégrité, squelette, check.sh, réseau | ✅ | « Quotidien P0 » |
| P1 — météo « habille-toi » | ✅ | « Quotidien P1 » |
| P2 — base de recettes | ✅ | « Quotidien P2 » |
| P3 — planificateur et courses | ✅ | « Quotidien P3-P4 » |
| P4 — vide-frigo | ✅ | « Quotidien P3-P4 » |
| P5 — anniversaires | ✅ | « Quotidien P5 » |
| P6 — brief, page, Rappels, iCloud, raccourcis | ✅ | « Quotidien P6-P7 » |
| P7 — démon, planification, doctor, budget IA | ✅ | « Quotidien P6-P7 » |
| P8 — bout en bout | ⏳ | |
| P9 — installation (script + vérification sur le Mac) | ⏳ | |
| P10 — revue hostile en deux passes | ⏳ | |

## P0 — 2026-10-07

- Empreinte « avant » prise **avant toute autre ligne** : `integrite/empreinte.py` puis
  `integrite/etat_avant.json` (dépôt hôte hors `quotidien/` : 593 fichiers, dont tout `bouclier/`).
- `quotidien/` : `pyproject.toml`, `.venv` (Python 3.11 ici), `config.py` (deux fichiers à toi, validés, valeurs par
  défaut), `db.py` (SQLite en 600, base corrompue mise de côté), `journal.py` (caviardé), `caviardage.py`,
  `reseau.py` (liste blanche : `api.anthropic.com`, `api.open-meteo.com`, `geocoding-api.open-meteo.com`).
- `tests/conftest.py` : maison imitée, réseau coupé et espionné (un hôte hors liste tenté fait échouer le test).
- `check.sh` : intégrité (début), ruff, mypy, pytest par groupes, couverture ≥ 90 %, intégrité (fin).

Preuve (`./check.sh`, extrait) :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 593 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 7 élément(s) divers, listes de Rappels : indisponibles)
All checks passed!
41 passed in 0.62s
25 passed in 0.27s
TOTAL                   421     22    95%
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 593 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 7 élément(s) divers, listes de Rappels : indisponibles)
CHECK OK
```

## P1 — 2026-10-07

- `meteo/open_meteo.py` : requête (hier + 3 jours, `unixtime`), lecture validée, cache 3 h, repli hors ligne signalé,
  géocodage. `meteo/trajets.py`, `meteo/regles.py` + `regles_tenue.toml`, `meteo/textes.py` (12 situations × 5–6
  modèles, phrases d'appoint × 5), `meteo/service.py` (ligne du brief, alerte de 21 h).
- Table de décision exhaustive : **3 936 cas** (−5 à 35 °C × 6 pluies × vent × UV × nuit × cours), **100 % conformes**
  à l'oracle écrit d'après la mission ; 300 journées aléatoires (hypothesis) sans aucun conseil contradictoire ;
  changement d'heure (23 h et 25 h) ; verglas (3 règles) ; bascule ; alerte (écart, pluie, tempête, orage, gel).
- Défauts trouvés et corrigés par les tests : variante « tram » sans le mot tram, lunettes un jour de neige, rappel
  d'éclairage perdu quand la ligne était pleine, verglas annoncé pour un gel sec (D-11, D-14, D-15).

Aperçu sur la fixture de janvier :

```
🌧️ 6 °C → 12 °C, averses entre 7h et 10h : imper ou poncho + sur-pantalon, pull + doudoune, gants à vélo, bonnet, tour de cou.
Dans le noir à l'aller comme au retour : allume ton éclairage, casque sur la tête. Retour au sec vers 18h30.
```

Preuve (`./check.sh`, extrait) :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 593 fichiers, …)
All checks passed!
41 passed · 77 passed (météo) · 25 passed (sécurité)
TOTAL                            1070     31    97%
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 593 fichiers, …)
CHECK OK
```

## P2 — 2026-10-07

- **228 recettes originales** (7 familles : française du quotidien, italienne, rapides, Asie, Méditerranée, Amériques
  et Afrique, saisons), 165 ingrédients (rayon, formats vendus, prix, allergènes, saison, conservation, synonymes),
  calendrier des saisons, 104 substitutions, 12 rayons. Générateur + vérificateur (`outils/construire_recettes.py`).
- Validation (`tests/repas/test_base_recettes.py`, 1 632 vérifications) : schéma strict, unités métriques, quantités
  par portion plausibles, allergènes égaux à ceux des ingrédients et conformes à une table d'attendus écrite à la main,
  régimes, sécurité (une étape dit quand c'est cuit), restes ≤ 3 jours, saisons justes, tutoiement.
- Couverture : 73 rapides (≥ 60), 117 végétariennes (≥ 50), de 81 à 170 recettes de saison selon le mois (≥ 40),
  53 plats « batch », 19 cuisines.
- Relecture de chef sur 20 recettes tirées au hasard : 8 corrections (D-24).

Preuve (`./check.sh`, extrait) :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 593 fichiers, …)
All checks passed!
41 passed · 77 passed (météo) · 1632 passed (recettes) · 25 passed (sécurité)
TOTAL                            1237     33    97%
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 593 fichiers, …)
CHECK OK
```

## P3 — 2026-10-07

- `repas/planificateur.py` : constructions au hasard puis amélioration locale. Contraintes dures : allergies, régime,
  aliments refusés, jours chargés (rapide ou restes), pas de répétition sur 14 jours, restes ≤ conservation,
  équipement. Cibles : budget ± 10 %, saison ≥ 70 %, chaînage anti-gaspi (alerte claire si impossible). Notes 👍/👎,
  envies, frigo, `remplacer`, `imposer` (vide-frigo → menu de ce soir).
- `repas/courses.py` : meilleur format vendu, frigo et placard déduits, « à congeler en rentrant », rayons, rien de
  perdu (chaque ingrédient du menu est dans la liste ou « déjà là »). `repas/envies.py` (local d'abord, IA si besoin),
  `repas/rappels_veille.py`, `repas/page.py` (Menu de la semaine.html), `repas/service.py`, `ia.py`, `systeme.py`.
- Commandes : `quotidien menu [--regenerer] [remplacer jeudi]`, `quotidien noter jeudi 👍`, `quotidien envie "…"`.
- Propriétés (hypothesis) : **1 200 profils aléatoires** et **150 séries de 4 semaines** : 0 violation d'allergie, de
  régime ou d'aliment refusé, 0 recette lente un jour chargé, 0 répétition sur 14 jours.
- Défauts trouvés et corrigés : « sans fromage » perdait sa négation (D-25), restes de la semaine suivante mal nommés
  (D-30).

Aperçu (menu par défaut, semaine du 5 octobre) :

```
🍽️ Menu de la semaine du lundi 5 octobre (14 € de repas, 100% de saison)
  lundi : Goulasch (140 min) — en faire plus pour jeudi soir
  mardi : Soupe turque aux lentilles corail (35 min)
  mercredi : Riz sauté au chou et à l'œuf (kimchi doux) (20 min)
  jeudi : restes de goulasch
  vendredi : Polenta crémeuse aux champignons (20 min)
  samedi : Soupe miso aux nouilles et au tofu (15 min)
  dimanche : Cake salé jambon-olives (60 min) — en faire plus pour mercredi soir de la semaine prochaine
🛒 Courses du lundi : 25 articles, ≈ 42.61 €
```

## P4 — 2026-10-07

- `frigo/analyse_texte.py` (local, 0 crédit) : pluriels, accents, fautes (Damerau-Levenshtein), quantités en chiffres
  ou en lettres, « une demi », « et demi », douzaines, unités, contenants, restes, absences (« plus de lait »).
- `frigo/correspondance.py` : score (D-31), au plus 2 manquants, substitutions, facultatifs, variété des protéines.
- `frigo/vision_ia.py` : image refaite à partir des pixels (1 024 px), métadonnées absentes vérifiées segment par
  segment, JSON validé, « à confirmer » sous 0,6, budget épuisé → « envoie-moi plutôt la liste en texte ».
- `frigo/service.py` : mémoire du frigo pour le planificateur, réponse courte (iPhone) ou longue, « ajouter au menu de
  ce soir », idée originale `--creatif` contrôlée (D-36). Commande `quotidien frigo "…" | photo.jpg | ce-soir N | vider`.
- **203 formulations : 100 %** normalisées (seuil 95 %). **60 frigos : 60/60** avec une recette pertinente dans le
  top 3 (seuil 95 %), **0 violation du profil** ; plus 300 frigos et profils aléatoires (hypothesis) sans violation.
- Photo : test avec une « photo d'iPhone » pleine de métadonnées (GPS, appareil, profil couleur, commentaire) : rien
  ne part. Test réel `reel` (image dessinée, < 0,02 $) prêt pour le Mac.

Aperçu :

```
$ quotidien frigo "2 courgettes, un reste de riz, feta, plus de lait, 6 oeufs" --court
🧊 J'ai compris : 2 courgettes, reste de riz long, feta, 6 œufs.
🚫 Plus de : lait demi-écrémé (retiré de ton frigo).
1. Poêlée de courgettes au chèvre et aux pâtes — 20 min · tu as tout
   👉 Pas de chèvre ? De la feta.
2. Riz sauté au chou et à l'œuf (kimchi doux) — 20 min · il manque : chou vert, carotte
3. Poivrons farcis au riz et à la feta — 50 min · il manque : tomate, oignon
```

Preuve (`./check.sh`, P3 et P4 ensemble) :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 593 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 7 élément(s) divers, listes de Rappels : indisponibles)
All checks passed!
54 passed (socle) · 77 passed (météo) · 1686 passed in 693.73s (recettes, menu, courses) · 43 passed (vide-frigo) · 25 passed (sécurité)
TOTAL                                3319     64    98%
INTÉGRITÉ OK : identique à etat_avant.json (…)
CHECK OK
```

## P5 — 2026-10-07

- `anniversaires/contacts.py` : Contacts du Mac en lecture seule (`CNContactStore`), accès demandé depuis le
  Terminal seulement ; `proches.py` : `proches.toml` (fiches, personnes hors Contacts), relié par prénom et nom ;
  `dates.py` : formats de date, 29 février (28/02 ou 01/03), âge, fuseau des réglages.
- `messages.py` : 3 variantes vérifiées (longueur, lignes, prénom, 40 formules interdites, pas de lien), IA avec
  seulement prénom, relation, ton, âge et notes caviardées ; modèles locaux par ton, avec l'âge et tes notes.
- `service.py` : rappels J-7 (proches), J-1, J, fenêtres d'utilité, une seule fois chacun, groupés, jamais la nuit ;
  le jour J, la fenêtre « Ouvrir dans Messages » (URL `sms:` + presse-papiers) ; fêtes en option.
- Commande `quotidien anniversaires [message|ouvrir Prénom N]`.
- Tests : Contacts imités (29 février, sans année, même jour, contact supprimé, année absurde), horloge simulée sur
  une semaine (J-7, J-1, J émis exactement une fois, redémarrage sans doublon, rattrapage utile seulement), espion de
  l'IA (0 nom de famille, 0 numéro, 0 adresse), 1 260 combinaisons ton × relation × âge × notes (3 780 messages) sans cliché ni mot
  genré, **aucune capacité d'envoi** (recherche dans tout le code livré, et preuve qu'elle trouverait chaque forme).

Aperçu (modèles locaux, sans IA) pour une amie proche, ton drôle, 25 ans, notes « voyage à Lisbonne », « foot » :

```
1. Bon anniversaire Camille !
   J'ai vérifié : aujourd'hui, tu as le droit de tout. Même au deuxième dessert.
   25 ans, un quart de siècle avec style.
2. Bon anniversaire Camille 🥳
   Aujourd'hui, interdiction de faire la vaisselle. C'est la loi, je n'y peux rien.
   Je repense encore à notre voyage à Lisbonne : on remet ça quand tu veux ?
3. Joyeux anniversaire Camille !
   Je t'aurais bien chanté la chanson, mais je tiens à notre amitié.
   J'espère qu'il y aura un peu de foot au programme aujourd'hui !
```

Preuve (`./check.sh`) :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 593 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 7 élément(s) divers, listes de Rappels : indisponibles)
All checks passed!
54 passed (socle) · 77 passed (météo) · 1686 passed in 726.05s (recettes) · 43 passed (vide-frigo) · 46 passed (anniversaires) · 29 passed (sécurité)
TOTAL                                 3920     70    98%
INTÉGRITÉ OK : identique à etat_avant.json (…)
CHECK OK
```

## P6-P7 — 2026-10-07

- `brief.py` : une ligne par brique (météo, repas du soir et ses restes, rappel de la veille, jour de courses,
  anniversaires), lignes vides omises, une brique en panne n'emporte rien ; page `Ma journée.html` (iCloud) et
  `brief.json` (pour l'assistant, INTEGRATION.md).
- `rappels_apple.py` : « Courses (menu) » et « Anniversaires » seulement, suffixe « (Quotidien) » en cas de nom pris,
  jamais un rappel en double, jamais une autre liste touchée ; désinstallation : nos listes seulement.
- `icloud.py` + `raccourcis/generer.py` : « Mon frigo » (photo, galerie, texte ou dictée) et « Envie de… », dépôt dans
  `Quotidien/entree/`, réponse en `Quotidien/reponses/<id>.txt`, 60 s d'attente, « Mac injoignable ».
- `planification.py`, `daemon.py`, `notifier.py` : tâches datées avec fenêtre d'utilité (D-46), rattrapage au
  réveil, silence 23 h – 7 h, réglages relus quand ils changent, brique en panne retentée.
- `doctor.py`, `installation.py`, `install.sh`, `uninstall.sh` (relançables, sans sudo, vérification « kill puis
  relance » et aller-retour iCloud), exemples `profil`, `reglages`, `proches`.
- Tests : le brief dans 12 combinaisons ; un faux Mac avec des listes d'autres projets (jamais touchées) ; le démon
  sur 5 jours d'horloge simulée (5 briefs à 7 h 15 exactement, 1 menu, 5 rappels de la veille, anniversaire J-1 et J
  une seule fois, 0 notification la nuit, rien de refait après un redémarrage, pas de brief à 15 h).

Aperçu (`quotidien brief`, ici sans réseau vers Open-Meteo) puis `quotidien doctor` (extrait) :

```
🌡️ Météo indisponible : pas de réseau et aucune prévision gardée. Regarde le ciel avant de partir.
🍽️ Ce soir : riz sauté au chou et à l'œuf (kimchi doux) (20 min).
🎂 Demain : anniversaire de Camille → message prêt.

✅ Menu                          semaine du 2026-10-05 (7 repas)
⚠️ Contacts                      Contacts indisponibles sur cette machine (pas un Mac ?) · proches.toml : 1 fiche(s)
✅ IA                            abonnement Claude · ce mois : 0.00 $ sur 2.00 $
✅ Tâche : brief du matin        prochaine : demain à 07:15
✅ Tâche : menu de la semaine    prochaine : dimanche 11 octobre à 17:00
```

Première passe de la revue hostile faite ici (6 corrections, D-53), avec README.md et `tests/e2e_mac`.

Preuve (`./check.sh`, après la première passe) :

```
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 593 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 7 élément(s) divers, listes de Rappels : indisponibles)
All checks passed!
55 passed (socle) · 77 passed (météo) · 1686 passed in 609.75s (recettes) · 44 passed (vide-frigo) · 46 passed (anniversaires) · 32 passed (brief, Rappels, iCloud, raccourcis) · 29 passed (sécurité) · 16 passed (bout en bout)
TOTAL                                 5027    111    98%
INTÉGRITÉ OK : identique à etat_avant.json (…)
CHECK OK
```
