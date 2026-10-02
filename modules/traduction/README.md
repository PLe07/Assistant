# 🇬🇧 La traduction au point

Allumée, elle transforme **chaque phrase française que tu finis par un point** en anglais, **là où tu écris**
(Mail, Notes, Pages, Word, la plupart des champs web…). Dans la plupart des applis, Cmd + Z rend le français.

| Quoi | Comment |
|---|---|
| Allumer / éteindre | icône → « 🇬🇧 Traduire mes phrases en anglais », ou `python assistant.py traduction on` / `off` |
| Première fois | `python -m modules.traduction --telecharger` (le modèle, ~100 Mo, une seule fois) |
| Essayer sans rien remplacer | `python -m modules.traduction --test` (tape dans Notes, regarde le Terminal) |
| Une phrase, ici | `python -m modules.traduction --texte "Je cherche une alternance en banque."` |
| Ça ne marche pas ? | `python -m modules.traduction --diagnostic` |

**Sur ton Mac, rien ne sort** : la traduction est faite par un modèle libre (Argos Translate) qui tourne sur le Mac,
en moins d'une seconde. Aucun appel à Claude, rien n'est envoyé ni gardé (ni touche, ni phrase) : le journal note
seulement « Phrase traduite (Mail) », et `etat` le nombre de phrases du jour.

**Ce qui n'est jamais traduit** : les phrases de moins de 3 mots (`mots_min` dans reglages.json), celles qui ne sont
pas en français, les nombres (« 3.5 »), les adresses (« www.site.fr »), les points de suspension, les champs de mot
de passe, et les applis exclues : les mêmes que les yeux (mots de passe, messageries, banques, impôts, santé,
navigation privée) + le Terminal. Ta liste en plus : `modules.traduction.applis_exclues` / `titres_exclus`.

**Si une appli ne laisse pas remplacer le texte** (Google Docs, certaines applis) : l'anglais est copié
(Cmd + V pour le coller) et une notification te le dit.

**Autorisations macOS** (demandées la première fois) : Réglages Système → Confidentialité et sécurité →
« **Surveillance de l'entrée** » (voir le point tapé) et « **Accessibilité** » (lire et remplacer la phrase) →
active « Python ». Puis éteins et rallume la traduction.

Quand elle est allumée, **🇬🇧 est dans l'icône**. La pause générale l'arrête aussi.
