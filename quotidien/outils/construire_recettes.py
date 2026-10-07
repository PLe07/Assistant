"""Construit la base de recettes de Quotidien à partir des sources écrites à la main (`outils/sources/`).

    python outils/construire_recettes.py          (écrit quotidien/repas/*.json et recettes/*.json)
    python outils/construire_recettes.py --verifier (échoue si les JSON ne correspondent pas aux sources)

Toutes les recettes sont originales, écrites pour Quotidien (aucun texte copié d'un site, CREDITS.md).
Le générateur refuse une recette mal formée (ingrédient inconnu, unité fausse, temps absurde, étape manquante) et
calcule ce qui doit l'être pour ne jamais être faux à la main : allergènes (depuis la table des ingrédients), régimes,
saisons, coût estimé, étiquettes « rapide », « four », « végétarien »…, mentions de sécurité alimentaire et
conservation des restes (3 jours au réfrigérateur au plus).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ICI = Path(__file__).resolve().parent
SOURCES = ICI / "sources"
SORTIE = ICI.parent / "quotidien" / "repas"

ALLERGENES = ("gluten", "crustaces", "oeufs", "poissons", "arachides", "soja", "lait", "fruits_a_coque", "celeri",
              "moutarde", "sesame", "sulfites", "lupin", "mollusques")  # fmt: skip
CATEGORIES_VIANDE = {"volaille", "boeuf", "porc", "agneau", "charcuterie"}
CATEGORIES_MER = {"poisson", "crustace", "mollusque"}
CATEGORIES_ANIMALES = {"oeuf", "laitier", "fromage"}
CATEGORIES_PRODUITS = {"legume", "fruit", "allium", "herbe", "condiment"}  # ceux qui peuvent avoir une saison
CATEGORIES = CATEGORIES_VIANDE | CATEGORIES_MER | CATEGORIES_ANIMALES | CATEGORIES_PRODUITS | {
    "tofu", "legumineuse", "feculent", "pain", "pate", "conserve", "sauce", "huile", "sucre", "epice", "noix",
    "graine", "fruit_sec", "surgele",
}  # fmt: skip
DIFFICULTES = ("facile", "moyen", "avance")
CUISINES = ("francaise", "italienne", "espagnole", "portugaise", "grecque", "turque", "libanaise", "marocaine",
            "tunisienne", "africaine", "antillaise", "reunionnaise", "indienne", "thai", "vietnamienne", "chinoise",
            "japonaise", "coreenne", "mexicaine", "americaine", "anglaise", "suisse", "belge", "hongroise")  # fmt: skip
PROTEINES = ("volaille", "boeuf", "porc", "agneau", "poisson", "fruits_de_mer", "oeuf", "fromage", "legumineuse",
             "tofu", "aucune")  # fmt: skip
FECULENTS = ("pates", "riz", "pomme_de_terre", "semoule", "boulgour", "quinoa", "polenta", "pain", "nouilles",
             "tortilla", "pate", "legumineuse", "aucun")  # fmt: skip
ETIQUETTES_MANUELLES = ("batch", "leger", "reconfortant", "epice", "soupe", "salade", "froid", "airfryer_possible",
                        "plat_unique", "transportable", "gratin", "tarte", "sucre_sale")  # fmt: skip
USTENSILES_EQUIPEMENT = {"four": "four", "mixeur": "mixeur", "micro-ondes": "micro-ondes"}
MOIS = range(1, 13)


class ErreurSource(Exception):
    pass


# --- Lecture des tables -------------------------------------------------------------------------------------------


def _lignes(chemin: Path) -> list[tuple[int, str]]:
    sortie = []
    for n, ligne in enumerate(chemin.read_text(encoding="utf-8").splitlines(), 1):
        brute = ligne.lstrip()
        if brute and (not brute.startswith("#") or brute.startswith("## ")):
            sortie.append((n, ligne))
    return sortie


def lire_rayons() -> dict[str, dict[str, Any]]:
    rayons = {}
    for _, ligne in _lignes(SOURCES / "rayons.txt"):
        id_, nom, emoji, ordre = (x.strip() for x in ligne.split("|"))
        rayons[id_] = {"nom": nom, "emoji": emoji, "ordre": int(ordre)}
    return rayons


def _mois(texte: str) -> list[int] | str | None:
    texte = texte.strip()
    if texte == "-":
        return None
    if texte == "imp":
        return "imp"
    mois: set[int] = set()
    for plage in texte.split(","):
        a, _, b = plage.strip().partition("-")
        debut, fin = int(a), int(b or a)
        m = debut
        while True:
            mois.add(m)
            if m == fin:
                break
            m = m % 12 + 1
    return sorted(mois)


def _formats(texte: str, unite: str, ou: str) -> list[dict[str, Any]]:
    formats = []
    # Les libellés peuvent contenir une virgule (« sac de 2,5 kg ») : on coupe seulement devant un nouveau format.
    for morceau in re.split(r",\s*(?=\d+(?:\.\d+)?(?:g|ml|p)@)", texte):
        morceau = morceau.strip()
        m = re.fullmatch(r"(\d+(?:\.\d+)?)(g|ml|p)@(\d+(?:\.\d+)?)(?:=(.+))?", morceau)
        if not m:
            raise ErreurSource(f"{ou} : format vendu illisible « {morceau} »")
        q, u, prix, libelle = float(m[1]), m[2], float(m[3]), (m[4] or "").strip()
        if u != unite:
            raise ErreurSource(f"{ou} : format en {u} pour un ingrédient compté en {unite}")
        formats.append({"quantite": q, "prix": prix, "libelle": libelle})
    return formats


def lire_ingredients(rayons: dict[str, Any]) -> dict[str, dict[str, Any]]:
    ingredients: dict[str, dict[str, Any]] = {}
    for n, ligne in _lignes(SOURCES / "ingredients.txt"):
        champs = [x.strip() for x in ligne.split("|")]
        ou = f"ingredients.txt:{n}"
        if len(champs) != 12:
            raise ErreurSource(f"{ou} : 12 champs attendus, {len(champs)} trouvés")
        id_, nom, pluriel, rayon, unite, formats, allerg, categorie, saison, jours, options, synonymes = champs
        if id_ in ingredients:
            raise ErreurSource(f"{ou} : identifiant en double « {id_} »")
        if rayon not in rayons:
            raise ErreurSource(f"{ou} : rayon inconnu « {rayon} »")
        if unite not in ("g", "ml", "p"):
            raise ErreurSource(f"{ou} : unité « {unite} » (g, ml ou p)")
        if categorie not in CATEGORIES:
            raise ErreurSource(f"{ou} : catégorie inconnue « {categorie} »")
        liste_allerg = [] if allerg == "-" else [a.strip() for a in allerg.split(",")]
        for a in liste_allerg:
            if a not in ALLERGENES:
                raise ErreurSource(f"{ou} : allergène inconnu « {a} »")
        opts: dict[str, Any] = {}
        for o in options.split():
            cle, _, valeur = o.partition("=")
            opts[cle] = valeur or True
        poids = None
        if "p" in opts:
            poids = float(str(opts.pop("p")).removesuffix("g"))
        saisons = _mois(saison)
        if saisons is not None and categorie not in CATEGORIES_PRODUITS:
            raise ErreurSource(f"{ou} : une saison pour un « {categorie} »")
        ingredients[id_] = {
            "id": id_,
            "nom": nom,
            "pluriel": pluriel,
            "rayon": rayon,
            "unite": unite,
            "poids_piece_g": poids,
            "formats": _formats(formats, unite, ou),
            "allergenes": liste_allerg,
            "categorie": categorie,
            "saison": saisons,
            "compte_saison": saisons is not None and not opts.get("sans_saison"),
            "conservation_jours": int(jours),
            "placard": bool(opts.get("placard")),
            "congeler": bool(opts.get("congeler")),
            "hache": bool(opts.get("hache")),
            "trempage_heures": int(opts["trempage"]) if "trempage" in opts else 0,
            "vegetarien": categorie not in CATEGORIES_VIANDE | CATEGORIES_MER and not opts.get("non_vege"),
            "vegan": categorie not in CATEGORIES_VIANDE | CATEGORIES_MER | CATEGORIES_ANIMALES
            and not opts.get("non_vege")
            and not opts.get("animal"),
            "pescetarien": categorie not in CATEGORIES_VIANDE,
            "porc": categorie in ("porc", "charcuterie"),
            "synonymes": [s.strip().lower() for s in synonymes.split(",") if s.strip()],
        }
        inconnues = set(opts) - {"placard", "congeler", "hache", "trempage", "sans_saison", "non_vege", "animal"}
        if inconnues:
            raise ErreurSource(f"{ou} : option(s) inconnue(s) {sorted(inconnues)}")
    return ingredients


def prix_unitaire(ing: dict[str, Any]) -> float:
    """Le prix le plus bas par unité de base (le plus grand format, souvent)."""
    return min(f["prix"] / f["quantite"] for f in ing["formats"])


# --- Recettes ---------------------------------------------------------------------------------------------------------

ENTETE = re.compile(r"^([a-z_]+)\s*:\s*(.+)$")


def _entete(ligne: str, ou: str) -> dict[str, str]:
    champs = {}
    for morceau in ligne.split("·"):
        m = ENTETE.match(morceau.strip())
        if not m:
            raise ErreurSource(f"{ou} : en-tête illisible « {morceau.strip()} »")
        champs[m[1]] = m[2].strip()
    return champs


def lire_recettes(ingredients: dict[str, Any]) -> list[dict[str, Any]]:
    recettes: list[dict[str, Any]] = []
    for fichier in sorted((SOURCES / "recettes").glob("*.txt")):
        courante: dict[str, Any] | None = None
        for n, ligne in _lignes(fichier):
            ou = f"{fichier.name}:{n}"
            l = ligne.strip()  # noqa: E741
            if l.startswith("## "):
                if courante:
                    recettes.append(courante)
                courante = {"nom": l[3:].strip(), "_ou": ou, "_fichier": fichier.stem, "ingredients": [],
                            "etapes": [], "etiquettes": [], "ustensiles": []}  # fmt: skip
                continue
            if courante is None:
                raise ErreurSource(f"{ou} : ligne hors recette")
            if l.startswith("- "):
                m = re.fullmatch(r"- (\d+(?:[.,]\d+)?)\s*(g|ml)?\s+([a-z_]+)(?:\s*:\s*(.+))?", l)
                if not m:
                    raise ErreurSource(f"{ou} : ingrédient illisible « {l} »")
                q, u, id_, note = float(m[1].replace(",", ".")), m[2] or "p", m[3], (m[4] or "").strip()
                if id_ not in ingredients:
                    raise ErreurSource(f"{ou} : ingrédient inconnu « {id_} »")
                if ingredients[id_]["unite"] != u:
                    raise ErreurSource(f"{ou} : « {id_} » se compte en {ingredients[id_]['unite']}, pas en {u}")
                courante["ingredients"].append({"id": id_, "quantite": q, "unite": u, "note": note})
            elif l.startswith("> "):
                courante["etapes"].append(l[2:].strip())
            elif l.startswith("tags:"):
                courante["etiquettes"] = [t.strip() for t in l[5:].split(",") if t.strip()]
            elif l.startswith("ustensiles:"):
                courante["ustensiles"] = [t.strip() for t in l[11:].split(",") if t.strip()]
            else:
                courante.update(_entete(l, ou))
        if courante:
            recettes.append(courante)
    return [_completer(r, ingredients) for r in recettes]


SECURITE = {
    "volaille": "Cuis la volaille à cœur : plus aucune trace rosée, jus clair (74 °C au centre).",
    "porc": "Cuis le porc à cœur : plus de rose au centre (70 °C).",
    "hache": "Cuis la viande hachée à cœur : plus de rose au centre (70 °C).",
    "poisson": "Le poisson est cuit quand sa chair devient opaque et se détache en lamelles.",
    "moules": "Jette les moules ouvertes avant cuisson et celles restées fermées après.",
    "crevette": "Crevettes surgelées : décongèle-les au réfrigérateur, jamais à température ambiante, et mange-les "
    "dans la journée.",
    "riz": "Riz cuit : refroidis-le vite et garde-le 24 h au frigo au plus.",
    "trempage": "Fais tremper les légumineuses sèches 12 h, puis jette l'eau de trempage avant cuisson.",
    "oeuf_cru": "Œufs : cuis-les jusqu'à ce que le blanc soit pris.",
}


def _completer(r: dict[str, Any], ingredients: dict[str, Any]) -> dict[str, Any]:
    ou = r.pop("_ou")
    fichier = r.pop("_fichier")
    for cle in ("id", "portions", "prep", "cuisson", "difficulte", "cuisine", "proteine", "feculent", "restes"):
        if cle not in r:
            raise ErreurSource(f"{ou} « {r['nom']} » : « {cle} » manquant")
    try:
        portions, prep, cuisson, restes = int(r["portions"]), int(r["prep"]), int(r["cuisson"]), int(r["restes"])
    except ValueError as e:
        raise ErreurSource(f"{ou} « {r['nom']} » : nombre illisible ({e})") from e
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", r["id"]):
        raise ErreurSource(f"{ou} : identifiant « {r['id']} » (minuscules et tirets)")
    if r["difficulte"] not in DIFFICULTES or r["cuisine"] not in CUISINES or r["proteine"] not in PROTEINES:
        raise ErreurSource(f"{ou} « {r['nom']} » : difficulté, cuisine ou protéine inconnue")
    if r["feculent"] not in FECULENTS:
        raise ErreurSource(f"{ou} « {r['nom']} » : féculent inconnu « {r['feculent']} »")
    if not 1 <= portions <= 8 or not 0 <= prep <= 60 or not 0 <= cuisson <= 240 or prep + cuisson < 5:
        raise ErreurSource(f"{ou} « {r['nom']} » : portions ou temps invraisemblables")
    if not 0 <= restes <= 3:
        raise ErreurSource(f"{ou} « {r['nom']} » : restes de 0 à 3 jours")
    if len(r["etapes"]) < 2 or len(r["ingredients"]) < 2:
        raise ErreurSource(f"{ou} « {r['nom']} » : au moins 2 ingrédients et 2 étapes")
    for t in r["etiquettes"]:
        if t not in ETIQUETTES_MANUELLES:
            raise ErreurSource(f"{ou} « {r['nom']} » : étiquette inconnue « {t} »")
    ids = [i["id"] for i in r["ingredients"]]
    if len(ids) != len(set(ids)):
        raise ErreurSource(f"{ou} « {r['nom']} » : ingrédient en double")
    ings = [ingredients[i] for i in ids]

    allergenes = sorted({a for i in ings for a in i["allergenes"]}, key=ALLERGENES.index)
    vegetarien = all(i["vegetarien"] for i in ings)
    vegan = all(i["vegan"] for i in ings)
    pescetarien = all(i["pescetarien"] for i in ings)
    sans_porc = not any(i["porc"] for i in ings)

    # Saisons : les mois où chaque fruit ou légume qui compte est de saison (un produit importé : jamais).
    comptes = [i for i in ings if i["compte_saison"]]
    mois = set(MOIS)
    for i in comptes:
        mois &= set() if i["saison"] == "imp" else set(i["saison"])
    cout = sum(q["quantite"] * prix_unitaire(ingredients[q["id"]]) for q in r["ingredients"])

    etiquettes = list(r["etiquettes"])
    total = prep + cuisson
    equipement = sorted({USTENSILES_EQUIPEMENT[u] for u in r["ustensiles"] if u in USTENSILES_EQUIPEMENT})
    auto = {
        "rapide": total <= 20,
        "vegetarien": vegetarien,
        "vegan": vegan,
        "sans_porc": sans_porc,
        "pescetarien": pescetarien,
        "au_four": "four" in equipement,
        "sans_four": "four" not in equipement,
        "sans_cuisson": cuisson == 0,
        "se_garde_3j": restes >= 3,
        "pas_cher": cout / portions <= 1.5,
        "poisson": any(i["categorie"] in CATEGORIES_MER for i in ings),
    }
    etiquettes += [k for k, v in auto.items() if v and k not in etiquettes]
    if "batch" in etiquettes and (restes < 3 or portions < 3):
        raise ErreurSource(f"{ou} « {r['nom']} » : un plat « batch » fait 3 portions ou plus et se garde 3 jours")

    securite = []
    cats = {i["categorie"] for i in ings}
    if "volaille" in cats:
        securite.append(SECURITE["volaille"])
    if any(i["hache"] for i in ings):
        securite.append(SECURITE["hache"])
    if "porc" in cats:
        securite.append(SECURITE["porc"])
    if any(i["categorie"] == "poisson" and i["id"] not in ("thon", "sardine") for i in ings):
        securite.append(SECURITE["poisson"])
    if "moules" in ids:
        securite.append(SECURITE["moules"])
    if "crevette" in ids:
        securite.append(SECURITE["crevette"])
    if any(i["trempage_heures"] for i in ings):
        securite.append(SECURITE["trempage"])
    if "riz" in ids or "riz_rond" in ids:
        securite.append(SECURITE["riz"])

    # Restes : 3 jours au plus ; 2 pour le poisson, la viande hachée et les fruits de mer ; 1 pour un plat de riz.
    plafond = 3
    if any(i["categorie"] in CATEGORIES_MER for i in ings) or any(i["hache"] for i in ings):
        plafond = 2
    if "moules" in ids or "crevette" in ids:
        plafond = 1
    restes_effectifs = min(restes, plafond)
    # Le riz mélangé au plat (riz cantonais, risotto, farce…) ne se garde qu'un jour : `riz: melange` dans la source,
    # ou du riz à risotto. Servi à part, le plat se garde et le riz se refait (la mention de sécurité le dit).
    if r.get("riz") not in (None, "melange", "a_part"):
        raise ErreurSource(f"{ou} « {r['nom']} » : riz: melange ou a_part")
    if r.get("riz") == "melange" or "riz_rond" in ids:
        restes_effectifs = min(restes_effectifs, 1)
    if ("riz" in ids or "riz_rond" in ids) and r["feculent"] != "riz" and r.get("riz") is None:
        raise ErreurSource(f"{ou} « {r['nom']} » : du riz sans féculent « riz »")
    if restes_effectifs == 0:
        conservation = "Ne se garde pas : à manger tout de suite."
    else:
        jours = "1 jour" if restes_effectifs == 1 else f"{restes_effectifs} jours"
        conservation = (f"Restes : {jours} au réfrigérateur dans une boîte fermée, mis au frais moins de 2 h après "
                        "la cuisson.")  # fmt: skip
        if "froid" not in etiquettes and cuisson > 0:
            conservation += " Réchauffe à cœur, jusqu'à ce que ce soit bien chaud au centre."
    if "batch" in etiquettes and restes_effectifs < 3:
        etiquettes.remove("batch")
    if restes_effectifs < 3 and "se_garde_3j" in etiquettes:
        etiquettes.remove("se_garde_3j")

    return {
        "id": r["id"],
        "nom": r["nom"],
        "famille": fichier,
        "portions": portions,
        "ingredients": r["ingredients"],
        "etapes": r["etapes"],
        "preparation_min": prep,
        "cuisson_min": cuisson,
        "temps_total_min": total,
        "difficulte": r["difficulte"],
        "cuisine": r["cuisine"],
        "proteine": r["proteine"],
        "feculent": r["feculent"],
        "cout_total_eur": round(cout, 2),
        "cout_portion_eur": round(cout / portions, 2),
        "saisons": sorted(mois),
        "produits_saisonniers": [i["id"] for i in comptes],
        "etiquettes": etiquettes,
        "allergenes": allergenes,
        "ustensiles": r["ustensiles"],
        "equipement": equipement,
        "conservation_jours": restes_effectifs,
        "conservation": conservation,
        "securite": securite,
        "source": "originale (Quotidien)",
    }


def lire_substitutions(ingredients: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    subs: dict[str, list[dict[str, str]]] = {}
    for n, ligne in _lignes(SOURCES / "substitutions.txt"):
        manquant, remplacant, conseil = (x.strip() for x in ligne.split("|"))
        for id_ in (manquant, remplacant):
            if id_ not in ingredients:
                raise ErreurSource(f"substitutions.txt:{n} : ingrédient inconnu « {id_} »")
        subs.setdefault(manquant, []).append({"par": remplacant, "conseil": conseil})
    return subs


def calendrier(ingredients: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    noms_mois = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
                 "novembre", "décembre")  # fmt: skip
    cal: dict[str, dict[str, list[str]]] = {}
    for m in MOIS:
        de_saison = [i for i in ingredients.values() if isinstance(i["saison"], list) and m in i["saison"]]
        legumes = sorted(i["id"] for i in de_saison if i["categorie"] == "legume")
        fruits = sorted(i["id"] for i in de_saison if i["categorie"] == "fruit")
        cal[str(m)] = {"mois": [noms_mois[m - 1]], "legumes": legumes, "fruits": fruits}
    return cal


def construire() -> dict[Path, str]:
    """Le contenu de chaque fichier JSON à écrire."""
    rayons = lire_rayons()
    ingredients = lire_ingredients(rayons)
    recettes = lire_recettes(ingredients)
    ids = [r["id"] for r in recettes]
    doublons = {i for i in ids if ids.count(i) > 1}
    if doublons:
        raise ErreurSource(f"identifiants de recette en double : {sorted(doublons)}")
    sorties: dict[Path, str] = {}

    def ecrire(chemin: Path, donnees: Any) -> None:
        sorties[chemin] = json.dumps(donnees, ensure_ascii=False, indent=1, sort_keys=False) + "\n"

    ecrire(SORTIE / "rayons.json", rayons)
    ecrire(SORTIE / "ingredients.json", ingredients)
    ecrire(SORTIE / "saisons.json", calendrier(ingredients))
    ecrire(SORTIE / "substitutions.json", lire_substitutions(ingredients))
    familles: dict[str, list[dict[str, Any]]] = {}
    for r in recettes:
        familles.setdefault(r["famille"], []).append(r)
    for famille, liste in familles.items():
        ecrire(SORTIE / "recettes" / f"{famille}.json", liste)
    return sorties


def main(argv: list[str]) -> int:
    try:
        sorties = construire()
    except ErreurSource as e:
        print(f"ERREUR : {e}")
        return 1
    if "--verifier" in argv:
        differents = [p for p, contenu in sorties.items() if not p.exists() or p.read_text(encoding="utf-8") != contenu]
        anciens = {p for p in (SORTIE / "recettes").glob("*.json")} - set(sorties)
        if differents or anciens:
            print("Les JSON ne correspondent pas aux sources :", [p.name for p in differents + sorted(anciens)])
            return 1
        print("JSON conformes aux sources.")
        return 0
    (SORTIE / "recettes").mkdir(parents=True, exist_ok=True)
    for p in (SORTIE / "recettes").glob("*.json"):
        if p not in sorties:
            p.unlink()
    for p, contenu in sorties.items():
        p.write_text(contenu, encoding="utf-8")
    n = sum(len(json.loads(c)) for p, c in sorties.items() if p.parent.name == "recettes")
    print(f"{n} recettes écrites dans {SORTIE.relative_to(ICI.parent)}/recettes/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
