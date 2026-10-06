# Avancement — Bouclier

Reprise après coupure : lire ce fichier et DECISIONS.md, puis reprendre à la première phase non cochée.

| Phase | État | Preuve |
|---|---|---|
| P0 Environnement, intégrité, squelette, check.sh, liste blanche | ✅ | ci-dessous |
| P1 Corpus d'arnaques | ✅ | 225 + 80 messages, ci-dessous |
| P2 Analyse locale n°20 | ⏳ | |
| P3 IA, caviardage, veto, budget, réflexes | ⏳ | |
| P4 Inventaire n°18 | ⏳ | |
| P5 Fuites n°19 | ⏳ | |
| P6 Métadonnées n°21 | ⏳ | |
| P7 Fiche urgence n°22 | ⏳ | |
| P8 Raccourcis, actions rapides, iCloud | ⏳ | |
| P9 Démon, tableau de bord, doctor, bout en bout | ⏳ | |
| P10 Installation réelle | ⏳ | |
| P11 Revue hostile (2 passes) | ⏳ | |

## P0 — Environnement, empreinte, squelette (✅)

- Empreinte « avant » prise **avant la première ligne de Bouclier** : `integrite/etat_avant.json`
  (455 fichiers du dépôt hors `bouclier/`, arbre git hors `bouclier/`, `.zshrc`, liste de `BoiteMac/`…).
- `integrite/verifier.sh` au début et à la fin de `check.sh`.
- Liste blanche du réseau (`bouclier/reseau.py`) et filet de test qui coupe et espionne le réseau (`tests/conftest.py`).
- Fondations : réglages, caviardage, base SQLite (600, base abîmée mise de côté), journal caviardé,
  notifications (3 par jour, silence 23 h – 8 h), interface du Mac.

```
$ ./check.sh
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (début)
  ✅ ruff check
  ✅ ruff format
  ✅ mypy
  ✅ pytest : unitaires et intégrité
  ✅ sécurité, réseau, vie privée
TOTAL                      574     24    96%
  ✅ couverture ≥ 90 % sur bouclier/
INTÉGRITÉ OK : identique à etat_avant.json (1 projet(s), 455 fichiers, 0 LaunchAgent(s), 0 réglage(s) Application Support, 5 élément(s) divers)
  ✅ intégrité des autres projets (fin)
CHECK OK
```

## P1 — Corpus d'arnaques (✅)

- `tests/corpus_arnaques/generer.py` : 225 messages dans le corpus principal (135 arnaques des 14 familles, 10
  injections, 80 légitimes dont des pièges), 80 dans le 2e corpus (48 arnaques, 32 légitimes) écrit **avant** les
  règles, avec des marques et des domaines absents du premier et de la liste des marques.
- SMS en texte, mails complets (en-têtes, Authentication-Results, Reply-To, désinscription, texte + HTML, base64,
  quoted-printable, ISO-8859-1). Variantes : fautes, émojis, raccourcisseurs, punycode, sosies, faux en-têtes.
- Contexte imité déterministe : RDAP (4/10 récents, 3/10 inconnus, 3/10 anciens), flux (1 lien piégé sur 5),
  inventaire (cliente de La Banque Postale et de Boursobank).

```
$ ./check.sh   (extrait)
  ✅ corpus d'arnaques (principal + 2e corpus inédit)
CHECK OK
```
