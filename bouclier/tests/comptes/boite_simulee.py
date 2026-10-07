"""Une boîte Gmail imitée (client IMAP injectable) : les en-têtes de 60 services avec leur vérité terrain, du bruit
de lettres d'information et des mails de personnes. Elle note chaque commande reçue et se comporte comme Gmail :
un FETCH BODY[…] sans PEEK marquerait le message comme lu (\\Seen)."""

from __future__ import annotations

import datetime as dt
import random
import re
from dataclasses import dataclass, field
from email.header import Header
from email.utils import format_datetime

COMPTES = [  # (domaine d'envoi, service attendu) : vrais comptes
    ("accounts.google.com", "google"), ("email.apple.com", "apple"), ("account.microsoft.com", "microsoft"),
    ("amazon.fr", "amazon"), ("mail.instagram.com", "instagram"), ("facebookmail.com", "facebook"),
    ("x.com", "twitter"), ("linkedin.com", "linkedin"), ("vinted.fr", "vinted"), ("leboncoin.fr", "leboncoin"),
    ("doctolib.fr", "doctolib"), ("info.ameli.fr", "ameli"), ("dgfip.finances.gouv.fr", "impots"),
    ("info.labanquepostale.fr", "labanquepostale"), ("boursobank.com", "boursobank"), ("paypal.fr", "paypal"),
    ("netflix.com", "netflix"), ("spotify.com", "spotify"), ("deezer.com", "deezer"), ("sncf-connect.com", "sncf"),
    ("blablacar.fr", "blablacar"), ("airbnb.fr", "airbnb"), ("booking.com", "booking"), ("uber.com", "uber"),
    ("deliveroo.fr", "deliveroo"), ("decathlon.fr", "decathlon"), ("fnac.com", "fnac"), ("cdiscount.com", "cdiscount"),
    ("contact.orange.fr", "orange"), ("edf.fr", "edf"), ("caf.fr", "caf"), ("steampowered.com", "steam"),
    ("discord.com", "discord"), ("dropbox.com", "dropbox"), ("canva.com", "canva"), ("duolingo.com", "duolingo"),
    ("boutique-des-graines.fr", "boutique-des-graines.fr"), ("club-escalade-bdx.fr", "club-escalade-bdx.fr"),
    ("mon-imprimerie-photo.com", "mon-imprimerie-photo.com"), ("notion.so", "notion"),
]  # fmt: skip
ABONNEMENTS = [  # lettres d'information seulement
    ("news.lemonde.fr", "lemonde"), ("newsletter.sudouest.fr", "sudouest"), ("e.ikea.fr", "ikea"),
    ("mail.zalando.fr", "zalando"), ("news.sephora.fr", "sephora"), ("info.leroymerlin.fr", "leroymerlin"),
    ("emailing.carrefour.fr", "carrefour"), ("news.ouigo.com", "ouigo"), ("newsletter.allocine.fr", "allocine"),
    ("mail.backmarket.fr", "backmarket"), ("news.ticketmaster.fr", "ticketmaster"),
    ("lettre.mediapart.fr", "mediapart"),
    ("news.veepee.fr", "veepee"), ("e.kiabi.com", "kiabi"), ("info.ugc.fr", "ugc"), ("news.lidl.fr", "lidl"),
    ("courrier.jardinerie-locale.fr", "jardinerie-locale.fr"), ("news.festival-bordeaux.fr", "festival-bordeaux.fr"),
    ("newsletter.cultura.com", "cultura"), ("mail.tripadvisor.fr", "tripadvisor"),
]  # fmt: skip
SUJETS_COMPTE = [
    "Bienvenue chez {nom} !",
    "Vérifiez votre adresse e-mail",
    "Réinitialisation de votre mot de passe",
    "Nouvelle connexion à votre compte",
    "Confirmation de votre commande n°{n}",
    "Welcome to {nom}",
    "Verify your email address",
    "Reset your password",
    "New sign-in to your account",
    "Your order #{n}",
    "Votre compte a été créé",
    "Code de vérification : {n}",
    "Confirmez votre inscription",
]
SUJETS_LETTRE = [
    "Nos nouveautés de la semaine",
    "-20 % ce week-end seulement",
    "La lettre de {nom} – octobre",
    "Vos idées sorties du mois",
    "Les meilleures offres pour vous",
    "Ce qu'il ne fallait pas manquer",
]


@dataclass
class Message:
    uid: int
    entetes: bytes
    drapeaux: set[str] = field(default_factory=set)
    libelles: tuple[str, ...] = ("\\\\Inbox",)
    corps: bytes = b""


def _entetes(expediteur: str, sujet: str, date: dt.datetime, lettre: bool) -> bytes:
    # Un sujet sur deux encodé (=?utf-8?b?…?=), l'autre en UTF-8 brut : les deux existent dans une vraie boîte.
    if len(sujet) % 2:
        sujet = str(Header(sujet, "utf-8").encode())
    lignes = [f"From: {expediteur}", f"Subject: {sujet}", f"Date: {format_datetime(date)}"]
    if lettre:
        lignes.append("List-Unsubscribe: <mailto:desinscription@exemple.invalid>")
    return ("\r\n".join(lignes) + "\r\n\r\n").encode()


def generer(graine: int = 7) -> tuple[list[Message], set[str], set[str]]:
    """(messages, services qui sont des comptes, services seulement abonnés)."""
    rnd = random.Random(graine)
    messages: list[Message] = []
    debut = dt.datetime(2019, 1, 1, tzinfo=dt.UTC)

    def ajouter(expediteur: str, sujet: str, lettre: bool) -> None:
        date = debut + dt.timedelta(days=rnd.randrange(0, 2800))
        drapeaux = {"\\Seen"} if rnd.random() < 0.7 else set()
        messages.append(Message(len(messages) + 1, _entetes(expediteur, sujet, date, lettre), drapeaux))

    for domaine, _ in COMPTES:
        nom = domaine.split(".")[-2].capitalize()
        ajouter(f'"{nom}" <no-reply@{domaine}>', rnd.choice(SUJETS_COMPTE).format(nom=nom, n=rnd.randrange(10**5)),
                rnd.random() < 0.3)  # fmt: skip
        for _ in range(rnd.randrange(0, 3)):
            ajouter(f'"{nom}" <news@{domaine}>', rnd.choice(SUJETS_LETTRE).format(nom=nom), True)
    for domaine, _ in ABONNEMENTS:
        nom = domaine.split(".")[-2].capitalize()
        for _ in range(rnd.randrange(1, 4)):
            ajouter(f'"{nom}" <news@{domaine}>', rnd.choice(SUJETS_LETTRE).format(nom=nom), True)
    for i in range(25):  # des personnes : jamais des comptes
        domaine = rnd.choice(["gmail.com", "outlook.fr", "orange.fr", "free.fr"])
        sujet = rnd.choice(["Bienvenue dans la famille !", "Re: dîner samedi", "Photos des vacances"])
        ajouter(f'"Ami {i}" <ami{i}@{domaine}>', sujet, False)
    rnd.shuffle(messages)
    for i, m in enumerate(messages, 1):
        m.uid = i * 3  # des UID qui ne se suivent pas, comme chez Gmail
    return messages, {s for _, s in COMPTES}, {s for _, s in ABONNEMENTS}


class FauxImap:
    """Imitation d'`imaplib.IMAP4_SSL` pour Gmail, qui note tout."""

    def __init__(self, messages: list[Message], validite: str = "777") -> None:
        self.messages = {m.uid: m for m in messages}
        self.validite = validite
        self.commandes: list[tuple[str, ...]] = []
        self.violations: list[str] = []
        self.mot_de_passe = "bon"

    def login(self, adresse: str, mot_de_passe: str) -> tuple[str, list[bytes]]:
        import imaplib

        self.commandes.append(("LOGIN", adresse))
        if mot_de_passe != self.mot_de_passe:
            raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")
        return "OK", [b"ok"]

    def list(self) -> tuple[str, list[bytes]]:
        self.commandes.append(("LIST",))
        return "OK", [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasChildren \\Noselect) "/" "[Gmail]"',
            b'(\\All \\HasNoChildren) "/" "[Gmail]/Tous les messages"',
            b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Messages envoy&AOk-s"',
        ]

    def select(self, dossier: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        self.commandes.append(("EXAMINE" if readonly else "SELECT", dossier))
        if " " in dossier and not dossier.startswith('"'):
            self.violations.append(f"nom de dossier sans guillemets : {dossier}")
        if not readonly:
            self.violations.append(f"SELECT en écriture : {dossier}")
        return "OK", [str(len(self.messages)).encode()]

    def response(self, code: str) -> tuple[str, list[bytes]]:
        return code, [self.validite.encode()]

    def uid(self, commande: str, *args: str) -> tuple[str, list[object]]:
        self.commandes.append(("UID", commande, *args))
        if commande == "SEARCH":
            debut = int(args[1].split(":")[0])
            uids = [u for u in sorted(self.messages) if u >= debut] or [max(self.messages)]
            return "OK", [" ".join(map(str, uids)).encode()]
        if commande == "FETCH":
            uids = [int(x) for x in args[0].split(",")]
            elements = args[1]
            sortie: list[object] = []
            for u in uids:
                m = self.messages[u]
                if re.search(r"BODY\[|RFC822(?!\.SIZE|\.HEADER)", elements):
                    m.drapeaux.add("\\Seen")  # ce que ferait Gmail
                    self.violations.append(f"FETCH qui marque comme lu : {elements}")
                if "FLAGS" in elements and "BODY" not in elements:
                    drapeaux = " ".join(sorted(m.drapeaux))
                    libelles = " ".join(f'"{x}"' for x in m.libelles)
                    sortie.append(f"{u} (X-GM-LABELS ({libelles}) UID {u} FLAGS ({drapeaux}))".encode())
                else:
                    contenu = m.entetes + m.corps if "BODY.PEEK[]" in elements else m.entetes
                    sortie.append((f"{u} (UID {u} BODY[] {{{len(contenu)}}}".encode(), contenu))
                    sortie.append(b")")
            return "OK", sortie
        self.violations.append(f"UID {commande}")
        return "NO", [b"interdit"]

    def logout(self) -> tuple[str, list[bytes]]:
        self.commandes.append(("LOGOUT",))
        return "BYE", [b""]

    # Ce que Bouclier ne doit jamais appeler :
    def store(self, *a: object) -> None:
        self.violations.append("STORE")

    def copy(self, *a: object) -> None:
        self.violations.append("COPY")

    def move(self, *a: object) -> None:
        self.violations.append("MOVE")

    def expunge(self, *a: object) -> None:
        self.violations.append("EXPUNGE")
