"""60 frigos réalistes (§10.3) : ce que tu écris, les aliments « à finir » qu'une recette pertinente doit utiliser
(au moins un), et le profil (régime, allergies, aliments refusés, équipement).

Une proposition est pertinente si elle utilise au moins un des aliments clés ; le vide-frigo réussit un frigo si
l'une des 3 premières propositions est pertinente. Aucune proposition ne doit jamais violer le profil.
"""

from __future__ import annotations

from typing import Any

FRIGOS: list[tuple[str, set[str], dict[str, Any]]] = [
    # --- Omnivore, sans contrainte ---
    ("2 courgettes, un reste de riz, feta, 6 oeufs", {"courgette", "riz", "feta", "oeuf"}, {}),
    ("poulet, crème, champignons", {"poulet_filet", "creme", "champignon"}, {}),
    ("steak haché, oignons, tomates", {"boeuf_hache", "tomate"}, {}),
    ("lentilles corail, lait de coco, oignon", {"lentille_corail", "lait_coco"}, {}),
    ("pâtes, lardons, crème", {"lardons", "creme"}, {}),
    ("saumon, citron, riz", {"saumon"}, {}),
    ("poireaux, pommes de terre", {"poireau", "pomme_de_terre"}, {}),
    ("6 oeufs, un reste de jambon, fromage râpé", {"oeuf", "jambon", "fromage_rape"}, {}),
    ("3 tomates, mozzarella, basilic", {"tomate", "mozzarella"}, {}),
    ("chorizo, poivron, oignon", {"chorizo", "poivron"}, {}),
    ("aubergine, tomates, oignon", {"aubergine", "tomate"}, {}),
    ("un reste de pâtes, 2 oeufs, parmesan", {"pates", "oeuf", "parmesan"}, {}),
    ("cuisses de poulet, citron, oignons", {"poulet_cuisse"}, {}),
    ("thon en boîte, tomates, oeufs", {"thon", "tomate", "oeuf"}, {}),
    ("épinards, ricotta, pâtes", {"epinard", "ricotta"}, {}),
    ("butternut, oignon, crème", {"courge", "creme"}, {}),
    ("carottes, pommes de terre, poireaux", {"carotte", "pomme_de_terre", "poireau"}, {}),
    ("saucisses, lentilles vertes, carottes", {"saucisse", "lentille_verte"}, {}),
    ("brocoli, poulet, sauce soja", {"brocoli", "poulet_filet"}, {}),
    ("pois chiches, épinards, tomates", {"pois_chiche", "epinard", "tomate"}, {}),
    ("un reste de riz, 2 oeufs, petits pois", {"riz", "oeuf", "petit_pois"}, {}),
    ("chou-fleur, fromage râpé, lait", {"chou_fleur", "fromage_rape"}, {}),
    ("courgettes, chèvre, pâte feuilletée", {"courgette", "chevre"}, {}),
    ("haricots rouges, steak haché, maïs", {"boeuf_hache", "haricot_rouge"}, {}),
    ("crevettes, ail, citron, pâtes", {"crevette"}, {}),
    ("champignons, oeufs, fromage râpé", {"champignon", "oeuf"}, {}),
    ("patate douce, pois chiches, épinards", {"patate_douce", "pois_chiche", "epinard"}, {}),
    ("dinde, crème, moutarde", {"dinde", "creme"}, {}),
    ("cabillaud, poireaux, crème", {"poisson_blanc", "poireau"}, {}),
    ("jambon, pain de mie, fromage râpé", {"jambon", "pain_mie"}, {}),
    ("tortillas, poulet, poivron", {"tortilla", "poulet_filet", "poivron"}, {}),
    ("un reste de poulet, riz, carottes", {"poulet_filet", "carotte"}, {}),
    ("pain rassis, oeufs, lait", {"pain", "oeuf"}, {}),
    ("feta, concombre, tomates", {"feta", "concombre", "tomate"}, {}),
    ("lardons, salade, oeufs", {"lardons", "salade", "oeuf"}, {}),
    # --- Végétarien ---
    ("courgettes, oeufs, feta", {"courgette", "oeuf", "feta"}, {"regime": "vegetarien"}),
    ("lentilles corail, carottes, lait de coco", {"lentille_corail", "carotte"}, {"regime": "vegetarien"}),
    ("champignons, crème, pâtes", {"champignon", "creme"}, {"regime": "vegetarien"}),
    ("pois chiches, tomates, oignon", {"pois_chiche", "tomate"}, {"regime": "vegetarien"}),
    ("poulet, poivron, oeufs, tomates", {"poivron", "oeuf", "tomate"}, {"regime": "vegetarien"}),  # jamais le poulet
    ("aubergine, mozzarella, tomates", {"aubergine", "mozzarella", "tomate"}, {"regime": "vegetarien"}),
    ("épinards, oeufs, fromage râpé", {"epinard", "oeuf"}, {"regime": "vegetarien"}),
    # --- Végan ---
    ("lentilles corail, lait de coco, tomates", {"lentille_corail", "lait_coco"}, {"regime": "vegan"}),
    ("pois chiches, courgettes, poivron", {"pois_chiche", "courgette", "poivron"}, {"regime": "vegan"}),
    ("tofu, brocoli, sauce soja", {"tofu", "brocoli"}, {"regime": "vegan"}),
    ("haricots rouges, maïs, tomates, oignon, carottes", {"haricot_rouge", "tomate", "mais"}, {"regime": "vegan"}),
    # --- Pescétarien ---
    ("saumon, épinards, crème", {"saumon", "epinard"}, {"regime": "pescetarien"}),
    ("thon, pâtes, tomates", {"thon", "tomate"}, {"regime": "pescetarien"}),
    ("steak haché, courgettes, oeufs", {"courgette", "oeuf"}, {"regime": "pescetarien"}),
    # --- Sans porc ---
    ("lardons, crème, pâtes, oeufs", {"creme", "oeuf"}, {"regime": "sans_porc"}),
    ("poulet, champignons, crème", {"poulet_filet", "champignon"}, {"regime": "sans_porc"}),
    # --- Allergies ---
    ("courgettes, oeufs, feta", {"courgette", "oeuf"}, {"allergies": {"lait"}}),
    (
        "pâtes, crème, champignons, oeufs, patate douce",
        {"champignon", "oeuf", "patate_douce"},
        {"allergies": {"gluten"}},
    ),
    ("oeufs, pain, lait", {"pain", "lait"}, {"allergies": {"oeufs"}}),
    ("poulet, cacahuètes, riz", {"poulet_filet"}, {"allergies": {"arachides"}}),
    ("crevettes, saumon, riz", {"saumon"}, {"allergies": {"crustaces"}}),
    ("tofu, brocoli, riz", {"brocoli"}, {"allergies": {"soja"}}),
    # --- Aliments refusés, équipement ---
    ("champignons, poulet, crème", {"poulet_filet", "creme"}, {"interdits": {"champignon"}}),
    ("pommes de terre, lardons, oignon", {"pomme_de_terre", "lardons"}, {"equipement": {"plaques"}}),
    (
        "courgettes, tomates, aubergine",
        {"courgette", "tomate", "aubergine"},
        {"equipement": {"plaques", "micro-ondes"}},
    ),
]
