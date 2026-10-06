"""Les ingrédients du corpus : des émetteurs, des produits, des personnes et des numéros, tous inventés.

Les IBAN, numéros de sécurité sociale et numéros de carte ont des clés de contrôle valides (ce qu'un vrai document
contiendrait), pour éprouver le caviardage ; aucun n'appartient à quelqu'un.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Emetteur:
    nom: str  # le nom attendu (celui de la base des émetteurs quand il y est)
    entete: str  # comment il s'écrit en haut du document
    adresse: str
    domaine: str
    siret: str = ""
    tva: str = ""
    connu: bool = True  # dans la base embarquée du Trieur ?


def _siret(r: random.Random) -> str:
    """Un SIRET au format valide (clé de Luhn), inventé."""
    while True:
        chiffres = "".join(str(r.randint(0, 9)) for _ in range(14))
        if luhn_ok(chiffres):
            return f"{chiffres[:3]} {chiffres[3:6]} {chiffres[6:9]} {chiffres[9:]}"


def luhn_ok(chiffres: str) -> bool:
    total = 0
    for i, c in enumerate(reversed(chiffres)):
        n = int(c)
        if i % 2:
            n = n * 2 - 9 if n * 2 > 9 else n * 2
        total += n
    return total % 10 == 0


def carte(r: random.Random) -> str:
    """Un numéro de carte bancaire au format valide (Luhn), inventé."""
    base = "4" + "".join(str(r.randint(0, 9)) for _ in range(14))
    for d in range(10):
        if luhn_ok(base + str(d)):
            return base + str(d)
    raise AssertionError


def iban(r: random.Random) -> str:
    """Un IBAN français au format valide (clé RIB et clé ISO 7064), inventé."""
    banque, guichet = f"{r.randint(10000, 99999)}", f"{r.randint(10000, 99999)}"
    compte = "".join(str(r.randint(0, 9)) for _ in range(11))
    cle_rib = 97 - ((89 * int(banque) + 15 * int(guichet) + 3 * int(compte)) % 97)
    bban = f"{banque}{guichet}{compte}{cle_rib:02d}"
    numerique = "".join(str(int(c, 36)) for c in bban + "FR00")
    cle = 98 - int(numerique) % 97
    brut = f"FR{cle:02d}{bban}"
    return " ".join(brut[i : i + 4] for i in range(0, len(brut), 4))


def iban_ok(texte: str) -> bool:
    brut = texte.replace(" ", "").upper()
    numerique = "".join(str(int(c, 36)) for c in brut[4:] + brut[:4])
    return int(numerique) % 97 == 1


def nir(r: random.Random) -> str:
    """Un numéro de sécurité sociale au format valide (clé 97), inventé."""
    corps = f"{r.choice('12')}{r.randint(60, 99):02d}{r.randint(1, 12):02d}{r.randint(1, 95):02d}{r.randint(1, 999):03d}{r.randint(1, 999):03d}"
    cle = 97 - int(corps) % 97
    return f"{corps[0]} {corps[1:3]} {corps[3:5]} {corps[5:7]} {corps[7:10]} {corps[10:13]} {cle:02d}"


PRENOMS = ["Camille", "Louis", "Inès", "Hugo", "Léa", "Jules", "Chloé", "Nathan", "Manon", "Arthur", "Zoé", "Adam"]
NOMS = ["Moreau", "Lefèvre", "Girard", "Bonnet", "Dupont", "Lambert", "Fontaine", "Rousseau", "Vincent", "Muller"]
RUES = ["rue des Lilas", "avenue de la République", "boulevard Voltaire", "rue Victor Hugo", "impasse des Tilleuls",
        "rue du Moulin", "place de la Mairie", "chemin des Vignes", "allée des Peupliers"]  # fmt: skip
VILLES = [("75011", "Paris"), ("69003", "Lyon"), ("33000", "Bordeaux"), ("31000", "Toulouse"), ("44000", "Nantes"),
          ("59000", "Lille"), ("67000", "Strasbourg"), ("13006", "Marseille"), ("35000", "Rennes")]  # fmt: skip


@dataclass
class Personne:
    prenom: str
    nom: str
    adresse: str
    ville: str
    courriel: str
    telephone: str
    iban: str
    nir: str
    carte: str
    lignes: list[str] = field(default_factory=list)


def personne(r: random.Random) -> Personne:
    prenom, nom = r.choice(PRENOMS), r.choice(NOMS)
    cp, ville = r.choice(VILLES)
    adresse = f"{r.randint(1, 120)} {r.choice(RUES)}"
    p = Personne(prenom, nom, adresse, f"{cp} {ville}",
                 f"{prenom.lower()}.{nom.lower().replace('è', 'e').replace('ü', 'u')}@exemple-mail.fr",
                 f"06 {r.randint(10, 99)} {r.randint(10, 99)} {r.randint(10, 99)} {r.randint(10, 99)}",
                 iban(r), nir(r), carte(r))  # fmt: skip
    p.lignes = [f"{prenom} {nom}".upper() if r.random() < 0.3 else f"{prenom} {nom}", adresse, p.ville]
    return p


def _e(nom: str, entete: str, adresse: str, domaine: str, r: random.Random, connu: bool = True) -> Emetteur:
    s = _siret(r)
    tva = f"FR{r.randint(10, 99)}{s.replace(' ', '')[:9]}"
    return Emetteur(nom, entete, adresse, domaine, s, tva, connu)


def emetteurs(r: random.Random) -> dict[str, list[Emetteur]]:
    """Par famille. Les noms attendus sont ceux de la base des émetteurs du Trieur."""
    return {
        "commerce": [
            _e("Fnac", "FNAC", "Fnac Paris Ternes · 26-30 avenue des Ternes · 75017 Paris", "fnac.com", r),
            _e("Darty", "DARTY", "Darty Bordeaux Lac · 33300 Bordeaux", "darty.com", r),
            _e("Boulanger", "Boulanger", "Boulanger Lille · 59000 Lille", "boulanger.com", r),
            _e("Decathlon", "DECATHLON", "Decathlon Nantes Atout Sud · 44400 Rezé", "decathlon.fr", r),
            _e("Leroy Merlin", "LEROY MERLIN", "Leroy Merlin Toulouse · 31200 Toulouse", "leroymerlin.fr", r),
            _e("Ikea", "IKEA", "IKEA Lyon Saint-Priest · 69800 Saint-Priest", "ikea.com", r),
            _e("Castorama", "Castorama", "Castorama Rennes · 35000 Rennes", "castorama.fr", r),
        ],
        "ecommerce": [
            _e(
                "Amazon",
                "amazon.fr",
                "Amazon EU S.à r.l. · 38 avenue John F. Kennedy · L-1855 Luxembourg",
                "amazon.fr",
                r,
            ),  # fmt: skip
            _e(
                "Cdiscount", "Cdiscount", "Cdiscount SA · 120-126 quai de Bacalan · 33000 Bordeaux", "cdiscount.com", r
            ),  # fmt: skip
            _e("Apple", "Apple", "Apple Distribution International · Hollyhill · Cork · Irlande", "apple.com", r),
            _e("Back Market", "Back Market", "Back Market · 12 rue d'Hauteville · 75010 Paris", "backmarket.fr", r),
        ],
        "supermarche": [
            _e("Carrefour", "CARREFOUR", "Carrefour Market · 75011 Paris", "carrefour.fr", r),
            _e("E.Leclerc", "E.LECLERC", "E.Leclerc · 33700 Mérignac", "e.leclerc", r),
            _e("Monoprix", "MONOPRIX", "Monoprix République · 75003 Paris", "monoprix.fr", r),
        ],
        "energie": [
            _e("EDF", "EDF", "EDF · Service Clients · TSA 20012 · 41975 Blois Cedex 9", "edf.fr", r),
            _e("Engie", "ENGIE", "ENGIE · TSA 31519 · 75901 Paris Cedex 15", "engie.fr", r),
            _e(
                "TotalEnergies",
                "TotalEnergies",
                "TotalEnergies Électricité et Gaz France · 92400 Courbevoie",
                "totalenergies.fr",
                r,
            ),  # fmt: skip
        ],
        "telecom": [
            _e("Orange", "orange", "Orange · Service Clients · 33734 Bordeaux Cedex 9", "orange.fr", r),
            _e("SFR", "SFR", "SFR · TSA 30103 · 69947 Lyon Cedex 20", "sfr.fr", r),
            _e("Free", "free", "Free · 75371 Paris Cedex 08", "free.fr", r),
            _e(
                "Bouygues Telecom",
                "BOUYGUES TELECOM",
                "Bouygues Telecom · 60436 Noailles Cedex",
                "bouyguestelecom.fr",
                r,
            ),  # fmt: skip
        ],
        "banque": [
            _e("BNP Paribas", "BNP PARIBAS", "BNP Paribas · Agence Paris République", "mabanque.bnpparibas", r),
            _e(
                "Société Générale",
                "SOCIETE GENERALE",
                "Société Générale · Agence Lyon Part-Dieu",
                "societegenerale.fr",
                r,
            ),  # fmt: skip
            _e(
                "Crédit Agricole",
                "Crédit Agricole",
                "Crédit Agricole Aquitaine · 33000 Bordeaux",
                "credit-agricole.fr",
                r,
            ),  # fmt: skip
            _e("LCL", "LCL", "LCL · Agence Toulouse Capitole", "lcl.fr", r),
            _e(
                "La Banque Postale",
                "La Banque Postale",
                "La Banque Postale · Centre financier de Nantes",
                "labanquepostale.fr",
                r,
            ),  # fmt: skip
        ],
        "impots": [
            _e(
                "Impôts",
                "DIRECTION GÉNÉRALE DES FINANCES PUBLIQUES",
                "Centre des Finances Publiques",
                "impots.gouv.fr",
                r,
            )
        ],  # fmt: skip
        "social": [
            _e("CAF", "Caisse d'Allocations Familiales", "CAF de la Gironde · 33085 Bordeaux Cedex", "caf.fr", r)
        ],  # fmt: skip
        "sante": [
            _e("Ameli", "l'Assurance Maladie", "CPAM de Paris · 75948 Paris Cedex 19", "ameli.fr", r),
            _e("MGEN", "MGEN", "MGEN · Section de Paris", "mgen.fr", r),
            _e(
                "Harmonie Mutuelle", "Harmonie Mutuelle", "Harmonie Mutuelle · 75015 Paris", "harmonie-mutuelle.fr", r
            ),  # fmt: skip
        ],
        "assurance": [
            _e("MAIF", "MAIF", "MAIF · 79018 Niort Cedex 9", "maif.fr", r),
            _e("AXA", "AXA", "AXA France IARD · 92727 Nanterre Cedex", "axa.fr", r),
            _e("MACIF", "MACIF", "MACIF · 79037 Niort Cedex 9", "macif.fr", r),
        ],
        "transport": [
            _e("SNCF", "SNCF Connect", "SNCF Voyageurs · 93200 Saint-Denis", "sncf-connect.com", r),
            _e("Air France", "AIR FRANCE", "Air France · 95747 Roissy CDG Cedex", "airfrance.fr", r),
            _e("BlaBlaCar", "BlaBlaCar", "Comuto SA · 75009 Paris", "blablacar.fr", r),
        ],
        "hebergement": [
            _e("Booking.com", "Booking.com", "Booking.com B.V. · Amsterdam", "booking.com", r),
            _e("Airbnb", "airbnb", "Airbnb Ireland UC · Dublin", "airbnb.fr", r),
        ],
        "immobilier": [_e("Foncia", "FONCIA", "Foncia Lyon · 69006 Lyon", "foncia.com", r)],
    }


@dataclass(frozen=True)
class Produit:
    libelle: str
    marque: str
    prix: float
    durable: bool


DURABLES = [
    Produit("Casque Sony WH-1000XM6", "Sony", 249.99, True),
    Produit('Téléviseur Samsung QLED 55"', "Samsung", 699.00, True),
    Produit("Lave-linge Bosch Série 6 9 kg", "Bosch", 549.99, True),
    Produit("Ordinateur portable Lenovo IdeaPad 5", "Lenovo", 799.00, True),
    Produit("Aspirateur Dyson V15 Detect", "Dyson", 599.00, True),
    Produit("Enceinte JBL Flip 6", "JBL", 129.99, True),
    Produit("Console Nintendo Switch OLED", "Nintendo", 319.99, True),
    Produit("Montre Garmin Forerunner 265", "Garmin", 449.99, True),
    Produit("Perceuse-visseuse Makita 18 V", "Makita", 189.90, True),
    Produit("Vélo électrique Riverside 520 E", "Riverside", 1299.00, True),
    Produit("Réfrigérateur LG combiné 384 L", "LG", 899.00, True),
    Produit("Machine à café Delonghi Magnifica", "Delonghi", 379.99, True),
    Produit("Imprimante HP OfficeJet Pro 9010", "HP", 179.99, True),
    Produit("Canapé 3 places Friheten", "Ikea", 549.00, True),
    Produit("iPhone 17 128 Go", "Apple", 969.00, True),
    Produit("MacBook Air 13 pouces M4", "Apple", 1199.00, True),
    Produit("Micro-ondes Whirlpool 25 L", "Whirlpool", 119.99, True),
    Produit("Appareil photo Fujifilm X-T30 II", "Fujifilm", 899.00, True),
]
CONSOMMABLES = [
    Produit("Cartouches d'encre HP 963 XL (pack de 4)", "HP", 89.99, False),
    Produit("Piles alcalines AA (lot de 24)", "Duracell", 17.99, False),
    Produit("Café en grains 1 kg", "Lavazza", 18.50, False),
    Produit("T-shirt coton bio", "Kiabi", 12.99, False),
    Produit("Filtres à eau Brita (lot de 6)", "Brita", 34.99, False),
    Produit("Câble USB-C 2 m", "Belkin", 19.99, False),
    Produit("Sac de croquettes 12 kg", "Purina", 54.90, False),
    Produit("Ampoules LED E27 (lot de 3)", "Philips", 14.99, False),
]
OCCASIONS = [
    Produit("iPhone 15 128 Go - reconditionné - Très bon état", "Apple", 529.00, True),
    Produit("MacBook Pro 14 M2 reconditionné", "Apple", 1349.00, True),
    Produit("Console PS5 reconditionnée", "Sony", 389.00, True),
]

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
        "décembre"]  # fmt: skip
