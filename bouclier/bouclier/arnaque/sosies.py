"""Les marques visées en France, leurs sites officiels, et la détection des sosies.

Un sosie est un nom de site qui imite une marque sans être le sien :
- il contient la marque (« colissimo-suivi-frais.top », « impots-gouv.info », « labanquepostale-securite.com ») ;
- il la déforme d'une lettre ou deux (« vintedd.fr », « ameii-sante.fr ») ;
- il remplace des lettres par des sosies visuels : « rn » pour « m » (« arneli.fr »), un « о » cyrillique, un
  accent (« colíssimo »), un chiffre (« paypa1 »).

Les domaines officiels viennent de la connaissance publique de ces marques ; tout `*.gouv.fr` est officiel pour les
administrations.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from bouclier.arnaque.texte import normaliser


@dataclass(frozen=True)
class Marque:
    id: str
    nom: str
    mots: tuple[str, ...]  # comment la marque apparaît dans un nom de site (sans tiret, minuscules)
    texte: str  # motif de la marque dans un texte normalisé (minuscules, sans accents)
    officiels: tuple[str, ...] = ()
    gouv: bool = False  # tout *.gouv.fr est officiel
    banque: bool = False
    site: str = ""  # le site officiel à donner à la personne
    motifs_officiels: tuple[str, ...] = field(default=())  # expressions régulières sur le domaine enregistrable


MARQUES: tuple[Marque, ...] = (
    # Livraison
    Marque(
        "laposte",
        "La Poste",
        ("laposte",),
        r"\bla ?poste\b|\blaposte\b",
        ("laposte.fr", "laposte.net", "laposte.com", "lapostegroupe.com", "colissimo.fr", "colissimo.com"),
        site="laposte.fr",
    ),
    Marque(
        "colissimo",
        "Colissimo",
        ("colissimo",),
        r"\bcolissimo\b",
        ("laposte.fr", "colissimo.fr", "colissimo.com", "laposte.net"),
        site="laposte.fr",
    ),
    Marque(
        "chronopost",
        "Chronopost",
        ("chronopost",),
        r"\bchronopost\b",
        ("chronopost.fr", "chronopost.com"),
        site="chronopost.fr",
    ),
    Marque("dhl", "DHL", ("dhl",), r"\bdhl\b", ("dhl.com", "dhl.fr", "dhl.de"), site="dhl.fr"),
    Marque("ups", "UPS", ("ups",), r"\bups\b", ("ups.com",), site="ups.com"),
    Marque(
        "mondialrelay",
        "Mondial Relay",
        ("mondialrelay",),
        r"\bmondial ?relay\b",
        ("mondialrelay.fr", "mondialrelay.com"),
        site="mondialrelay.fr",
    ),
    Marque(
        "amazon",
        "Amazon",
        ("amazon", "amzn"),
        r"\bamazon\b",
        (
            "amazon.fr",
            "amazon.com",
            "amazon.de",
            "amazon.es",
            "amazon.it",
            "amazon.co.uk",
            "amzn.to",
            "amzn.eu",
            "amazon.jobs",
        ),
        site="amazon.fr",
    ),
    # Administrations et services publics
    Marque(
        "ameli",
        "Ameli (Assurance Maladie)",
        ("ameli", "assurancemaladie", "cartevitale", "vitale"),
        r"\bameli\b|assurance maladie|carte vitale|\bcpam\b",
        ("ameli.fr", "assurance-maladie.fr"),
        gouv=True,
        site="ameli.fr",
    ),
    Marque(
        "impots",
        "impots.gouv (DGFiP)",
        ("impots", "impot", "dgfip"),
        r"impots?\.gouv|\bimpots?\b|\bdgfip\b|finances publiques|tresor public",
        (),
        gouv=True,
        site="impots.gouv.fr",
    ),
    Marque(
        "antai",
        "ANTAI (amendes)",
        ("antai", "amendes", "amende"),
        r"\bantai\b|amende|contravention",
        ("amendes.gouv.fr", "antai.gouv.fr"),
        gouv=True,
        site="amendes.gouv.fr",
    ),
    Marque(
        "critair",
        "Crit'Air",
        ("critair", "certificatair", "vignettecritair"),
        r"crit'? ?air",
        ("certificat-air.gouv.fr",),
        gouv=True,
        site="certificat-air.gouv.fr",
    ),
    Marque(
        "ants",
        "ANTS",
        ("ants",),
        r"\bants\b|agence nationale des titres",
        ("ants.gouv.fr",),
        gouv=True,
        site="ants.gouv.fr",
    ),
    Marque("caf", "Caf", ("caf",), r"\bcaf\b|allocations familiales", ("caf.fr",), gouv=True, site="caf.fr"),
    Marque(
        "francetravail",
        "France Travail",
        ("francetravail", "poleemploi"),
        r"france travail|pole emploi",
        ("francetravail.fr", "pole-emploi.fr"),
        gouv=True,
        site="francetravail.fr",
    ),
    Marque(
        "cpf",
        "Mon Compte Formation (CPF)",
        ("moncompteformation", "compteformation", "cpf"),
        r"\bcpf\b|compte (personnel de )?formation|moncompteformation",
        ("moncompteformation.gouv.fr",),
        gouv=True,
        site="moncompteformation.gouv.fr",
    ),
    Marque(
        "servicepublic",
        "Service-Public",
        ("servicepublic",),
        r"service-public",
        ("service-public.fr",),
        gouv=True,
        site="service-public.fr",
    ),
    Marque(
        "gouv", "un service de l'État", ("gouv",), r"\bgouv\b|\bministere\b", (), gouv=True, site="service-public.fr"
    ),
    # Banques et paiement
    Marque(
        "labanquepostale",
        "La Banque Postale",
        ("labanquepostale", "banquepostale"),
        r"la banque postale|\blbp\b|certicode",
        ("labanquepostale.fr", "labanquepostale.com"),
        banque=True,
        site="labanquepostale.fr",
    ),
    Marque(
        "creditagricole",
        "Crédit Agricole",
        ("creditagricole",),
        r"credit agricole|securipass",
        (
            "credit-agricole.fr",
            "credit-agricole.com",
            "ca-aquitaine.fr",
            "ca-paris.fr",
            "ca-pyrenees-gascogne.fr",
            "ca-charente-perigord.fr",
        ),
        banque=True,
        site="credit-agricole.fr",
    ),
    Marque(
        "societegenerale",
        "Société Générale",
        ("societegenerale",),
        r"societe generale",
        ("societegenerale.fr", "societegenerale.com", "sg.fr"),
        banque=True,
        site="societegenerale.fr",
    ),
    Marque(
        "bnp",
        "BNP Paribas",
        ("bnpparibas", "bnp"),
        r"\bbnp\b|bnp paribas",
        ("bnpparibas.com", "bnpparibas.fr", "bnpparibas.net"),
        banque=True,
        site="mabanque.bnpparibas",
        motifs_officiels=(r"(^|\.)bnpparibas$",),
    ),
    Marque("lcl", "LCL", ("lcl",), r"\blcl\b|secur'? ?pass", ("lcl.fr", "lcl.com"), banque=True, site="lcl.fr"),
    Marque(
        "caissedepargne",
        "Caisse d'Épargne",
        ("caisseepargne", "caissedepargne"),
        r"caisse d'epargne",
        ("caisse-epargne.fr",),
        banque=True,
        site="caisse-epargne.fr",
    ),
    Marque(
        "banquepopulaire",
        "Banque Populaire",
        ("banquepopulaire",),
        r"banque populaire",
        ("banquepopulaire.fr",),
        banque=True,
        site="banquepopulaire.fr",
    ),
    Marque(
        "creditmutuel",
        "Crédit Mutuel",
        ("creditmutuel",),
        r"credit mutuel",
        ("creditmutuel.fr", "creditmutuel.com"),
        banque=True,
        site="creditmutuel.fr",
    ),
    Marque("cic", "CIC", ("cic",), r"\bcic\b", ("cic.fr",), banque=True, site="cic.fr"),
    Marque(
        "boursobank",
        "Boursobank",
        ("boursobank", "boursorama", "bourso"),
        r"\bbourso(bank|rama)?\b",
        ("boursobank.com", "boursorama.com", "boursorama-banque.com"),
        banque=True,
        site="boursobank.com",
    ),
    Marque(
        "hellobank", "Hello bank!", ("hellobank",), r"hello ?bank", ("hellobank.fr",), banque=True, site="hellobank.fr"
    ),
    Marque("fortuneo", "Fortuneo", ("fortuneo",), r"\bfortuneo\b", ("fortuneo.fr",), banque=True, site="fortuneo.fr"),
    Marque("monabanq", "Monabanq", ("monabanq",), r"\bmonabanq\b", ("monabanq.com",), banque=True, site="monabanq.com"),
    Marque(
        "paypal",
        "PayPal",
        ("paypal",),
        r"\bpaypal\b",
        ("paypal.com", "paypal.fr", "paypal.me", "paypalobjects.com"),
        banque=True,
        site="paypal.com",
    ),
    Marque("n26", "N26", ("n26",), r"\bn26\b", ("n26.com",), banque=True, site="n26.com"),
    Marque("revolut", "Revolut", ("revolut",), r"\brevolut\b", ("revolut.com",), banque=True, site="revolut.com"),
    # Annonces
    Marque("vinted", "Vinted", ("vinted",), r"\bvinted\b", ("vinted.fr", "vinted.com", "vinted.net"), site="vinted.fr"),
    Marque(
        "leboncoin",
        "Leboncoin",
        ("leboncoin", "lbc"),
        r"\ble ?bon ?coin\b|\blbc\b",
        ("leboncoin.fr", "leboncoin.com", "leboncoin.info"),
        site="leboncoin.fr",
    ),
    # Comptes en ligne, abonnements, énergie, télécoms
    Marque("netflix", "Netflix", ("netflix",), r"\bnetflix\b", ("netflix.com", "netflix.net"), site="netflix.com"),
    Marque(
        "apple",
        "Apple",
        ("apple", "icloud", "appleid"),
        r"\bapple\b|\bicloud\b|identifiant apple",
        ("apple.com", "icloud.com", "me.com", "apple.fr"),
        site="apple.com",
    ),
    Marque(
        "microsoft",
        "Microsoft",
        ("microsoft", "office365", "outlook", "hotmail", "windows"),
        r"\bmicrosoft\b|\bwindows\b|\boffice ?365\b|\boutlook\b",
        (
            "microsoft.com",
            "live.com",
            "outlook.com",
            "outlook.fr",
            "hotmail.com",
            "hotmail.fr",
            "live.fr",
            "office.com",
            "microsoftonline.com",
            "windows.com",
            "office365.com",
            "msn.com",
        ),
        site="microsoft.com",
    ),
    Marque(
        "google",
        "Google",
        ("google",),
        r"\bgoogle\b|\bgmail\b",
        ("google.com", "google.fr", "gmail.com", "googlemail.com", "youtube.com", "goo.gl", "g.co"),
        site="google.com",
    ),
    Marque("orange", "Orange", ("orange",), r"\borange\b", ("orange.fr", "orange.com", "sosh.fr"), site="orange.fr"),
    Marque("sfr", "SFR", ("sfr",), r"\bsfr\b", ("sfr.fr", "sfr.com", "red-by-sfr.fr"), site="sfr.fr"),
    Marque(
        "free",
        "Free",
        ("free", "freemobile", "freebox"),
        r"\bfree( mobile)?\b|\bfreebox\b",
        ("free.fr", "free-mobile.fr"),
        site="free.fr",
    ),
    Marque(
        "bouygues",
        "Bouygues Telecom",
        ("bouygues", "bouyguestelecom"),
        r"\bbouygues\b",
        ("bouyguestelecom.fr", "bouygues-telecom.fr"),
        site="bouyguestelecom.fr",
    ),
    Marque("edf", "EDF", ("edf",), r"\bedf\b", ("edf.fr", "edf.com"), site="edf.fr"),
    Marque("engie", "Engie", ("engie",), r"\bengie\b", ("engie.fr", "engie.com"), site="engie.fr"),
    Marque(
        "sncf",
        "SNCF",
        ("sncf",),
        r"\bsncf\b",
        ("sncf.com", "sncf.fr", "sncf-connect.com", "sncf-voyageurs.com"),
        site="sncf-connect.com",
        motifs_officiels=(r"(^|\.)sncf$",),
    ),
    Marque("ouigo", "Ouigo", ("ouigo",), r"\bouigo\b", ("ouigo.com",), site="ouigo.com"),
    # Santé, commerce, loisirs (marques souvent imitées, et sites que la personne utilise)
    Marque("doctolib", "Doctolib", ("doctolib",), r"\bdoctolib\b", ("doctolib.fr", "doctolib.com"), site="doctolib.fr"),
    Marque(
        "cdiscount",
        "Cdiscount",
        ("cdiscount",),
        r"\bcdiscount\b",
        ("cdiscount.com", "cdiscount.fr"),
        site="cdiscount.com",
    ),
    Marque("fnac", "Fnac", ("fnac",), r"\bfnac\b", ("fnac.com", "fnac.fr", "fnac-darty.com"), site="fnac.com"),
    Marque("darty", "Darty", ("darty",), r"\bdarty\b", ("darty.com", "darty.fr", "fnac-darty.com"), site="darty.com"),
    Marque(
        "decathlon",
        "Decathlon",
        ("decathlon",),
        r"\bdecathlon\b",
        ("decathlon.fr", "decathlon.com"),
        site="decathlon.fr",
    ),
    Marque("spotify", "Spotify", ("spotify",), r"\bspotify\b", ("spotify.com",), site="spotify.com"),
    Marque(
        "disney",
        "Disney+",
        ("disneyplus",),
        r"\bdisney ?\+|\bdisney ?plus\b",
        ("disneyplus.com", "disney.fr", "disney.com"),
        site="disneyplus.com",
    ),
    Marque(
        "canal",
        "Canal+",
        ("canalplus", "mycanal"),
        r"\bcanal ?\+|\bcanal ?plus\b|\bmycanal\b",
        ("canalplus.com", "canal-plus.com", "mycanal.fr"),
        site="canalplus.com",
    ),
    Marque(
        "totalenergies",
        "TotalEnergies",
        ("totalenergies",),
        r"\btotal ?energies\b",
        ("totalenergies.fr", "totalenergies.com"),
        site="totalenergies.fr",
    ),
)

PAR_ID = {m.id: m for m in MARQUES}

# Sosies visuels : caractères étrangers ou chiffres qui ressemblent à des lettres latines.
_HOMOGLYPHES = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "і": "i", "ј": "j", "ѕ": "s",
        "ԁ": "d", "ɡ": "g", "һ": "h", "ӏ": "l", "ո": "n", "ս": "u", "ν": "v", "ο": "o", "α": "a", "τ": "t",
        "ι": "i", "κ": "k", "м": "m", "т": "t", "в": "b", "н": "h", "к": "k", "ł": "l", "ø": "o", "đ": "d",
        "0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s",
    }
)  # fmt: skip


def decoder_idn(hote: str) -> str:
    """« xn--colssimo-… » → « colíssimo » (le nom tel qu'il s'affiche)."""
    morceaux = []
    for label in hote.split("."):
        if label.startswith("xn--"):
            try:
                morceaux.append(label.encode("ascii").decode("idna"))
                continue
            except (UnicodeError, ValueError):
                pass
        morceaux.append(label)
    return ".".join(morceaux)


def squelette(texte: str) -> str:
    """La forme que l'œil lit : sans accents, sosies visuels remplacés, « rn » → « m », « vv » → « w »."""
    t = unicodedata.normalize("NFKC", texte.lower()).translate(_HOMOGLYPHES)
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return t.replace("rn", "m").replace("vv", "w")


def distance(a: str, b: str) -> int:
    """Distance de Damerau-Levenshtein (transpositions comprises), bornée à 3 pour aller vite."""
    if abs(len(a) - len(b)) > 2:
        return 3
    precedente2: list[int] = []
    precedente = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        courante = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cout = 0 if ca == cb else 1
            courante[j] = min(precedente[j] + 1, courante[j - 1] + 1, precedente[j - 1] + cout)
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                courante[j] = min(courante[j], precedente2[j - 2] + 1)
        precedente2, precedente = precedente, courante
    return min(precedente[-1], 3)


def est_officiel(domaine: str, hote: str, marque: Marque) -> bool:
    d = domaine.lower()
    if d in marque.officiels or any(re.search(m, d) for m in marque.motifs_officiels):
        return True
    return marque.gouv and (hote.lower().endswith(".gouv.fr") or hote.lower() == "gouv.fr")


def officiel_pour_une_marque(domaine: str, hote: str) -> Marque | None:
    for m in MARQUES:
        if m.id != "gouv" and est_officiel(domaine, hote, m):
            return m
    return None


@dataclass(frozen=True)
class Sosie:
    marque: Marque
    maniere: str  # "contient", "deforme", "caracteres"


# Mots courants trop proches d'une marque pour la règle « déformée d'une lettre » (« email » ≈ « gmail »).
MOTS_COURANTS = frozenset(
    {"email", "emails", "mail", "mails", "online", "service", "services", "secure", "login", "compte", "account",
     "client", "clients", "orage", "apply", "engine", "amazone", "vintage", "colis", "news", "infos", "ample",
     "party", "parts", "dirty", "dorty"}
)  # fmt: skip


def _jetons(label: str) -> list[str]:
    return [j for j in re.split(r"[-_]", label) if j]


@lru_cache(maxsize=4096)
def sosie(domaine: str, hote: str) -> Sosie | None:
    """Le site imite-t-il une marque dont il n'est pas un site officiel ?"""
    if hote.lower().endswith(".gouv.fr") or officiel_pour_une_marque(domaine, hote) is not None:
        return None
    affiche = decoder_idn(hote.lower())
    non_ascii = any(ord(c) > 127 for c in affiche)
    labels = affiche.split(".")
    # On regarde le nom enregistré et les sous-domaines (« mondialrelay-pointrelais.fr.colis-info.com ») ;
    # la règle « déformée d'une lettre » ne regarde que le nom enregistré (les sous-domaines sont des mots courants).
    candidats: list[str] = list(labels[:-1] or labels)
    nb_labels_domaine = max(1, len(domaine.split(".")) - 1)
    enregistre = (
        decoder_idn(".".join(labels[-(nb_labels_domaine + 1) :])).split(".")[0] if len(labels) > 1 else labels[0]
    )
    tout = "".join(lab.replace("-", "") for lab in labels[:-1])
    for marque in MARQUES:
        if est_officiel(domaine, hote, marque):
            continue
        for mot in marque.mots:
            court = len(mot) <= 4
            for label in candidats:
                jetons = _jetons(label)
                compact = label.replace("-", "")
                sq_compact = squelette(compact)
                if court:
                    if mot in jetons or (non_ascii and mot in [squelette(j) for j in jetons]):
                        return Sosie(marque, "caracteres" if non_ascii and mot not in jetons else "contient")
                    continue
                if mot in compact:
                    return Sosie(marque, "deforme" if distance(compact, mot) == 1 else "contient")
                if non_ascii and mot in sq_compact:
                    return Sosie(marque, "caracteres")
                if mot in sq_compact and sq_compact != compact:
                    return Sosie(marque, "caracteres")
                if label != enregistre:
                    continue
                for j in [*jetons, compact]:
                    if j in MOTS_COURANTS:
                        continue
                    sq = squelette(j)
                    seuil = 1 if len(mot) < 9 else 2
                    if len(mot) >= 5 and sq != mot and 0 < distance(sq, mot) <= seuil and abs(len(sq) - len(mot)) <= 1:
                        return Sosie(marque, "deforme")
                    if len(mot) >= 5 and sq == mot and j != mot:
                        return Sosie(marque, "caracteres")
            if not court and mot in tout:
                return Sosie(marque, "contient")
    return None


@lru_cache(maxsize=2048)
def _motif(texte: str) -> re.Pattern[str]:
    return re.compile(texte)


def marques_citees(texte: str) -> list[Marque]:
    """Les marques nommées dans un texte (dans l'ordre de leur première apparition)."""
    t = normaliser(texte)
    trouvees: list[tuple[int, Marque]] = []
    for m in MARQUES:
        if m.id == "gouv":
            continue
        r = _motif(m.texte).search(t)
        if r:
            trouvees.append((r.start(), m))
    trouvees.sort(key=lambda x: x[0])
    return [m for _, m in trouvees]
