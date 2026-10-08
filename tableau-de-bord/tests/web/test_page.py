"""La page locale sans navigateur : cartes et pastilles, détail et graphiques, vues transverses, mise à jour en
direct (SSE), actions (nouvelle référence, pas normal, sourdine), autonomie (ni CDN, ni script en ligne), vitesse."""

from __future__ import annotations

import html
import re
import socket
import time
from typing import Any

from tableau import vues
from tableau.module import EtatModule, Pastille
from tableau.web import graphiques, rendu, sse
from tests.fabrique_web import JETON, MAINTENANT, etats
from tests.outils_http import requete


def cartes(texte: str) -> dict[str, str]:
    return dict(re.findall(r'data-module="([^"]+)" data-pastille="([^"]+)"', texte))


def test_accueil_bandeau_et_cartes(site: Any) -> None:
    r = requete(site.port, "/")
    assert r.code == 200 and r.entetes["Content-Type"] == "text/html; charset=utf-8"
    t = html.unescape(r.texte)
    assert "🔴 2 choses à regarder" in t
    assert cartes(r.texte) == {"trieur": "rouge", "quotidien": "jaune", "bouclier": "vert", "corvees": "gris"}
    assert list(cartes(r.texte)) == ["trieur", "quotidien", "bouclier", "corvees"]  # le plus grave d'abord
    for morceau in ("Trieur s'est arrêté 5 fois aujourd'hui", "0,95 $ sur 1,00 $", "Erreurs sur 24 h",
                    "Prochaine tâche", "brief demain à 7h15", "31,0 %", "80 Mo", "analyse il y a 5 min",
                    "Mettre les alertes en sourdine 1 h", "éteint ou pas installé"):  # fmt: skip
        assert morceau in t, morceau
    # Chaque lien garde le jeton ; aucune ressource extérieure ; ni script ni style en ligne.
    liens = re.findall(r'(?:href|src)="([^"]+)"', r.texte)
    assert liens and all(lien.startswith(("/", "#", "data:")) for lien in liens)
    assert all(f"t={JETON}" in html.unescape(lien) for lien in liens if lien.startswith("/"))
    assert "http://" not in r.texte and "https://" not in r.texte
    assert not re.search(r"<script(?![^>]*\bsrc=)", r.texte) and " style=" not in r.texte
    assert re.search(r'<html lang="fr">', r.texte) and 'name="viewport"' in r.texte


def test_bandeau_tout_va_bien_et_vide(site: Any) -> None:
    site.source.publier([EtatModule("bouclier", "Bouclier", "🛡️", Pastille.VERT, "Tout va bien")])
    assert "✅ Tout va bien" in html.unescape(requete(site.port, "/").texte)
    site.source.publier([])
    assert "Aucun module observé" in requete(site.port, "/fragment/accueil").texte
    assert vues.bandeau([EtatModule("q", "Q", "", Pastille.JAUNE, "")])["texte"] == "🟡 1 chose à regarder"


def test_detail_d_un_module(site: Any) -> None:
    r = requete(site.port, "/module/trieur")
    t = html.unescape(r.texte)
    assert r.code == 200 and "<title>Trieur · Tableau de bord</title>" in t
    assert t.count("<svg viewBox") == 4 and t.count("Voir les chiffres") == 4
    attendus = [
        "Temps en bonne santé (%)", "Erreurs par jour", "Processeur moyen (%)", "Mémoire moyenne (Mo)",
        "Historique sur 7 jours", "Voir 30 jours", "Files d'attente", "BoiteMac : 2 documents",
        "Derniers messages d'erreur (caviardés)", "1 fichier changé depuis la référence",
        "C'était moi, nouvelle référence", "Pas normal", "Lancer le diagnostic", "trieur doctor",
    ]  # fmt: skip
    for titre in attendus:
        assert titre in t, titre
    trente = html.unescape(requete(site.port, "/module/trieur?jours=30").texte)
    assert (
        "Historique sur 30 jours" in trente and "Voir 7 jours" in trente and trente.count("<tr><th scope='row'>") >= 120
    )
    attentes = html.unescape(requete(site.port, "/module/quotidien").texte)
    assert "A-t-il fait son travail ?" in attentes and "✗ manqué" in attentes and "✓ fait" in attentes
    assert "Pas encore de référence." in attentes
    assert requete(site.port, "/module/inconnu").code == 404
    assert requete(site.port, "/api/module/inconnu").code == 404
    # Un module du registre pas encore observé a quand même sa page.
    site.source.publier([e for e in etats() if e.id != "corvees"])
    assert "Pas encore observé" in html.unescape(requete(site.port, "/module/corvees").texte)


def test_series_jour_par_jour(site: Any) -> None:
    s = vues.series(site.source.base, "trieur", 7, MAINTENANT)
    assert [p["etiquette"] for p in s] == ["01/10", "02/10", "03/10", "04/10", "05/10", "06/10", "07/10"]
    assert s[-1]["part_vert"] is not None and s[-1]["part_vert"] < 100  # les 4 dernières heures en rouge
    assert s[0]["part_vert"] == 100  # les agrégats horaires remontent jusqu'au 1er octobre
    trente = vues.series(site.source.base, "trieur", 30, MAINTENANT)
    assert trente[0]["part_vert"] is None and trente[0]["cpu_moy"] is None and trente[0]["erreurs"] is None
    assert s[2]["part_vert"] == 100 and s[2]["cpu_moy"] == 1.5  # agrégats horaires


def test_vues_transverses(site: Any) -> None:
    c = html.unescape(requete(site.port, "/credits").texte)
    assert "Crédits Claude · 2026-10" in c and "1,75 $" in c and "sur 3,00 $ de plafonds" in c
    assert "Mois précédent : 1,20 $" in c and "option éteinte" in c
    r = html.unescape(requete(site.port, "/ressources").texte)
    assert "Mon assistant me coûte-t-il de la batterie ?" in r and "de la charge du processeur du Mac" in r
    i = html.unescape(requete(site.port, "/integrite").texte)
    assert "Trieur : ⚠️ changé" in i and "main.py : modifié" in i and "ne restaure jamais rien" in i
    j = html.unescape(requete(site.port, "/journal").texte)
    assert "Trieur s'est arrêté 5 fois en 10 min" in j and "Bouclier tourne de nouveau" in j
    filtre = html.unescape(requete(site.port, "/journal?module=trieur").texte)
    assert "Bouclier tourne de nouveau" not in filtre and 'aria-current="true">Trieur' in filtre
    assert "Bouclier tourne de nouveau" in requete(site.port, "/journal?module=nimporte").texte
    assert requete(site.port, "/inconnue").code == 404
    assert requete(site.port, "/fragment/inconnue").code == 404


def test_credits_reels_et_mac_illisibles(site: Any) -> None:
    base = site.source.base
    base.ecrire_meta("credits_reels", '{"mois": "2026-10", "usd": 2.5}')
    assert "Coût réel de l'organisation (rapport officiel) : <b>2,50 $</b>" in html.unescape(
        requete(site.port, "/credits").texte
    )
    for abime in ('{"mois": "2026-09", "usd": 2.5}', "abîmé", '{"mois": "2026-10"}'):
        base.ecrire_meta("credits_reels", abime)
        assert vues.vue_credits(site.source)["reel_usd"] is None
    site.source.reglages["credits"]["api_admin"] = True
    assert "pas encore relevé" in html.unescape(requete(site.port, "/credits").texte)
    base.ecrire_meta("mac", "abîmé")
    assert vues.vue_ressources(site.source)["part_cpu_mac"] is None


def test_fragments_et_api(site: Any) -> None:
    f = requete(site.port, "/fragment/module/trieur?jours=30")
    assert f.code == 200 and not f.texte.startswith("<!doctype") and "Historique sur 30 jours" in f.texte
    page = requete(site.port, "/module/trieur?jours=30").texte
    assert f'data-fragment="/fragment/module/trieur?t={JETON}&amp;jours=30"' in page
    a = requete(site.port, "/api/etat").json()
    assert a["bandeau"]["niveau"] == "rouge" and [c["id"] for c in a["cartes"]][0] == "trieur"
    d = requete(site.port, "/api/module/trieur").json()
    assert (
        d["jours"] == 7 and len(d["series"]) == 7 and d["erreurs"][0]["message"].startswith("Échec d'envoi à [e-mail]")
    )
    assert requete(site.port, "/", "HEAD").corps == b""


def lire_flux(port: int, n: int, delai: float = 5) -> list[str]:
    """Les `n` premiers messages « maj » du flux en direct."""
    s = socket.create_connection(("127.0.0.1", port), timeout=delai)
    s.sendall(f"GET /evenements?t={JETON} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\r\n".encode())
    tampon = b""
    fin = time.monotonic() + delai
    while tampon.count(b"event: maj") < n and time.monotonic() < fin:
        morceau = s.recv(4096)
        if not morceau:
            break
        tampon += morceau
    s.close()
    return re.findall(r"event: maj\ndata: (\d+)", tampon.decode())


def test_direct_par_sse(site: Any) -> None:
    import threading

    def publier_bientot() -> None:
        time.sleep(0.3)
        site.source.publier(etats())

    threading.Thread(target=publier_bientot).start()
    versions = lire_flux(site.port, 2)
    assert len(versions) == 2 and int(versions[1]) == int(versions[0]) + 1
    entete = requete(site.port, "/evenements", jeton="faux")
    assert entete.code == 403
    assert sse.message("maj", "a\nb") == b"event: maj\ndata: a b\n\n"


def test_battement_et_fermeture(site: Any) -> None:
    s = socket.create_connection(("127.0.0.1", site.port), timeout=5)
    s.sendall(f"GET /evenements?t={JETON} HTTP/1.1\r\nHost: 127.0.0.1:{site.port}\r\n\r\n".encode())
    tampon = b""
    fin = time.monotonic() + 4
    while b": battement" not in tampon and time.monotonic() < fin:
        tampon += s.recv(4096)
    assert b"text/event-stream" in tampon and b": battement" in tampon
    assert site.source.diffuseur.clients == 1
    s.close()
    d = sse.Diffuseur()
    assert d.entrer() and d.version == 0
    d.fermer()
    assert d.attendre(0, 5) == 0 and not d.entrer() and d.ferme
    d.sortir()
    d.sortir()
    assert d.clients == 0


def test_actions(site: Any) -> None:
    r = requete(site.port, "/action/pas-normal/trieur", "POST")
    d = r.json()
    assert d["ok"] and d["commande"].startswith("cd ") and "Rien n'a été restauré" in d["message"]
    assert d["ecarts"] == [{"chemin": "main.py", "genre": "modifié", "quand": 1}]
    r = requete(site.port, "/action/reference/trieur", "POST")
    assert r.json()["message"].startswith("C'est noté : le code actuel de Trieur devient la référence")
    assert site.source.gardien.etat("trieur")["ecarts"] == []
    genres = [e["genre"] for e in site.source.base.evenements(0)]
    assert "reference" in genres and "pas_normal" in genres
    assert requete(site.port, "/action/sourdine", "POST", corps={"duree": "30min"}).json()["message"] == (
        "Alertes en sourdine jusqu'à 10h30."
    )
    accueil = html.unescape(requete(site.port, "/").texte)
    assert "Notifications : en sourdine jusqu'à 10h30" in accueil and "Lever la sourdine" in accueil
    assert requete(site.port, "/action/sourdine", "POST", corps={"duree": "fin"}).json()["message"] == "Sourdine levée."
    assert requete(site.port, "/action/pas-normal/inconnu", "POST").code == 404
    assert requete(site.port, "/action/diagnostic/inconnu", "POST").code == 404


def test_diagnostic_sans_dossier(site: Any) -> None:
    from tableau import systeme

    defn = site.source.defs["trieur"]
    site.source.defs["trieur"] = type(defn)(**{**defn.__dict__, "dossier_projet": "~/Nulle/Part"})
    d = site.source.diagnostic("trieur", systeme.DemandeExplicite("terminal", "trieur"))
    assert d == {"ok": False, "sortie": "Le dossier du module est introuvable."}


def test_vitesse(site: Any) -> None:
    for chemin in ("/", "/module/trieur?jours=30", "/credits", "/journal"):
        requete(site.port, chemin)
        debut = time.perf_counter()
        assert requete(site.port, chemin).code == 200
        assert time.perf_counter() - debut < 0.3, chemin


def test_graphiques() -> None:
    svg = graphiques.graphique("Erreurs", ["a", "b", "c"], [None, None, None])
    assert (
        "0 jour observé sur 3" in svg and "<path" not in svg and svg.count("pas observé") == 6
    )  # 3 infobulles, 3 cases du tableau
    ligne = graphiques.graphique("Proc", ["a", "b", "c", "d"], [1.0, None, 2.0, 3.0], "ligne")
    assert ligne.count("<polyline") == 1 and ligne.count("<circle") == 3  # le trou coupe la courbe
    barres = graphiques.graphique("Part", [str(i) for i in range(30)], [50.0] * 29 + [0.0], "barres", 100.0)
    assert barres.count("<path") == 29 and "<circle" not in barres
    piege = graphiques.graphique("<script>alert(1)</script>", ["<b>"], [1.0])
    assert "<script" not in piege and "&lt;script&gt;" in piege and "&lt;b&gt;" in piege
    assert (
        graphiques._graduation(0) == 1 and graphiques._graduation(57) == 100 and graphiques._graduation(12345) == 12346
    )
    assert graphiques.jauge(None, 2.0, "x") == "" and graphiques.jauge(1.0, None, "x") == ""
    assert "jauge-ok" in graphiques.jauge(0.5, 2.0, "x") and "jauge-jaune" in graphiques.jauge(1.7, 2.0, "x")
    assert "jauge-rouge" in graphiques.jauge(2.5, 2.0, "x") and 'width="100.0"' in graphiques.jauge(2.5, 2.0, "x")


def test_page_d_erreur_sans_lien() -> None:
    page = rendu.erreur(403, "jeton absent ou faux")
    assert "403" in page and "href" not in page and "src" not in page
    assert rendu.lien("/module/a b", "j&t", jours=None) == "/module/a b?t=j%26t"
