"""Le rapport HTML : autonome, en français, mode sombre, tout échappé, sans ce que tu as déjà décidé."""

import re
import stat
from types import SimpleNamespace

from modules.corvees import propositions, rapport
from modules.corvees.descriptions import locale
from tests.corvees.unitaires.test_ia import SOIR, candidat, description


def remplir(base, reglages, cands, descriptions=None):
    base.enregistrer_candidats(cands, SOIR - 60)
    base.ecrire("derniere_analyse", SOIR - 60)
    for c in cands:
        d = (descriptions or {}).get(c["signature"]) or locale(c)
        source = "claude" if c["signature"] in (descriptions or {}) else "locale"
        base.noter_description(c["signature"], source, d, SOIR)
        propositions.ecrire(reglages, c, {**d, "source": source})


def test_page_autonome_francaise_et_sombre(base, reglages):
    cands = [candidat(1), candidat(2, tokens=["cmd:make"], type="shell")]
    remplir(base, reglages, cands, {"sig1": description("id0001")})
    page = rapport.construire(base, reglages, SOIR)
    assert page.startswith("<!doctype html>") and '<html lang="fr">' in page
    assert "prefers-color-scheme:dark" in page and 'name="color-scheme" content="light dark"' in page
    assert not re.search(r"""(src|href)=["']?(https?:)?//""", page)  # rien à télécharger
    assert "2 corvées" in page and "Tes corvées repérées" in page
    assert "Tu déplaces les fichiers « Facture_*.pdf » de ~/Downloads vers ~/Documents/Factures1" in page
    assert "Dernière fois : <strong>" in page and "fois par mois" in page and "min/mois" in page
    assert "corvees accept id0001" in page and "corvees reject id0001" in page and "corvees snooze id0001 7" in page
    assert "par Claude" in page and "sans Claude" in page
    assert "Tu ranges tes factures à la main chaque semaine." in page  # le texte de Claude
    assert "corvees accept id0002 --installer" in page  # l'alias est sûr et installable


def test_tout_est_echappe(base, reglages):
    c = candidat(1, tokens=["app:<script>alert(1)</script>"], type="sequence")
    d = description("id0001", titre_court="<img src=x onerror=alert(1)>")
    d["solution"]["script"] = "echo '</code></pre><script>alert(2)</script>'"
    remplir(base, reglages, [c], {"sig1": d})
    page = rapport.construire(base, reglages, SOIR)
    assert "<script>alert" not in page and "<img src=x" not in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in page


def test_un_script_douteux_est_signale_et_pas_installable(base, reglages):
    d = description("id0001")
    d["solution"]["script"] = "sudo rm -rf /"
    remplir(base, reglages, [candidat(1)], {"sig1": d})
    page = rapport.construire(base, reglages, SOIR)
    assert "⚠️ à vérifier" in page and "sudo" in page and "--installer" not in page


def test_ce_que_tu_as_decide_depuis_n_apparait_plus(base, reglages):
    cands = [candidat(1), candidat(2)]
    remplir(base, reglages, cands)
    base.decider("sig1", "id0001", "reject", None, 12.9, cands[0]["tokens"])
    page = rapport.construire(base, reglages, SOIR)
    assert "id0001" not in page and "id0002" in page and "1 corvée" in page


def test_rien_a_proposer(base, reglages):
    page = rapport.construire(base, reglages, SOIR)
    assert "Rien de solide pour l'instant" in page and "Analyse du jamais" in page


def test_une_description_manquante_est_faite_sur_place(base, reglages):
    base.enregistrer_candidats([candidat(1)], SOIR)
    page = rapport.construire(base, reglages, SOIR)
    assert "Ranger les « Facture_*.pdf »" in page and "sans Claude" in page


def test_ecrire_et_ouvrir(base, reglages):
    remplir(base, reglages, [candidat(1)])
    fichier = rapport.ecrire(base, reglages, SOIR)
    assert fichier.name == "rapport.html" and stat.S_IMODE(fichier.stat().st_mode) == 0o600
    vus = []

    def lancer(commande, **_):
        vus.append(commande)
        return SimpleNamespace(returncode=0)

    assert rapport.ouvrir(fichier, lancer, "darwin") and vus == [["open", str(fichier)]]
    assert not rapport.ouvrir(fichier, lancer, "linux") and len(vus) == 1


def test_dates_en_francais():
    assert rapport.date_lisible(SOIR) == "lun. 5 oct. à 21:00"
    assert rapport.date_lisible(None) == "jamais"
    assert rapport._nombre(12.94) == "13" and rapport._nombre(2.5) == "2,5" and rapport._nombre(3.0) == "3"
