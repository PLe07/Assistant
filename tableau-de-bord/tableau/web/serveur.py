"""Le serveur de la page locale : 127.0.0.1 seulement, jeton obligatoire, lecture seule sauf trois actions en POST.

Pages : `/` (accueil), `/module/<id>` (détail, `?jours=30`), `/credits`, `/ressources`, `/integrite`, `/journal`.
Fragments (mise à jour en direct) : `/fragment/…` (même chemin). Données : `/api/etat`, `/api/module/<id>`.
Direct : `/evenements` (SSE). Fichiers : `/static/app.css`, `/static/app.js`.
Actions (POST, jeton dans l'adresse **et** dans `X-Jeton`, corps JSON) :
`/action/reference/<id>`, `/action/pas-normal/<id>`, `/action/sourdine` (`{"duree": "1h"}`),
`/action/diagnostic/<id>` (la commande de diagnostic du module, seulement sur ton clic).

Le port : celui des réglages (47615) s'il est libre, sinon le premier libre de 47616 à 47639, retenu dans les
réglages. Aucun journal des requêtes (les adresses contiennent le jeton).
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable
from functools import cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from tableau import config, systeme, vues
from tableau.web import rendu, securite, sse

STATIQUES = {"app.css": "text/css; charset=utf-8", "app.js": "text/javascript; charset=utf-8"}
CORPS_MAX = 4096
VUES_TRANSVERSES = ("credits", "ressources", "integrite", "journal")


@cache
def _statique(nom: str) -> bytes:
    return (Path(__file__).resolve().parent / "static" / nom).read_bytes()


class Gestionnaire(BaseHTTPRequestHandler):
    server: Serveur
    protocol_version = "HTTP/1.1"
    timeout = 15
    server_version = "TableauDeBord"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - signature imposée
        """Rien : les adresses portent le jeton, elles ne doivent apparaître dans aucun journal."""

    # --- réponses ----------------------------------------------------------------------------------------------------

    def _envoyer(self, code: int, corps: bytes, type_: str, entetes: dict[str, str] | None = None) -> None:
        self.send_response(code)
        for nom, valeur in {**securite.ENTETES, **(entetes or {})}.items():
            self.send_header(nom, valeur)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corps)

    def _html(self, texte: str, code: int = 200) -> None:
        self._envoyer(code, texte.encode(), "text/html; charset=utf-8")

    def _json(self, donnees: Any, code: int = 200) -> None:
        self._envoyer(code, json.dumps(donnees, ensure_ascii=False, default=str).encode(), "application/json")

    def _refus(self, code: int, motif: str) -> None:
        if self.command == "POST":
            self._json({"ok": False, "message": motif}, code)
        else:
            self._html(rendu.erreur(code, motif), code)

    # --- la porte ----------------------------------------------------------------------------------------------------

    def _porte(self) -> bool:
        entetes = {nom: self.headers.get(nom) or "" for nom in securite.ENTETES_LUES if nom in self.headers}
        v = securite.verifier(self.command, self.path, entetes, self.server.jeton, self.server.port)
        if not v.ok:
            self.server.refus += 1
            self._refus(v.code, v.motif)
        return v.ok

    def do_GET(self) -> None:  # noqa: N802 - nom imposé
        if not self._porte():
            return
        try:
            self._get()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:  # noqa: BLE001 - la page ne fait jamais tomber le démon
            self.server.erreurs += 1
            self._html(rendu.erreur(500, "Erreur interne : le détail est dans le journal du tableau de bord."), 500)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if not self._porte():
            return
        try:
            self._post()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:  # noqa: BLE001
            self.server.erreurs += 1
            self._json({"ok": False, "message": "Erreur interne."}, 500)

    def _refuser_autre(self) -> None:
        self._refus(405, "méthode refusée")

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _refuser_autre  # noqa: N815

    # --- GET -----------------------------------------------------------------------------------------------------

    def _get(self) -> None:
        url = urlsplit(self.path)
        chemin = unquote(url.path)
        params = parse_qs(url.query)
        source = self.server.source
        jeton = self.server.jeton
        if chemin.startswith("/static/"):
            nom = chemin[len("/static/") :]
            if nom not in STATIQUES:
                return self._refus(404, "introuvable")
            return self._envoyer(200, _statique(nom), STATIQUES[nom])
        if chemin == "/evenements":
            return self._flux()
        if chemin == "/api/etat":
            return self._json(vues.accueil(source))
        if chemin.startswith("/api/module/"):
            d = vues.detail(source, chemin[len("/api/module/") :], _jours(params))
            return self._json(d) if d else self._refus(404, "module inconnu")
        fragment = chemin.startswith("/fragment/")
        base = "/" + chemin[len("/fragment/") :] if fragment else chemin
        rendu_ = self._dessiner(base, params)
        if rendu_ is None:
            return self._refus(404, "page introuvable")
        titre, contenu, actif = rendu_
        if fragment:
            return self._html(contenu)
        adresse_fragment = rendu.lien("/fragment" + (base if base != "/" else "/accueil"), jeton, **_garder(params))
        self._html(rendu.page(titre, contenu, jeton, adresse_fragment, actif))

    def _dessiner(self, chemin: str, params: dict[str, list[str]]) -> tuple[str, str, str] | None:
        source = self.server.source
        jeton = self.server.jeton
        if chemin in ("/", "/accueil"):
            return "Accueil", rendu.fragment_accueil(vues.accueil(source), jeton), "/"
        if chemin.startswith("/module/"):
            d = vues.detail(source, chemin[len("/module/") :], _jours(params))
            if d is None:
                return None
            return d["carte"]["nom"], rendu.fragment_module(d, jeton), "/"
        if chemin == "/credits":
            return "Crédits", rendu.fragment_credits(vues.vue_credits(source), jeton), chemin
        if chemin == "/ressources":
            return "Ressources", rendu.fragment_ressources(vues.vue_ressources(source), jeton), chemin
        if chemin == "/integrite":
            return "Intégrité", rendu.fragment_integrite(vues.vue_integrite(source), jeton), chemin
        if chemin == "/journal":
            demande = (params.get("module") or [""])[0]
            module = demande if demande in source.defs or demande == "tableau" else None
            modules = sorted(((d.id, d.nom) for d in source.defs.values()), key=lambda x: x[1].lower())
            return "Journal", rendu.fragment_journal(vues.journal(source, module), modules, module, jeton), chemin
        return None

    def _flux(self) -> None:
        if self.command == "HEAD":
            return self._envoyer(200, b"", "text/event-stream; charset=utf-8")
        diffuseur = self.server.source.diffuseur
        if not diffuseur.entrer():
            return self._refus(503, "trop de pages ouvertes")
        try:
            self.send_response(200)
            for nom, valeur in securite.ENTETES.items():
                self.send_header(nom, valeur)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            vue = diffuseur.version
            self.wfile.write(b"retry: 5000\n\n" + sse.message("maj", str(vue)))
            self.wfile.flush()
            while not diffuseur.ferme and not self.server.arret.is_set():
                version = diffuseur.attendre(vue, self.server.battement_s)
                if version > vue:
                    vue = version
                    self.wfile.write(sse.message("maj", str(vue)))
                else:
                    self.wfile.write(sse.BATTEMENT)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            pass
        finally:
            diffuseur.sortir()

    # --- POST ----------------------------------------------------------------------------------------------------

    def _post(self) -> None:
        try:
            longueur = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            longueur = -1
        if longueur < 0:
            return self._refus(400, "longueur du corps illisible")
        if longueur > CORPS_MAX:
            return self._refus(413, "corps trop long")
        try:
            corps = json.loads(self.rfile.read(longueur) or b"{}") if longueur else {}
        except ValueError:
            return self._refus(400, "corps JSON illisible")
        if not isinstance(corps, dict):
            return self._refus(400, "corps JSON illisible")
        chemin = unquote(urlsplit(self.path).path)
        source = self.server.source
        try:
            if chemin.startswith("/action/reference/"):
                return self._json(
                    {"ok": True, "message": source.nouvelle_reference(chemin[len("/action/reference/") :])}
                )
            if chemin.startswith("/action/pas-normal/"):
                return self._json({"ok": True, **source.pas_normal(chemin[len("/action/pas-normal/") :])})
            if chemin == "/action/sourdine":
                return self._json({"ok": True, "message": source.sourdine(str(corps.get("duree", "1h")))})
            if chemin.startswith("/action/diagnostic/"):
                module = chemin[len("/action/diagnostic/") :]
                d = source.diagnostic(module, systeme.DemandeExplicite("page", module))
                return self._json({"message": "Diagnostic terminé." if d["ok"] else "Diagnostic : échec.", **d})
        except KeyError:
            return self._refus(404, "module inconnu")
        except ValueError as e:
            return self._refus(400, str(e))
        return self._refus(404, "action inconnue")


def _jours(params: dict[str, list[str]]) -> int:
    return 30 if (params.get("jours") or ["7"])[0] == "30" else 7


def _garder(params: dict[str, list[str]]) -> dict[str, str]:
    return {k: v[0] for k, v in params.items() if k in ("jours", "module") and v}


class Serveur(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, source: vues.Source, jeton: str, port: int, battement_s: float = sse.BATTEMENT_S) -> None:
        self.source = source
        self.jeton = jeton
        self.battement_s = battement_s
        self.arret = threading.Event()
        self.refus = 0
        self.erreurs = 0
        super().__init__(("127.0.0.1", port), Gestionnaire)
        self.port = int(self.server_address[1])
        self._fil: threading.Thread | None = None

    def server_bind(self) -> None:
        # Jamais SO_REUSEADDR : un port déjà pris doit l'être vraiment pour nous aussi.
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        super().server_bind()

    def demarrer(self) -> Serveur:
        self._fil = threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.5}, name="page", daemon=True)
        self._fil.start()
        return self

    def arreter(self) -> None:
        self.arret.set()
        self.source.diffuseur.fermer()
        self.shutdown()
        self.server_close()
        if self._fil is not None:
            self._fil.join(timeout=5)

    @property
    def adresse(self) -> str:
        return rendu.lien(f"http://127.0.0.1:{self.port}/", self.jeton)


def ouvrir(
    source: vues.Source,
    jeton: str,
    port_souhaite: int,
    retenir: Callable[[int], None] | None = None,
    ports_de_repli: range = config.PORTS_DE_REPLI,
) -> Serveur:
    """Le serveur sur le port souhaité, ou le premier libre des ports de repli (retenu par `retenir`)."""
    derniere: OSError | None = None
    for port in [port_souhaite, *[p for p in ports_de_repli if p != port_souhaite]]:
        try:
            serveur = Serveur(source, jeton, port)
        except OSError as e:
            derniere = e
            continue
        if port != port_souhaite and retenir is not None:
            retenir(port)
        return serveur
    raise OSError(f"aucun port libre pour la page locale ({derniere})")
