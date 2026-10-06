"""§11.2 : aucune donnée plantée (faux IBAN, numéro de carte, téléphone, adresse, nom) dans ce qui part vers l'IA,
ni dans le journal, ni dans l'historique, après une vérification complète."""

from __future__ import annotations

import json
from pathlib import Path

from bouclier import config, db, journal
from bouclier.arnaque import analyse, extraction, historique
from tests.unitaires.test_ia import JSON_OK, FauxClient

PLANTES = {
    "nom": "Camille Exemplaire",
    "telephone": "06 98 76 54 32",
    "adresse": "27 rue des Acacias",
    "email": "camille.exemplaire@example.org",
    "iban": "FR76 3000 6000 0112 3456 7890 189",
    "carte": "4970 1012 3456 7893",
}
MORCEAUX_INTERDITS = ["Exemplaire", "98 76 54", "Acacias", "camille.exemplaire", "3000 6000", "4970 1012", "7893"]


def _message() -> extraction.Message:
    texte = (
        f"Bonjour {PLANTES['nom']}, votre carte {PLANTES['carte']} est bloquée. Confirmez votre IBAN {PLANTES['iban']}"
        f" et votre adresse {PLANTES['adresse']}, 33000 Bordeaux, ici : https://banque-securite-maj.top/c?mail="
        f"{PLANTES['email']} ou rappelez-nous, nous vous appellerons au {PLANTES['telephone']}."
    )
    return extraction.depuis_texte(texte, "sms")


def test_rien_de_personnel_ne_sort(tmp_path: Path) -> None:
    chemins = config.chemins()
    chemins.support.mkdir(parents=True)
    chemins.config.write_text(
        "[moi]\n"
        f'noms = ["{PLANTES["nom"]}"]\ntelephones = ["{PLANTES["telephone"]}"]\n'
        f'adresses = ["{PLANTES["adresse"]}"]\nemails = ["{PLANTES["email"]}"]\n',
        encoding="utf-8",
    )
    reglages = config.charger(chemins)
    journal.configurer(chemins.logs, reglages["moi"])
    base = db.ouvrir(chemins.base)
    client = FauxClient([JSON_OK])
    outils = analyse.Outils(reglages, base, client=client)
    resultat = analyse.verifier(_message(), outils, "test", demande_ia=True)
    assert resultat.verdict.ia_consultee and len(client.recus) == 1

    envoye = client.recus[0]
    lignes = historique.lister(base)
    stocke = json.dumps([dict(ligne) for ligne in lignes], ensure_ascii=False)
    for h in list(journal.log().handlers):
        h.flush()
    log = (chemins.logs / "bouclier.log").read_text(encoding="utf-8")
    assert "vérification n°" in log
    for lieu, contenu in (("IA", envoye), ("historique", stocke), ("journal", log)):
        for morceau in MORCEAUX_INTERDITS:
            assert morceau not in contenu, (lieu, morceau)
    assert "[IBAN]" in envoye and "[CARTE]" in envoye and "[NOM]" in envoye
    base.fermer()
