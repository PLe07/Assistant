# Crédits

Bouclier réutilise des données publiques et des bibliothèques libres. Merci à leurs auteurs.

## Données embarquées

| Données | Source | Licence | Usage dans Bouclier |
|---|---|---|---|
| Liens et difficulté de suppression des comptes | [JustDeleteMe](https://github.com/jdm-contrib/jdm) (`_data/sites.json`), © 2013-2020 Robb Lewis, The JDM Contrib Team & contributeurs | MIT | `bouclier/comptes/services.json` (champs `suppression`, `difficulte`, `aide`) |
| Double authentification, catégories et pays des services | [2factorauth / twofactorauth](https://github.com/2factorauth/twofactorauth) (`entries/`), © 2021 2factorauth et contributeurs | MIT | `bouclier/comptes/services.json` (champs `double_auth`, `doc_double_auth`, catégorie) |

Versions utilisées : voir `_sources` en tête de `bouclier/comptes/services.json` (commits exacts). Pour mettre à jour :
`python outils/importer_bases.py <copie de jdm> <copie de twofactorauth>`.

Les deux licences MIT demandent de garder la mention de copyright et la licence : la voici.

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
> documentation files (the "Software"), to deal in the Software without restriction, including without limitation
> the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
> to permit persons to whom the Software is furnished to do so, subject to the following conditions: The above
> copyright notice and this permission notice shall be included in all copies or substantial portions of the
> Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.

## Services consultés (réseau)

- **Have I Been Pwned** (Troy Hunt) : liste publique des fuites, `https://haveibeenpwned.com/api/v3/breaches`,
  sous licence [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/). Attribution
  affichée dans le tableau de bord.
- **OpenPhish** (flux communautaire) et **URLhaus** (abuse.ch) : listes de liens piégés, téléchargées en entier.
- **rdap.org** : date de création des noms de domaine (seul le nom de domaine est envoyé).

## Bibliothèques

anthropic, pydantic, pikepdf, Pillow, pillow-heif, reportlab, watchdog, numpy, pyobjc (Vision) : voir
`pyproject.toml`.
