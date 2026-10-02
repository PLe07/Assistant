# 🇬🇧 La traduction au point

Allumée, elle transforme **chaque phrase française que tu finis par un point** en anglais, **là où tu écris**
(Mail, Notes, Pages, Word, la plupart des champs web…). Dans la plupart des applis, Cmd + Z rend le français.

| Quoi | Comment |
|---|---|
| Allumer / éteindre | icône → « 🇬🇧 Traduire mes phrases en anglais », ou `python assistant.py traduction on` / `off` |
| Première fois | `python -m modules.traduction --telecharger` (le grand modèle, ~1,3 Go, une seule fois) |
| Comparer les deux modèles | `python -m modules.traduction --comparer "La prof nous a rendu un contrôle."` |
| Essayer sans rien remplacer | `python -m modules.traduction --test` (tape dans Notes, regarde le Terminal ; si ça bloque, il affiche chaque étape avec la réponse de macOS) |
| Une phrase, ici | `python -m modules.traduction --texte "Je cherche une alternance en banque."` |
| Ça ne marche pas ? | `python -m modules.traduction --diagnostic` |

**Sur ton Mac, rien ne sort** : la traduction est faite par un modèle libre qui tourne sur le Mac. Le **grand**
(NLLB de Meta, ~1,3 Go) comprend le sens, en ~1 seconde par phrase ; le **petit** (Argos Translate, ~100 Mo)
répond en 0,1 s mais traduit presque mot à mot. Le grand sert s'il est là ; pour revenir au petit :
`"moteur": "argos"` dans reglages.json (modules → traduction), puis éteins et rallume 🇬🇧.
Aucun appel à Claude, rien n'est envoyé ni gardé (ni touche, ni phrase) : le journal note seulement
« Phrase traduite (Mail) », et `etat` le nombre de phrases du jour.

**Ce qui n'est jamais traduit** : les phrases de moins de 3 mots (`mots_min` dans reglages.json), celles qui ne sont
pas en français, les nombres (« 3.5 »), les adresses (« www.site.fr »), les points de suspension, les champs de mot
de passe, et les applis exclues : les mêmes que les yeux (mots de passe, messageries, banques, impôts, santé,
navigation privée) + le Terminal. Ta liste en plus : `modules.traduction.applis_exclues` / `titres_exclus`.

**Si une appli ne laisse pas remplacer le texte** (Google Docs, certaines applis) : l'anglais est copié
(Cmd + V pour le coller) et une notification te le dit.

**Pages et Keynote cachent leur texte à macOS** : on y passe par le clavier. Dès que tu t'arrêtes de taper
(⅓ de seconde), ton paragraphe est sélectionné et copié pour être lu (⌥⇧↑ puis ⌘C, tu le vois clignoter),
puis tes phrases sont sélectionnées (⇧←) et l'anglais collé à la place (⌘V). **Ton presse-papiers est remis
comme avant**, et si tu reprends la main pendant ce temps, rien n'est collé (l'anglais est copié, une
notification le dit). De toi, le clavier ne retient que l'heure de ta dernière touche et le nombre de phrases
finies, jamais les touches. Une autre appli dans ce cas : ajoute-la à `modules.traduction.applis_clavier`
dans reglages.json (seulement si ⌥⇧↑ y sélectionne bien jusqu'au début du paragraphe).

**Autorisations macOS** (demandées la première fois) : Réglages Système → Confidentialité et sécurité →
« **Surveillance de l'entrée** » (voir le point tapé) et « **Accessibilité** » (lire et remplacer la phrase) →
active « Python ». Puis éteins et rallume la traduction.

Quand elle est allumée, **🇬🇧 est dans l'icône**. La pause générale l'arrête aussi.
