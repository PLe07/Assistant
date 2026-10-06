"""§11.1 : le corpus lui-même (taille, familles, vérité terrain, messages bien formés)."""

from __future__ import annotations

import email
import json
from collections import Counter
from email.policy import default
from pathlib import Path

from tests.corpus_arnaques import generer

FAMILLES_EXIGEES = {"colis", "amende", "sante", "impots", "formation", "banque", "proche", "annonce", "support",
                    "sextorsion", "loterie", "crypto", "emploi", "surtaxe"}  # fmt: skip


def test_taille_et_composition() -> None:
    c = generer.corpus_principal()
    n = Counter((e.verite, e.injection) for e in c)
    assert len(c) >= 200
    assert n[("arnaque", False)] >= 120 and n[("legitime", False)] >= 80 and n[("arnaque", True)] == 10
    assert FAMILLES_EXIGEES <= {e.famille for e in c if e.verite == "arnaque"}
    assert len({e.id for e in c}) == len(c)
    inedit = generer.corpus_inedit()
    assert len(inedit) == 80 and {e.id for e in inedit}.isdisjoint({e.id for e in c})


def test_variantes_exigees() -> None:
    textes = " ".join(e.brut.decode("utf-8", "replace") for e in generer.corpus_principal())
    assert "xn--" in textes  # punycode
    assert "bit.ly" in textes and "tinyurl.com" in textes  # liens raccourcis
    assert "arneli.fr" in textes and "impots-gouv.info" in textes and "labanquepostale-securite.com" in textes
    assert "📦" in textes and "Vore colis" in textes  # émojis, fautes
    assert "dmarc=fail" in textes  # faux en-têtes


def test_le_2e_corpus_est_inedit() -> None:
    """Aucun domaine du 2e corpus n'apparaît dans le premier (anti-triche)."""
    d1 = {d for e in generer.corpus_principal() for d in e.domaines}
    d2 = {d for e in generer.corpus_inedit() for d in e.domaines if e.verite == "arnaque"}
    assert d2 and d1.isdisjoint(d2 - {"googlemail.com", "outlook.com", "wa.me", "t.me"})  # plateformes communes


def test_mails_bien_formes() -> None:
    for e in generer.corpus_principal() + generer.corpus_inedit():
        if e.canal != "mail":
            continue
        m = email.message_from_bytes(e.brut, policy=default)
        assert m["From"] and m["Subject"] and m["Authentication-Results"], e.id
        corps = m.get_body(preferencelist=("plain",))
        assert corps is not None and corps.get_content().strip(), e.id


def test_contexte_deterministe() -> None:
    c = generer.corpus_principal()
    a, b = generer.contexte(c), generer.contexte(c)
    assert a == b
    dates, flux = a
    recents = [d for d, v in dates.items() if v and (generer.MAINTENANT.date() - v).days < 30]
    assert recents and flux and None in dates.values()


def test_ecrire(tmp_path: Path) -> None:
    v = generer.ecrire(tmp_path)
    assert len(v) == len(generer.corpus_principal()) + 80
    assert json.loads((tmp_path / "verite.json").read_text(encoding="utf-8")) == v
    assert (tmp_path / "principal" / "colis-05.eml").read_bytes().startswith(b"From:")
