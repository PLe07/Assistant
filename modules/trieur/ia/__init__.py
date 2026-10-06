"""La couche IA (§6) : Claude ne voit un document que si les règles locales hésitent (confiance < 0,75), et
seulement son texte, caviardé et coupé à 3000 caractères. Jamais le fichier, jamais un document sensible.

- Sensible (santé, identité, impôts, paie) : d'après le classement local ou des indices sûrs (n° de sécurité
  sociale, « numéro fiscal »…) → rien ne part, le document va dans « À vérifier ».
- La réponse est un JSON vérifié par un schéma ; s'il ne colle pas, une seule relance avec les erreurs.
- Panne passagère (surcharge 529, quota 429, délai) : 3 essais avec une attente croissante.
- Budget : 1 $ par mois par défaut (coût estimé à partir des jetons) ; au-delà, plus d'appel jusqu'au mois suivant.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from jsonschema import Draft202012Validator

from core.journal import journal
from modules.trieur.base import Base, Element
from modules.trieur.classement import SANS_MONTANT, Classement, regles, remplir
from modules.trieur.classement.texte import normaliser
from modules.trieur.extraction import Extraction
from modules.trieur.ia.caviardage import NIR, caviarder

log = journal("trieur")

DESCRIPTIONS = {
    "facture_achat": "facture d'un achat (objet, appareil, meuble) en magasin ou en ligne",
    "ticket_caisse": "ticket de caisse d'un magasin",
    "facture_service": "facture d'un abonnement ou d'un service (énergie, eau, téléphone, internet, streaming)",
    "releve_bancaire": "relevé de compte bancaire",
    "avis_imposition": "avis d'impôt, taxe foncière ou d'habitation",
    "quittance_loyer": "quittance de loyer",
    "bail_contrat": "bail, contrat de location, de prestation ou de travail",
    "attestation": "attestation ou certificat (scolarité, employeur, assurance, CAF)",
    "bulletin_paie": "bulletin de paie",
    "assurance": "contrat, avis d'échéance ou conditions d'assurance",
    "billet_transport": "billet de train, d'avion, de bus, carte d'embarquement",
    "reservation": "réservation d'hôtel ou de location de vacances",
    "sante": "ordonnance, remboursement de santé, document médical",
    "identite": "pièce d'identité, passeport, permis de conduire",
    "devis": "devis",
    "facture_emise": "facture émise par la micro-entreprise de l'utilisateur",
    "garantie_notice": "certificat de garantie ou notice d'utilisation",
    "courrier_admin": "courrier d'une administration ou d'un organisme",
    "autre": "rien de tout cela",
}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "confiance", "emetteur", "date", "montant", "detail"],
    "properties": {
        "type": {"enum": regles.TYPES},
        "confiance": {"type": "number", "minimum": 0, "maximum": 1},
        "emetteur": {"type": ["string", "null"], "maxLength": 60},
        "date": {"type": ["string", "null"], "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "montant": {"type": ["number", "null"], "minimum": 0, "maximum": 1000000},
        "detail": {"type": "string", "maxLength": 40},
    },
}
_VALIDATEUR = Draft202012Validator(SCHEMA)
SYSTEME = ("Tu classes des documents français (factures, relevés, courriers…). Le texte est un extrait, "
           "des informations personnelles y sont masquées entre crochets. "
           "Réponds uniquement par le JSON demandé.")  # fmt: skip
CONSIGNES = """Classe ce document. Types possibles :
{types}

Donne : type ; confiance (0 à 1) ; emetteur (l'entreprise ou l'organisme qui l'a écrit, null si inconnu) ;
date (la date du document au format AAAA-MM-JJ : date d'achat ou de facture, fin de période d'un relevé, départ d'un
billet ; null si aucune) ; montant (le total TTC payé ou à payer, en euros, null si aucun) ; detail (2 à 4 mots :
l'objet acheté, le service… ; vide si rien d'utile).

Texte du document :
<<<
{texte}
>>>"""
MARQUEURS_SENSIBLES = re.compile(
    r"numero fiscal|n° fiscal|revenu fiscal|avis d.impot|securite sociale|assurance maladie|carte vitale|\bcpam\b|"
    r"ameli|bulletin de (?:paie|salaire)|salaire brut|net imposable|carte nationale d.identite|passeport|"
    r"permis de conduire|titre de sejour|ordonnance|mutuelle|remboursement de soins|feuille de soins|medecin|"
    r"diagnostic|\bpatient|consultation|\bdr\b|docteur|pharmacie|\bsoins\b|dentist|kine|ophtalmo|hopital|"
    r"clinique|radiologie|laboratoire d.analyses|posologie"
)


class Refuse(Exception):
    """Le document ne partira pas chez Claude (sensible, budget, désactivé…)."""


def est_sensible(texte: str, c: Classement | None, sensibles: list[str]) -> str | None:
    """La raison pour laquelle ce document ne doit pas partir, ou None."""
    if c is not None:
        if c.type in sensibles:
            return f"type sensible ({c.type})"
        for type_, points in c.scores[:3]:
            if type_ in sensibles and points >= 2:  # le moindre indice sérieux suffit à ne rien envoyer
                return f"peut-être {type_}"
    if NIR.search(texte):
        return "numéro de sécurité sociale"
    m = MARQUEURS_SENSIBLES.search(normaliser(texte))
    return f"indice sensible ({m.group(0)})" if m else None


def cout(entree: int, sortie: int, tarifs: dict[str, float]) -> float:
    return entree * float(tarifs["entree"]) / 1e6 + sortie * float(tarifs["sortie"]) / 1e6


def _passagere(e: Exception) -> bool:
    if getattr(e, "definitif", False) or getattr(e, "pause", False):
        return False
    texte = str(e).lower()
    return not any(m in texte for m in ("introuvable", "jeton", "absent", "désactivé", "plafond", "pause"))


def noms_du_compte() -> list[str]:
    """Ton nom tel que le Mac le connaît (le nom complet de ta session) : toujours masqué, sans rien régler."""
    try:
        import os
        import pwd

        complet = pwd.getpwuid(os.getuid()).pw_gecos.split(",")[0].strip()
    except Exception:
        return []
    if not complet or complet.lower() in ("root", "system administrator", "unprivileged user"):
        return []
    return [complet] + [m for m in complet.split() if len(m) >= 3]


class CoucheIA:
    def __init__(self, reglages: dict[str, Any], base: Base, demander: Callable[..., Any] | None = None,
                 dormir: Callable[[float], None] = time.sleep):  # fmt: skip
        self.reglages, self.base, self.dormir = reglages, base, dormir
        self.r = reglages["ia"]
        self._demander = demander
        self.mots = list(self.r.get("mots_masques", []))
        if self.r.get("masquer_nom_du_compte", True):
            self.mots += noms_du_compte()
        self.envoyes: list[str] = []  # ce qui est parti pendant cette session (pour les tests et doctor)

    # --- le budget -------------------------------------------------------------------------------------------------

    def depense_du_mois(self, mois: str | None = None) -> float:
        mois = mois or date.today().strftime("%Y-%m")
        x = self.base._x("SELECT COALESCE(SUM(cout_usd), 0) FROM depenses_ia WHERE mois = ?", (mois,)).fetchone()
        return float(x[0])

    def _noter(self, element: int | None, entree: int, sortie: int, resultat: str) -> None:
        c = cout(entree, sortie, self.r["tarifs_usd_par_million"])
        self.base._x("INSERT INTO depenses_ia (quand, mois, element, entree, sortie, cout_usd, resultat) VALUES "
                     "(?, ?, ?, ?, ?, ?, ?)", (time.time(), date.today().strftime("%Y-%m"), element, entree, sortie, c,
                                                resultat))  # fmt: skip

    # --- la demande ------------------------------------------------------------------------------------------------

    def message(self, texte: str) -> str:
        compact = re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]{3,}", "  ", texte)).strip()  # moins de jetons
        extrait = caviarder(compact, self.mots, int(self.r["caracteres_max"]))
        types = "\n".join(f"- {t} : {d}" for t, d in DESCRIPTIONS.items())
        return CONSIGNES.format(types=types, texte=extrait)

    def _appeler(self, message: str) -> Any:
        demander = self._demander
        if demander is None:
            from core.cerveau import demander as demander_assistant

            demander = demander_assistant
        derniere: Exception | None = None
        for essai in range(int(self.r["essais"])):
            try:
                self.envoyes.append(message)
                return demander(message, module="trieur", systeme=SYSTEME, schema=SCHEMA, modele=self.r["modele"],
                                delai=int(self.r["delai_s"]), essais=1)  # fmt: skip
            except Exception as e:
                derniere = e
                if not _passagere(e) or essai + 1 == int(self.r["essais"]):
                    break
                self.dormir(2 ** (essai + 1))  # 2 s, puis 4 s
        raise Refuse(f"Claude indisponible : {derniere}")

    def demander(self, texte: str, element: int | None) -> dict[str, Any]:
        """La réponse validée de Claude pour ce texte (déjà jugé envoyable)."""
        if not self.r.get("actif", True):
            raise Refuse("IA désactivée dans les réglages")
        budget = float(self.r["budget_mensuel_usd"])
        message = self.message(texte)
        estimation = cout(len(message) // 3 + 400, 200, self.r["tarifs_usd_par_million"])
        if self.depense_du_mois() + estimation > budget:
            raise Refuse(f"budget du mois atteint ({budget:.2f} $)")
        reponse = self._appeler(message)
        donnees, erreurs = self.valider(reponse.donnees)
        entree, sortie = int(reponse.tokens_entree), int(reponse.tokens_sortie)
        if erreurs:
            relance = (message + "\n\nTa réponse précédente ne respectait pas le format : " + "; ".join(erreurs) +
                       ". Réponds de nouveau, uniquement par le JSON.")  # fmt: skip
            reponse = self._appeler(relance)
            donnees, erreurs = self.valider(reponse.donnees)
            entree, sortie = entree + int(reponse.tokens_entree), sortie + int(reponse.tokens_sortie)
        self._noter(element, entree, sortie, "erreur de format" if erreurs else str(donnees and donnees["type"]))
        if erreurs or donnees is None:
            raise Refuse("réponse de Claude hors format, deux fois")
        return donnees

    @staticmethod
    def valider(donnees: Any) -> tuple[dict[str, Any] | None, list[str]]:
        if not isinstance(donnees, dict):
            return None, ["pas d'objet JSON"]
        erreurs = [f"{'/'.join(str(p) for p in e.absolute_path) or 'racine'} : {e.message}"
                   for e in _VALIDATEUR.iter_errors(donnees)]  # fmt: skip
        if not erreurs and donnees.get("date"):
            try:
                date.fromisoformat(donnees["date"])
            except ValueError:
                erreurs.append(f"date : {donnees['date']} n'existe pas")
        return (None, erreurs[:6]) if erreurs else (donnees, [])

    # --- pour la chaîne de traitement ------------------------------------------------------------------------------

    def classer(self, e: Extraction, c: Classement | None, el: Element) -> Classement | None:
        """Le classement de Claude, ou None (le classement local s'applique : « À vérifier »)."""
        if not e.texte.strip():
            return None
        raison = est_sensible(e.texte, c, list(self.r["types_sensibles"]))
        if raison:
            log.info("%s : pas envoyé à Claude (%s)", el.nom, raison)
            return None
        try:
            d = self.demander(e.texte, el.id)
        except Refuse as refus:
            log.info("%s : %s", el.nom, refus)
            return None
        if d["type"] in self.r["types_sensibles"]:
            log.info("%s : Claude y voit un document sensible (%s) : à vérifier", el.nom, d["type"])
            return None
        return construire(d, e.texte, c, self.reglages, el.note)


def construire(d: dict[str, Any], texte: str, local: Classement | None, reglages: dict[str, Any],
               note: str | None) -> Classement:  # fmt: skip
    """Le classement final : le type et la confiance de Claude ; dates, montants et garanties lus sur place pour ce
    type (plus sûrs), complétés par Claude quand le texte ne les donne pas."""
    r = regles.charger()
    c = Classement(d["type"], round(float(d["confiance"]), 3), r.libelles.get(d["type"], d["type"]), source="ia")
    if local is not None:
        c.emetteur, c.emetteur_connu, c.categorie = local.emetteur, local.emetteur_connu, local.categorie
        c.scores = local.scores
    if d.get("emetteur") and not (local and local.emetteur_connu):
        c.emetteur = str(d["emetteur"])[:60]
    c.raisons = ["Claude"]
    remplir(c, texte, reglages, note)
    if c.date is None and d.get("date"):
        c.date = date.fromisoformat(d["date"])
    if c.montant is None and d.get("montant") is not None and c.type not in SANS_MONTANT:
        try:
            c.montant = Decimal(str(d["montant"])).quantize(Decimal("0.01"))
        except InvalidOperation:
            pass
    if not c.detail and d.get("detail"):
        c.detail = str(d["detail"])[:40]
    if c.type == "autre":
        c.emetteur = None
    return c


def couche(reglages: dict[str, Any], base: Base) -> CoucheIA | None:
    return CoucheIA(reglages, base) if reglages["ia"].get("actif", True) else None
