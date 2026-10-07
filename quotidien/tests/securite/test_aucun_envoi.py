"""Aucune capacité d'envoi (§0.5, §6, §10.4) : Quotidien prépare, c'est toi qui envoies.

Recherche automatisée dans tout le code livré (Python, scripts, raccourcis, modèles) : le mot « send », un
`osascript` qui parlerait à Messages, `smtplib`, `sendmail`, un `tell application "Messages"`… Le test échoue s'il
trouve quoi que ce soit. Et les Contacts sont lus sans aucune requête d'écriture.
"""

from __future__ import annotations

import re
from pathlib import Path

from quotidien import config

RACINE = config.racine_projet()
EXTENSIONS = {".py", ".sh", ".json", ".toml", ".plist", ".applescript", ".scpt", ".shortcut", ".html", ".js"}
INTERDITS = [
    re.compile(r"\bsend\w*", re.IGNORECASE),  # send, sendmail, sendMessage…
    re.compile(r"smtplib|smtp\.", re.IGNORECASE),
    re.compile(r"application\s+\\?\"?Messages", re.IGNORECASE),
    re.compile(r"osascript[^\n]*Messages", re.IGNORECASE),
    re.compile(r"\bimessage:", re.IGNORECASE),  # ouvrir oui (sms:), mais jamais d'envoi direct
    re.compile(r"com\.apple\.(?:iChat|MobileSMS)", re.IGNORECASE),
    re.compile(r"WFSendMessageAction|is\.workflow\.actions\.sendmessage|sendemail", re.IGNORECASE),
]
ECRITURE_CONTACTS = re.compile(r"CNSaveRequest|executeSaveRequest|addContact|updateContact|deleteContact|"
                               r"CNMutableContact", re.IGNORECASE)  # fmt: skip
CE_FICHIER = Path(__file__).resolve()


def fichiers_livres() -> list[Path]:
    dossiers = [RACINE / "quotidien", RACINE / "outils", RACINE / "integrite"]
    fichiers = [f for d in dossiers for f in d.rglob("*") if f.is_file() and f.suffix in EXTENSIONS]
    fichiers += [f for f in RACINE.glob("*.sh")] + [f for f in RACINE.glob("*.toml")]
    return sorted(f for f in fichiers if "__pycache__" not in f.parts and f.resolve() != CE_FICHIER)


def test_aucune_capacite_d_envoi() -> None:
    fichiers = fichiers_livres()
    assert len(fichiers) > 40 and any(f.name == "messages.py" for f in fichiers)
    trouves = []
    for f in fichiers:
        texte = f.read_text(encoding="utf-8", errors="replace")
        for motif in INTERDITS:
            for m in motif.finditer(texte):
                ligne = texte.count("\n", 0, m.start()) + 1
                trouves.append(f"{f.relative_to(RACINE)}:{ligne} : {m.group(0)}")
    assert not trouves, "capacité d'envoi trouvée :\n" + "\n".join(trouves)


def test_la_recherche_trouverait_un_envoi(tmp_path: Path) -> None:
    """La recherche n'est pas aveugle : elle attrape chaque forme d'envoi connue."""
    pieges = [
        'tell application "Messages" to send "coucou" to buddy "x"',
        "osascript -e 'tell app \"Messages\" …'",
        "import smtplib",
        "server.sendmail(a, b, c)",
        "client.send_message(m)",
        "open imessage://x?body=y",
        "<string>is.workflow.actions.sendmessage</string>",
    ]
    for piege in pieges:
        assert any(m.search(piege) for m in INTERDITS), piege


def test_contacts_en_lecture_seule() -> None:
    for f in (RACINE / "quotidien").rglob("*.py"):
        assert not ECRITURE_CONTACTS.search(f.read_text(encoding="utf-8")), f
    assert ECRITURE_CONTACTS.search("store.executeSaveRequest_error_(req, None)")


def test_ouvrir_messages_ne_fait_qu_ouvrir() -> None:
    """La seule porte vers Messages : une URL sms: ouverte par `open`, avec le texte copié (pbcopy)."""
    from quotidien.systeme import Resultat, Systeme

    appels: list[list[str]] = []
    s = Systeme(lambda a, e, d: appels.append(list(a)) or Resultat(0, ""), mac=True)  # type: ignore[func-returns-value]
    assert s.ouvrir_messages("Bon anniversaire Léa !\nÀ très vite", "06 11 22 33 44")
    assert [a[0] for a in appels] == ["pbcopy", "open"]
    url = appels[1][1]
    assert url.startswith("sms:0611223344") and "body=Bon%20anniversaire" in url
