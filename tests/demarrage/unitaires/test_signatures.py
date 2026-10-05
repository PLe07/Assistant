import time

from modules.demarrage import signatures as sg
from modules.demarrage.systeme import Resultat
from tests.demarrage.conftest import fixture
from tests.demarrage.outils import codesign, programme, signe_par


def test_analyser_codesign_sur_fixtures():
    assert sg.analyser_codesign(0, fixture("codesign_apple.txt")) == sg.Signature(
        "apple", "Apple", None, "Software Signing"
    )
    tiers = sg.analyser_codesign(0, fixture("codesign_tiers.txt"))
    assert (tiers.etat, tiers.editeur, tiers.equipe) == ("developpeur", "Zoom Video Communications, Inc.", "BJ4HAAB9B3")
    store = sg.analyser_codesign(0, fixture("codesign_appstore.txt"))
    assert (store.etat, store.editeur, store.equipe) == ("app_store", None, "QQ77RR66SS") and store.valide
    assert sg.analyser_codesign(0, fixture("codesign_adhoc.txt")).etat == "adhoc"
    assert sg.analyser_codesign(1, fixture("codesign_non_signe.txt")).etat == "non_signe"
    assert sg.analyser_codesign(1, fixture("codesign_introuvable.txt")).etat == "introuvable"


def test_analyser_codesign_cas_limites():
    assert sg.analyser_codesign(1, "invalid signature (code or signature have been modified)").etat == "invalide"
    assert sg.analyser_codesign(1, "").etat == "inconnue"
    assert sg.analyser_codesign(0, "Authority=Apple Development: Jean (AB12CD34EF)\n").editeur == "Jean"
    autre = sg.analyser_codesign(0, "Authority=Certificat Maison\nTeamIdentifier=ZZ\n")
    assert (autre.etat, autre.equipe, autre.valide) == ("inconnue", "ZZ", False)
    assert sg.analyser_codesign(0, "Identifier=x\n").etat == "inconnue"


def test_signer_cache_et_parallele(mac):
    a = programme(mac, "/Applications/A.app/Contents/MacOS/A")
    b = programme(mac, "/opt/b")
    mac.repondre_debut(["codesign"], codesign({a: signe_par("Éditeur A", "AAAAAAAAAA")}))
    cache = sg.CacheSignatures()
    r = sg.signer(mac, [a, b, a, "/disparu"], cache)
    assert r[a].editeur == "Éditeur A" and r[b].etat == "non_signe" and r["/disparu"].etat == "introuvable"
    assert len(mac.lancees("codesign")) == 2 and cache.modifie
    r2 = sg.signer(mac, [a, b], sg.CacheSignatures(cache.entrees))
    assert r2 == {a: r[a], b: r[b]} and len(mac.lancees("codesign")) == 2  # tout vient du cache
    mac.fichier(b, b"nouvelle version, plus longue")  # mis à jour : la taille change, on revérifie
    sg.signer(mac, [b], sg.CacheSignatures(cache.entrees))
    assert len(mac.lancees("codesign")) == 3


def test_signer_sans_codesign_ou_delai(mac):
    a = programme(mac, "/opt/a")
    mac.commandes.discard("codesign")
    cache = sg.CacheSignatures()
    assert sg.signer(mac, [a], cache)[a].etat == "inconnue" and not cache.modifie
    mac.commandes.add("codesign")
    mac.repondre_debut(["codesign"], Resultat(124, "", "pas de réponse"))
    assert sg.signer(mac, [a], cache)[a].etat == "inconnue" and not cache.modifie  # panne : pas gardée


def test_mdls():
    quand = sg.analyser_mdls(fixture("mdls_date.txt"))
    assert time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(quand)) == "2026-06-01 08:12:33"
    assert sg.analyser_mdls("2026-06-01 10:12:33 +0200") == quand
    assert sg.analyser_mdls(fixture("mdls_null.txt")) is None
    assert sg.analyser_mdls("2026-13-45 99:99:99 +0000") is None


def test_dernieres_utilisations(mac):
    mac.repondre(["mdls", "-raw", "-name", "kMDItemLastUsedDate", "/Applications/A.app"], "2026-06-01 08:12:33 +0000")
    mac.repondre(["mdls", "-raw", "-name", "kMDItemLastUsedDate", "/Applications/B.app"], "(null)")
    mac.repondre(["mdls", "-raw", "-name", "kMDItemLastUsedDate", "/Applications/F.app"], "2099-01-01 00:00:00 +0000")
    r = sg.dernieres_utilisations(
        mac, ["/Applications/A.app", "/Applications/B.app", "/Applications/C.app", "/Applications/F.app"]
    )
    assert r["/Applications/A.app"] and r["/Applications/B.app"] is None and r["/Applications/C.app"] is None
    assert r["/Applications/F.app"] is None  # date dans le futur : absurde
    mac.commandes.discard("mdls")
    assert sg.dernieres_utilisations(mac, ["/Applications/A.app"]) == {}
