"""L'IA (plafond de 2 $ par mois, délai croissant sur 429/529, JSON validé, repli) et l'interface du Mac."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from quotidien import config, ia
from quotidien.db import Base
from quotidien.systeme import Resultat, Systeme, executer_vraiment, url_sms


class Etiquettes(BaseModel):
    voulus: list[str]


class Client:
    nom = "imitation"

    def __init__(self, reponses: list[Any]) -> None:
        self.reponses, self.appels = reponses, 0

    def envoyer(self, systeme: str, contenu: ia.Contenu, max_jetons: int, delai: float) -> ia.ReponseBrute:
        self.appels += 1
        r = self.reponses.pop(0)
        if isinstance(r, Exception):
            raise r
        return ia.ReponseBrute(r, 1000, 100)


@pytest.fixture
def db(tmp_path: Path) -> Base:
    return Base(tmp_path / "q.db")


def _reglages(**ia_: Any) -> dict[str, Any]:
    r = config.defauts().reglages
    r["ia"].update(ia_)
    return r


def test_reponse_valide_et_cout_compte(db: Base) -> None:
    r = ia.demander(db, _reglages(), "test", "sys", "texte", Etiquettes,
                    client=Client(['Voici : ```json\n{"voulus": ["a"]}\n```']))  # fmt: skip
    assert r.statut == "ok" and r.valeur.voulus == ["a"] and r.detail == "imitation"
    assert r.cout_usd == pytest.approx(1000 * 1e-6 + 100 * 5e-6)
    assert ia.Budget(db, _reglages()).depense_du_mois() == pytest.approx(r.cout_usd)


def test_delai_croissant_puis_abandon(db: Base) -> None:
    attentes: list[float] = []
    client = Client([ia.ErreurPassagere("529")] * 4)
    r = ia.demander(db, _reglages(), "t", "s", "x", Etiquettes, client=client, dormir=attentes.append)
    assert r.statut == "erreur" and attentes == [2.0, 4.0, 8.0] and client.appels == 4
    attentes.clear()
    client = Client([ia.ErreurPassagere("429", attendre=11.0), '{"voulus": []}'])
    r = ia.demander(db, _reglages(), "t", "s", "x", Etiquettes, client=client, dormir=attentes.append)
    assert r.statut == "ok" and attentes == [11.0]  # le délai demandé par l'API (retry-after)


def test_json_invalide_un_seul_nouvel_essai(db: Base) -> None:
    client = Client(["pas du json", '{"autre": 1}'])
    r = ia.demander(db, _reglages(), "t", "s", "x", Etiquettes, client=client)
    assert r.statut == "invalide" and client.appels == 2
    client = Client(["oups", '{"voulus": ["b"]}'])
    assert ia.demander(db, _reglages(), "t", "s", "x", Etiquettes, client=client).valeur.voulus == ["b"]


def test_erreur_definitive_budget_desactivee_indisponible(db: Base) -> None:
    r = ia.demander(db, _reglages(), "t", "s", "x", Etiquettes, client=Client([ia.ErreurDefinitive("400")]))
    assert r.statut == "erreur"
    assert ia.demander(db, _reglages(active=False), "t", "s", "x", Etiquettes).statut == "desactivee"
    assert ia.demander(db, _reglages(), "t", "s", "x", Etiquettes, lire_trousseau=lambda s: None).statut == (
        "indisponible"
    )
    # Plafond atteint : on n'appelle même pas.
    client = Client([])
    r = ia.demander(db, _reglages(budget_mensuel_usd=0.0), "t", "s", "x", Etiquettes, client=client)
    assert r.statut == "budget" and client.appels == 0


def test_budget_estimation_et_mois(db: Base) -> None:
    b = ia.Budget(db, _reglages(), horloge=lambda: 1_790_000_000.0)
    assert b.mois() == "2026-09"
    image = [{"type": "image", "source": {}}, {"type": "text", "text": "x" * 300}]
    assert b.estimation("s" * 30, image, 100) > b.estimation("s" * 30, "x" * 300, 100)
    b.noter(ia.ReponseBrute("", 10, 10, cout_usd=1.5), "photo")
    assert b.depense_du_mois() == 1.5 and b.reste() == 0.5 and b.permet(0.5) and not b.permet(0.51)
    assert ia.Budget(db, _reglages(), horloge=lambda: 1_795_000_000.0).depense_du_mois() == 0  # mois suivant


def test_extraire_json() -> None:
    assert ia.extraire_json('bla {"a": 1} bla') == {"a": 1}
    with pytest.raises(ValueError):
        ia.extraire_json("rien")


def test_choisir_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    r = _reglages()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "cle-env")
    assert isinstance(ia.choisir_client(r, lambda s: None), ia.ClientSDK)
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    c = ia.choisir_client(r, lambda s: "cle-trousseau" if s == "quotidien-anthropic" else None)
    assert isinstance(c, ia.ClientSDK) and c.cle == "cle-trousseau"
    assert ia.choisir_client(r, lambda s: None) is None  # pas de clé, pas de Claude Code
    faux = tmp_path / "claude"
    faux.write_text("")
    c = ia.choisir_client(r, lambda s: "jeton" if s == "quotidien-claude" else None, binaire=str(faux))
    assert isinstance(c, ia.ClientClaudeCode) and c.jeton == "jeton"
    assert ia.choisir_client(_reglages(active=False), lambda s: "x") is None


def test_client_claude_code() -> None:
    vus: list[dict[str, Any]] = []

    def executer(commande: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        vus.append({"commande": commande, **kw})
        resultat = {"type": "result", "result": '{"voulus": []}', "usage": {"input_tokens": 50, "output_tokens": 5},
                    "total_cost_usd": 0.0012}  # fmt: skip
        flux = "stream-json" in commande  # en flux : des lignes d'évènements, le résultat à la fin
        sortie = (json.dumps({"type": "system"}) + "\n" + json.dumps(resultat)) if flux else json.dumps(resultat)
        return subprocess.CompletedProcess(commande, 0, sortie, "")

    c = ia.ClientClaudeCode("/bin/claude", "claude-haiku-4-5", "jeton", executer)
    r = c.envoyer("sys", "texte", 100, 30)
    assert r.texte == '{"voulus": []}' and r.cout_usd == 0.0012 and r.jetons_entree == 50
    cmd = vus[0]["commande"]
    assert "--tools" in cmd and cmd[cmd.index("--tools") + 1] == "" and "--no-session-persistence" in cmd
    assert vus[0]["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "jeton" and "ANTHROPIC_API_KEY" not in vus[0]["env"]
    assert vus[0]["input"] == "texte"
    # Une image : entrée « stream-json ».
    c.envoyer("sys", [{"type": "text", "text": "x"}], 100, 30)
    assert "stream-json" in vus[1]["commande"] and json.loads(vus[1]["input"])["type"] == "user"

    def surcharge(commande: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(commande, 1, json.dumps({"is_error": True, "result": "529 overloaded"}), "")

    with pytest.raises(ia.ErreurPassagere):
        ia.ClientClaudeCode("/bin/claude", "m", None, surcharge).envoyer("s", "t", 10, 5)

    def casse(commande: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(commande, 2, "", "boum")

    with pytest.raises(ia.ErreurDefinitive):
        ia.ClientClaudeCode("/bin/claude", "m", None, casse).envoyer("s", "t", 10, 5)

    def lent(commande: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(commande, 5)

    with pytest.raises(ia.ErreurPassagere):
        ia.ClientClaudeCode("/bin/claude", "m", None, lent).envoyer("s", "t", 10, 5)

    def absent(commande: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        raise OSError("introuvable")

    with pytest.raises(ia.ErreurDefinitive):
        ia.ClientClaudeCode("/bin/claude", "m", None, absent).envoyer("s", "t", 10, 5)


def test_client_sdk_erreurs() -> None:
    import anthropic
    import httpx2 as httpx  # le SDK anthropic 1.x s'appuie sur httpx2

    class Reponse:
        def __init__(self, texte: str, stop: str = "end_turn") -> None:
            self.content = [type("B", (), {"type": "text", "text": texte})()]
            self.usage = type("U", (), {"input_tokens": 12, "output_tokens": 3})()
            self.stop_reason = stop

    def fabrique(erreur: Exception | None = None, reponse: Reponse | None = None) -> Any:
        class Messages:
            def create(self, **kw: Any) -> Any:
                if erreur is not None:
                    raise erreur
                return reponse

        class FauxAnthropic:
            def __init__(self, **kw: Any) -> None:
                assert kw["max_retries"] == 0
                self.messages = Messages()

        return FauxAnthropic

    r = ia.ClientSDK("k", "m", fabrique(reponse=Reponse("ok"))).envoyer("s", "t", 10, 5)
    assert (r.texte, r.jetons_entree, r.jetons_sortie) == ("ok", 12, 3)
    with pytest.raises(ia.ErreurDefinitive):
        ia.ClientSDK("k", "m", fabrique(reponse=Reponse("", "refusal"))).envoyer("s", "t", 10, 5)
    requete = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    for code, attendu in ((429, ia.ErreurPassagere), (529, ia.ErreurPassagere), (400, ia.ErreurDefinitive)):
        rep = httpx.Response(code, request=requete, headers={"retry-after": "3"})
        erreur = anthropic.APIStatusError("x", response=rep, body=None)
        with pytest.raises(attendu) as info:
            ia.ClientSDK("k", "m", fabrique(erreur)).envoyer("s", "t", 10, 5)
        if attendu is ia.ErreurPassagere:
            assert info.value.attendre == 3.0  # type: ignore[attr-defined]
    with pytest.raises(ia.ErreurPassagere):
        ia.ClientSDK("k", "m", fabrique(anthropic.APIConnectionError(request=requete))).envoyer("s", "t", 10, 5)


# --- Système ---------------------------------------------------------------------------------------------------------


class Imitation:
    def __init__(self, code: int = 0, sortie: str = "") -> None:
        self.appels: list[tuple[list[str], str | None]] = []
        self.code, self.sortie = code, sortie

    def __call__(self, args: Sequence[str], entree: str | None, delai: float) -> Resultat:
        self.appels.append((list(args), entree))
        return Resultat(self.code, self.sortie)


def test_systeme_commandes_construites() -> None:
    im = Imitation(sortie="Variante 2\n")
    s = Systeme(im, mac=True)
    assert s.notifier("Titre", 'Un « texte » ; " end run', "sous")
    cmd = im.appels[-1][0]
    assert cmd[:2] == ["osascript", "-e"] and cmd[-3:] == ["Titre", 'Un « texte » ; " end run', "sous"]
    assert "«" not in cmd[2] and cmd[3] == "--"  # les valeurs passent en arguments, jamais dans le script
    assert s.choisir("Anniversaire", "Choisis", "Ouvrir", ["Variante 1", "Variante 2"]) == "Variante 2"
    assert s.copier("bonjour") and im.appels[-1] == (["pbcopy"], "bonjour")
    assert s.ouvrir_messages("Joyeux anniversaire ! 🎂", "+33 6 12")
    assert im.appels[-2] == (["pbcopy"], "Joyeux anniversaire ! 🎂")
    assert im.appels[-1][0][0] == "open" and im.appels[-1][0][1].startswith("sms:+336")
    assert s.trousseau_lire("quotidien-anthropic") == "Variante 2"
    assert s.trousseau_lire("bouclier-gmail") is None  # jamais le secret d'un autre projet
    assert s.applescript("return 1").code == 0
    assert Systeme(Imitation(code=1), mac=True).choisir("t", "i", "b", ["a"]) is None
    assert Systeme(im, mac=True).choisir("t", "i", "b", []) is None


def test_systeme_hors_mac() -> None:
    im = Imitation()
    s = Systeme(im, mac=False)
    assert not s.notifier("t", "x") and not s.copier("x") and s.trousseau_lire("quotidien-x") is None
    assert s.choisir("t", "i", "b", ["a"]) is None and s.applescript("x").code == 127
    assert s.ouvrir("/tmp/x") and im.appels[-1][0][0] == "xdg-open"
    assert isinstance(s.commande_existe("ls"), bool)


def test_url_sms_et_execution_reelle() -> None:
    assert url_sms("Bonne fête & bises", "06 12 34 56 78") == "sms:0612345678&body=Bonne%20f%C3%AAte%20%26%20bises"
    assert executer_vraiment(["/bin/echo", "ok"]).sortie.strip() == "ok"
    assert executer_vraiment(["/introuvable/commande"]).code == 127
    assert executer_vraiment(["sleep", "5"], delai=0.2).code == 124
