"""La page dans un vrai navigateur sans fenêtre (Chromium par Playwright, §9.4) : cartes et pastilles, aucune erreur
dans la console, contrastes AA mesurés en clair et en sombre, 375 px sans défilement horizontal, navigation au
clavier, mise à jour en direct, boutons d'action, chargement en moins de 300 ms. Sauté si Playwright est absent."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from tableau.module import Pastille
from tests.fabrique_web import JETON, etats

pytestmark = pytest.mark.navigateur
sync_api = pytest.importorskip("playwright.sync_api")
# Les attentes par sélecteur n'évaluent pas de texte JavaScript : elles marchent malgré notre CSP stricte.
attendre = sync_api.expect

PAGES = ["/", "/module/trieur", "/module/quotidien?jours=30", "/credits", "/ressources", "/integrite", "/journal"]

CONTRASTE = """
() => {
  const lire = (c) => {
    const m = c && c.match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(parseFloat);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const melanger = (h, b) => ({ r: h.r * h.a + b.r * (1 - h.a), g: h.g * h.a + b.g * (1 - h.a),
                                b: h.b * h.a + b.b * (1 - h.a), a: 1 });
  const lum = ({ r, g, b }) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const fond = (el) => {
    const couches = [];
    for (let e = el; e; e = e.parentElement) {
      const c = lire(getComputedStyle(e).backgroundColor);
      if (c && c.a > 0) { couches.push(c); if (c.a >= 1) break; }
    }
    let res = { r: 255, g: 255, b: 255, a: 1 };
    for (let i = couches.length - 1; i >= 0; i--) res = melanger(couches[i], res);
    return res;
  };
  const echecs = [];
  let n = 0;
  const marcheur = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (marcheur.nextNode()) {
    const t = marcheur.currentNode;
    const el = t.parentElement;
    if (!el || !t.textContent.trim() || el.closest('title, desc, script, style')) continue;
    const st = getComputedStyle(el);
    const boite = el.getBoundingClientRect();
    if (st.visibility === 'hidden' || st.display === 'none' || boite.width === 0 || boite.height === 0) continue;
    if (el.closest('.evitement')) continue;
    const svg = el instanceof SVGElement;
    const avant = lire(svg ? st.fill : st.color);
    if (!avant) continue;
    const b = fond(svg ? el.closest('figure') : el);
    const f = melanger(avant, b);
    const l1 = lum(f), l2 = lum(b);
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    const taille = parseFloat(st.fontSize), gras = parseInt(st.fontWeight, 10) >= 700;
    const seuil = (taille >= 24 || (gras && taille >= 18.66)) ? 3 : 4.5;
    n += 1;
    if (ratio < seuil) echecs.push(t.textContent.trim().slice(0, 40) + ' : ' + ratio.toFixed(2));
  }
  return { n, echecs };
}
"""


@pytest.fixture(scope="module")
def navigateur() -> Iterator[Any]:
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # noqa: BLE001 - pas de navigateur installé : on saute
            pytest.skip(f"Chromium indisponible : {e}")
        yield b
        b.close()


def ouvrir(
    navigateur: Any, site: Any, chemin: str, largeur: int = 1100, schema: str = "light"
) -> tuple[Any, list[str]]:
    page = navigateur.new_page(viewport={"width": largeur, "height": 900}, color_scheme=schema)
    problemes: list[str] = []
    page.on(
        "console",
        lambda m: problemes.append(f"console {m.type} : {m.text}") if m.type in ("error", "warning") else None,
    )
    page.on("pageerror", lambda e: problemes.append(f"erreur : {e}"))
    page.on("requestfailed", lambda r: problemes.append(f"échec : {r.url}") if "/evenements" not in r.url else None)
    page.on("response", lambda r: problemes.append(f"{r.status} : {r.url}") if r.status >= 400 else None)
    separateur = "&" if "?" in chemin else "?"
    page.goto(f"http://127.0.0.1:{site.port}{chemin}{separateur}t={JETON}", wait_until="load")
    return page, problemes


def test_cartes_pastilles_et_aucune_erreur(navigateur: Any, site: Any) -> None:
    page, problemes = ouvrir(navigateur, site, "/")
    cartes = page.locator("li.carte")
    assert cartes.count() == 4
    pastilles = {c.get_attribute("data-module"): c.get_attribute("data-pastille") for c in cartes.all()}
    assert pastilles == {"trieur": "rouge", "quotidien": "jaune", "bouclier": "vert", "corvees": "gris"}
    assert " ".join(page.locator("li.carte[data-module=trieur] .pastille").inner_text().split()) == "🔴 problème"
    assert page.locator("#titre-bandeau").inner_text() == "🔴 2 choses à regarder"
    attendre(page.locator("#etat-direct")).to_have_text("En direct")
    for chemin in PAGES[1:]:
        p, autres = ouvrir(navigateur, site, chemin)
        problemes += autres
        p.close()
    page.close()
    assert problemes == []


@pytest.mark.parametrize("schema", ["light", "dark"])
def test_contrastes_aa(navigateur: Any, site: Any, schema: str) -> None:
    for chemin in PAGES:
        page, _ = ouvrir(navigateur, site, chemin, schema=schema)
        for ouvert in page.locator("details").all():
            ouvert.evaluate("d => d.open = true")
        r = page.evaluate(CONTRASTE)
        page.close()
        assert r["n"] > 10 and r["echecs"] == [], (chemin, r["echecs"])


def test_bouton_theme_et_contrastes_force(navigateur: Any, site: Any) -> None:
    page, _ = ouvrir(navigateur, site, "/module/trieur", schema="light")
    bouton = page.locator("#theme")
    assert bouton.get_attribute("aria-pressed") == "false"
    bouton.click()
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    assert bouton.get_attribute("aria-pressed") == "true"
    assert page.evaluate(CONTRASTE)["echecs"] == []
    page.reload()
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"  # retenu
    page.close()


def test_petit_ecran_sans_defilement_horizontal(navigateur: Any, site: Any) -> None:
    for schema in ("light", "dark"):
        for chemin in PAGES:
            page, _ = ouvrir(navigateur, site, chemin, largeur=375, schema=schema)
            largeur = page.evaluate("document.documentElement.scrollWidth")
            page.close()
            assert largeur <= 375, (chemin, largeur)


def test_navigation_au_clavier(navigateur: Any, site: Any) -> None:
    page, _ = ouvrir(navigateur, site, "/")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.textContent") == "Aller au contenu"
    for _ in range(20):
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement.classList.contains('carte-lien')"):
            break
    else:
        pytest.fail("aucune carte atteinte au clavier")
    # Le contour de focus est visible.
    assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") == "solid"
    page.keyboard.press("Enter")
    page.wait_for_url("**/module/trieur?t=*")
    assert "Trieur" in page.locator("h1").inner_text()
    page.close()


def test_mise_a_jour_en_direct(navigateur: Any, site: Any) -> None:
    page, problemes = ouvrir(navigateur, site, "/")
    attendre(page.locator("#etat-direct")).to_have_text("En direct")
    nouveaux = etats()
    nouveaux[1].pastille = Pastille.VERT
    nouveaux[1].problemes = []
    nouveaux[1].phrase = "Tourne de nouveau"
    site.source.publier(nouveaux)
    page.wait_for_selector("li.carte[data-module=trieur][data-pastille=vert]", timeout=5000)
    assert "Tourne de nouveau" in page.locator("li.carte[data-module=trieur]").inner_text()
    page.close()
    assert problemes == []


def test_boutons_d_action(navigateur: Any, site: Any) -> None:
    page, problemes = ouvrir(navigateur, site, "/module/trieur")
    page.get_by_role("button", name="Pas normal").click()
    resultat = page.locator("#resultat")
    resultat.locator("pre").wait_for()
    assert "Rien n'a été restauré" in resultat.inner_text()
    assert resultat.locator("pre").inner_text().startswith("cd ")
    page.once("dialog", lambda d: d.accept())
    page.get_by_role("button", name="C'était moi, nouvelle référence").click()
    attendre(resultat).to_contain_text("devient la référence")
    # La page se met à jour seule : plus de code changé.
    attendre(page.locator("#contenu")).to_contain_text("Identique à la référence")
    # Refuser la confirmation : rien n'est lancé.
    page.once("dialog", lambda d: d.dismiss())
    page.get_by_role("button", name="Lancer le diagnostic").click()
    page.wait_for_timeout(300)
    assert "devient la référence" in resultat.inner_text()
    page.once("dialog", lambda d: d.accept())
    page.get_by_role("button", name="Lancer le diagnostic").click()
    attendre(resultat).to_contain_text("Diagnostic terminé")
    assert "diagnostic ok pour [e-mail]" in resultat.inner_text()
    page.close()
    assert problemes == []


def test_chargement_rapide(navigateur: Any, site: Any) -> None:
    for chemin in ("/", "/module/trieur?jours=30"):
        page, _ = ouvrir(navigateur, site, chemin)
        page.reload(wait_until="load")
        duree = page.evaluate("performance.getEntriesByType('navigation')[0].loadEventEnd")
        page.close()
        assert 0 < duree < 300, (chemin, duree)
