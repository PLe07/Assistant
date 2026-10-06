"""L'analyse locale (§3.2) : gratuite, rapide, rejouable. Chaque indice est pondéré et expliqué en une phrase.

Score de 0 à 100 → 4 niveaux (🔴 ≥ 70, 🟠 ≥ 45, 🟡 ≥ 20, ⚪ sinon). Règles de sûreté :
- les indices tirés du texte ne font qu'ajouter des points : un message ne peut pas « se blanchir » en parlant ;
- seuls des faits techniques vérifiés (expéditeur authentifié par le serveur qui a reçu le mail) retirent des points ;
- un indice critique (lien déjà signalé, sosie qui demande de payer, demande de code…) tient le verdict à 🟠 au moins.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from bouclier.arnaque import entetes, familles, liens, pression
from bouclier.arnaque.extraction import Message
from bouclier.arnaque.score import evaluer
from bouclier.arnaque.signaux import Niveau, Signal
from bouclier.arnaque.sosies import MARQUES, Marque, decoder_idn, est_officiel, marques_citees, sosie
from bouclier.arnaque.texte import chiffres, est_surtaxe, montants, normaliser, telephones
from bouclier.urgence import sources

PLAFOND_PRESSION = 20
_FOURRE_TOUT = frozenset({"banque", "support", "regularisation"})


@dataclass
class Contexte:
    rdap: Callable[[str], dt.date | None] | None = None
    flux: Callable[[str], str | None] | None = None
    comptes: Callable[[], set[str]] | None = None  # identifiants des marques où tu as un compte (inventaire)
    aujourd_hui: dt.date = field(default_factory=dt.date.today)
    max_rdap: int = 4


@dataclass
class AnalyseLocale:
    message: Message
    signaux: list[Signal]
    score: int
    niveau: Niveau
    marque: Marque | None
    famille: str | None

    @property
    def critiques(self) -> list[Signal]:
        return [s for s in self.signaux if s.critique]

    def raisons(self, n: int = 3) -> list[str]:
        positifs = [s for s in self.signaux if s.poids > 0]
        # Les indices critiques d'abord, puis les plus lourds (« il te demande de payer » avant « .top »).
        positifs.sort(key=lambda s: (not s.critique, -s.poids))
        vues: list[str] = []
        for s in positifs:
            if s.phrase not in vues:
                vues.append(s.phrase)
            if len(vues) == n:
                break
        return vues


class _Collecte:
    def __init__(self) -> None:
        self.signaux: dict[str, Signal] = {}

    def ajouter(self, s: Signal | None) -> None:
        if s is None:
            return
        ancien = self.signaux.get(s.code)
        if ancien is None or s.poids > ancien.poids or (s.critique and not ancien.critique):
            self.signaux[s.code] = s

    def a(self, prefixe: str) -> bool:
        return any(c.startswith(prefixe) for c in self.signaux)


def _age(creation: dt.date, aujourd_hui: dt.date) -> int:
    return (aujourd_hui - creation).days


def _phrase_age(jours: int) -> str:
    if jours <= 1:
        return "Ce site a été créé il y a moins de 2 jours."
    if jours < 60:
        return f"Ce site a été créé il y a {jours} jours."
    return f"Ce site est récent (créé il y a {jours // 30} mois)."


def _marques_revendiquees(m: Message) -> list[Marque]:
    """Les marques au nom desquelles le message parle : expéditeur, sujet, début, ligne de signature."""
    morceaux = [m.expediteur_nom, m.sujet, m.texte[:100]]
    for ligne in m.texte.splitlines():
        if 0 < len(ligne.strip()) <= 40:
            morceaux.append(ligne)
    return marques_citees("\n".join(morceaux))


def analyser(message: Message, ctx: Contexte | None = None) -> AnalyseLocale:
    ctx = ctx or Contexte()
    t = normaliser(message.texte_complet)
    c = _Collecte()
    infos = []
    vus: set[str] = set()
    for lien in message.liens:
        if lien.url not in vus:
            vus.add(lien.url)
            infos.append((lien, liens.analyser(lien.url)))
    numeros = [n for n in telephones(message.texte) if len(re.sub(r"\D", "", n)) >= 10]
    revendiquees = _marques_revendiquees(message)
    sosies_vus: dict[str, Marque] = {}

    # --- Liens -----------------------------------------------------------------------------------------------------
    domaines_rdap: list[str] = []
    for lien, info in infos:
        if not info.hote:
            continue
        source = ctx.flux(lien.url) if ctx.flux else None
        if source:
            c.ajouter(Signal("lien:flux", 60, "Ce lien est déjà signalé comme piégé dans une liste publique de sites"
                             " dangereux.", critique=True))  # fmt: skip
        if info.ip:
            c.ajouter(Signal("lien:ip", 35, "Le lien mène à une adresse en chiffres au lieu d'un nom de site : les"
                             " vrais services ne font pas ça."))  # fmt: skip
        if info.arobase:
            c.ajouter(Signal("lien:arobase", 40, "Le lien est déguisé : la partie avant « @ » fait croire à un site"
                             " connu, mais il mène ailleurs.", critique=True))  # fmt: skip
        if info.raccourci:
            c.ajouter(Signal("lien:raccourci", 20, "Le lien est raccourci : on ne voit pas où il mène vraiment."))
        if info.messagerie:
            c.ajouter(Signal("demande:messagerie", 15, "Il veut continuer sur WhatsApp ou Telegram, loin des"
                             " protections habituelles."))  # fmt: skip
        if info.hebergeur:
            c.ajouter(Signal("lien:hebergeur", 12, "Le lien mène vers une page hébergée gratuitement, souvent utilisée"
                             " pour les fausses pages."))  # fmt: skip
        if info.extension in liens.EXTENSIONS_TRES_RISQUEES:
            c.ajouter(Signal("lien:extension", 15, f"Le site se termine par « .{info.extension} », une extension très"
                             " utilisée par les arnaques."))  # fmt: skip
        elif info.extension in liens.EXTENSIONS_RISQUEES:
            c.ajouter(Signal("lien:extension", 8, f"Le site se termine par « .{info.extension} », une extension"
                             " souvent utilisée par les arnaques."))  # fmt: skip
        if not info.https and not info.ip:
            c.ajouter(Signal("lien:http", 5, "Le lien n'est pas sécurisé (pas de cadenas)."))
        s = sosie(info.domaine, info.hote) if not info.ip else None
        if s:
            sosies_vus[s.marque.id] = s.marque
            affiche = decoder_idn(info.hote)
            if s.maniere == "caracteres":
                phrase = (f"« {affiche} » imite {s.marque.nom} avec des lettres trompeuses : le vrai site est"
                          f" {s.marque.site}.")  # fmt: skip
            else:
                phrase = f"Le lien mène à « {info.domaine} », pas au site officiel de {s.marque.nom} ({s.marque.site})."
            c.ajouter(Signal("lien:sosie", 45, phrase))
        if lien.affiche:
            d_affiche = liens.domaine_affiche(lien.affiche)
            if d_affiche and d_affiche != info.domaine:
                officiel_commun = any(
                    est_officiel(d_affiche, d_affiche, m) and est_officiel(info.domaine, info.hote, m) for m in MARQUES
                )
                if not officiel_commun:
                    c.ajouter(Signal("lien:trompeur", 35, f"Le lien affiche « {d_affiche} » mais mène en réalité à"
                                     f" « {info.domaine} »."))  # fmt: skip
        officiel = any(est_officiel(info.domaine, info.hote, m) for m in MARQUES)
        if (
            not officiel
            and not info.ip
            and not info.raccourci
            and not info.messagerie
            and not info.hebergeur
            and info.domaine not in domaines_rdap
        ):
            domaines_rdap.append(info.domaine)

    # --- Expéditeur (mail) -----------------------------------------------------------------------------------------
    domaine_exp = entetes.domaine_adresse(message.expediteur_adresse)
    enregistrable_exp = liens.domaine_enregistrable(domaine_exp) if domaine_exp else ""
    auth = entetes.lire_authentification(message.authentification)
    authentifie_officiel = False
    if message.canal == "mail" and domaine_exp:
        s_exp = sosie(enregistrable_exp, domaine_exp)
        if s_exp:
            sosies_vus[s_exp.marque.id] = s_exp.marque
            c.ajouter(Signal("expediteur:sosie", 45, f"L'adresse d'envoi ({domaine_exp}) imite {s_exp.marque.nom}"
                             f" sans être la sienne ({s_exp.marque.site})."))  # fmt: skip
        for marque in marques_citees(message.expediteur_nom):
            if marque.id in sosies_vus or est_officiel(enregistrable_exp, domaine_exp, marque):
                continue
            c.ajouter(Signal("expediteur:nom", 35, f"Le nom affiché « {message.expediteur_nom} » ne correspond pas à"
                             f" l'adresse d'envoi ({domaine_exp})."))  # fmt: skip
        officielle = next((m for m in MARQUES if est_officiel(enregistrable_exp, domaine_exp, m)), None)
        if auth.usurpe:
            if officielle:
                c.ajouter(Signal("expediteur:usurpe", 40, f"L'adresse d'envoi se fait passer pour {officielle.nom},"
                                 " mais la vérification d'authenticité a échoué : le mail est usurpé.",
                                 critique=bool(infos or numeros)))  # fmt: skip
            else:
                c.ajouter(Signal("expediteur:usurpe", 20, "La vérification d'authenticité de l'expéditeur a échoué."))
        elif auth.douteux:
            c.ajouter(Signal("expediteur:douteux", 10, "Le serveur d'envoi n'est pas reconnu pour cette adresse."))
        reponse = entetes.domaine_adresse(message.reply_to.split(",")[0]) if message.reply_to else ""
        if reponse and liens.domaine_enregistrable(reponse) != enregistrable_exp:
            if reponse in entetes.WEBMAILS:
                c.ajouter(Signal("expediteur:reponse", 25, f"Les réponses partent vers une adresse personnelle"
                                 f" ({reponse}), pas vers l'expéditeur affiché."))  # fmt: skip
            else:
                c.ajouter(Signal("expediteur:reponse", 10, f"Les réponses partent vers une autre adresse ({reponse})."))
        meme_domaine = auth.domaine_dmarc and liens.domaine_enregistrable(auth.domaine_dmarc) == enregistrable_exp
        if auth.authentifie and meme_domaine and domaine_exp not in entetes.WEBMAILS:
            revendique_ailleurs = [
                m for m in marques_citees(message.expediteur_nom) if not est_officiel(enregistrable_exp, domaine_exp, m)
            ]
            if officielle and not revendique_ailleurs and not s_exp:
                authentifie_officiel = True
                c.ajouter(Signal("expediteur:authentifie", -40, f"L'expéditeur est authentifié : c'est bien"
                                 f" {officielle.nom} ({enregistrable_exp})."))  # fmt: skip
            elif not officielle and not s_exp and ctx.rdap and not revendique_ailleurs:
                creation = ctx.rdap(enregistrable_exp)
                if creation and _age(creation, ctx.aujourd_hui) > 365:
                    c.ajouter(Signal("expediteur:ancien", -10, "L'expéditeur est authentifié et son site existe depuis"
                                     " longtemps."))  # fmt: skip
        if not auth.authentifie and not auth.usurpe and revendiquees and not authentifie_officiel:
            c.ajouter(Signal("expediteur:non_authentifie", 10, "L'expéditeur n'est pas authentifié."))
        if domaine_exp not in entetes.WEBMAILS and not authentifie_officiel and enregistrable_exp not in domaines_rdap:
            if not any(est_officiel(enregistrable_exp, domaine_exp, m) for m in MARQUES):
                domaines_rdap.append(enregistrable_exp)

    # --- Date de création des sites (RDAP, nom de domaine seulement) ---------------------------------------------
    if ctx.rdap:
        for d in domaines_rdap[: ctx.max_rdap]:
            creation = ctx.rdap(d)
            if creation is None:
                continue
            jours = _age(creation, ctx.aujourd_hui)
            if jours < 30:
                c.ajouter(Signal("lien:recent", 30, _phrase_age(jours)))
            elif jours < 180:
                c.ajouter(Signal("lien:recent", 12, _phrase_age(jours)))

    # --- La marque revendiquée et l'endroit où mènent les liens ----------------------------------------------------
    # Un seul lien hors des sites officiels suffit : ajouter un vrai lien à côté d'un faux ne blanchit rien.
    liens_a_risque = [i for _, i in infos if not any(est_officiel(i.domaine, i.hote, m) for m in MARQUES)]
    for marque in revendiquees:
        if marque.id in sosies_vus or authentifie_officiel or not liens_a_risque:
            continue
        if all(i.raccourci for i in liens_a_risque):
            phrase = f"Le message se présente comme {marque.nom}, mais cache son lien derrière un raccourci."
        else:
            phrase = (f"Le message se présente comme {marque.nom}, mais le lien ne mène pas à son site officiel"
                      f" ({marque.site}).")  # fmt: skip
        c.ajouter(Signal("marque:lien", 30, phrase))
        break

    # --- Téléphones ------------------------------------------------------------------------------------------------
    # Un numéro officiel payant (opposition bancaire 0 892 705 705) n'est pas un piège.
    officiels = sources.charger().chiffres_officiels()
    surtaxes = [n for n in numeros if est_surtaxe(n) and chiffres(n) not in officiels]
    if surtaxes:
        c.ajouter(
            Signal("telephone:surtaxe", 45, f"Le numéro {surtaxes[0]} est surtaxé : l'appel peut coûter très cher.")
        )
    if numeros and familles.trouver(pression.APPEL, t):
        c.ajouter(Signal("telephone:appel", 12, "Il te demande d'appeler un numéro donné dans le message : appelle"
                         " plutôt le numéro officiel que tu connais (au dos de ta carte, sur le site officiel).",
                         technique=False))  # fmt: skip

    # --- Contenu : demandes, familles, faux proche, pression -------------------------------------------------------
    # Un lien vers un site officiel (« connectez-vous sur ameli.fr ») n'est pas un moyen de piéger.
    for s_dem in pression.signaux_de_demandes(t, lien=bool(liens_a_risque), telephone=bool(numeros)):
        c.ajouter(s_dem)
    vecteur = (
        bool(liens_a_risque or numeros)
        or c.a("demande:")
        or bool(familles.trouver(pression.REPONDRE, t, negation=False))
        or bool(familles.trouver(pression.DEMANDE_CONTACT, t))
    )
    reconnues = familles.reconnaitre(t, vecteur)
    famille_principale: str | None = None
    if reconnues:
        # À égalité, la famille précise l'emporte sur les familles fourre-tout (banque, support, impayé).
        meilleure = max(
            reconnues,
            key=lambda r: (r.famille.poids + 8 * r.accroches + 15 * r.forte, r.famille.id not in _FOURRE_TOUT),
        )
        argent = montants(message.texte)
        action = f"de payer {argent[0]}" if argent else "d'agir vite (payer, confirmer, reprogrammer)"
        c.ajouter(familles.signal_famille(meilleure, action))
        famille_principale = meilleure.famille.id
    proche = _faux_proche(t)
    for s_proche in proche:
        c.ajouter(s_proche)
    if proche and famille_principale is None:
        famille_principale = "proche"
    total_pression = 0
    for s_pr in pression.signaux_de_pression(t):
        if total_pression + s_pr.poids <= PLAFOND_PRESSION:
            c.ajouter(s_pr)
            total_pression += s_pr.poids
    c.ajouter(pression.signal_injection(t) or pression.signal_injection(normaliser(message.texte_cache)))

    # --- Inventaire : « ta banque » chez qui tu n'as pas de compte -----------------------------------------------
    if ctx.comptes and not authentifie_officiel:
        mes_comptes = ctx.comptes()
        if mes_comptes:
            for marque in [*sosies_vus.values(), *revendiquees]:
                if marque.banque and marque.id not in mes_comptes:
                    c.ajouter(Signal("contexte:pas_de_compte", 15, f"Tu n'as aucun compte détecté chez {marque.nom} :"
                                     " un message « de ta banque » venant de là est suspect."))  # fmt: skip
                    break

    # --- Sosie + demande d'argent ou de données : critique (§3.3) ---------------------------------------------------
    if "lien:sosie" in c.signaux and any(
        k in c.signaux
        for k in ("demande:paiement", "demande:carte", "demande:rib", "demande:identifiants", "demande:code")
    ):
        ancien = c.signaux["lien:sosie"]
        c.signaux["lien:sosie"] = Signal(ancien.code, ancien.poids, ancien.phrase, critique=True)

    signaux = list(c.signaux.values())
    score, niveau = evaluer(signaux)
    principale = next(iter(sosies_vus.values()), None) or (revendiquees[0] if revendiquees else None)
    return AnalyseLocale(message, signaux, score, niveau, principale, famille_principale)


_RELATIF = re.compile(
    r"\b(maman|papa|mamie|papi|papy|mamy|grand-?(pere|mere)|tonton|tata|ma (grande )?(fille|soeur)"
    r"|mon (grand )?(fils|frere)|ta (fille|petite-fille|soeur|niece)|ton (fils|petit-fils|frere|neveu))\b"
)
_NOUVEAU_NUMERO = re.compile(
    r"nouveau (numero|portable|telephone|tel)\b|change de (numero|portable|telephone)"
    r"|(telephone|tel|portable)( est)? (casse|perdu|tombe|en reparation|vole)|numero prete|telephone d'un ami"
    r"|depuis (le|ce) (telephone|numero|tel)|j'ai (perdu|casse) mon (telephone|tel|portable)|(enregistre|note)[- ]le"
)
_ARGENT = re.compile(
    r"virement|\bpay(er|ez)\b|\bregl(er|ez)\b|facture|argent|\d ?€|\brib\b|\biban\b|carte pcs|recharge|\bcode\b"
    r"|loyer|hopital|caution"
)
_SERVICE = re.compile(r"\bservice\b|\baide\b|besoin|whatsapp|urgent|presse|rapidement|un truc")


def _faux_proche(t: str) -> list[Signal]:
    if not _RELATIF.search(t):
        return []
    sortie: list[Signal] = []
    nouveau = bool(_NOUVEAU_NUMERO.search(t))
    argent = bool(_ARGENT.search(t))
    if nouveau:
        sortie.append(Signal("proche:nouveau_numero", 35, "Un « proche » qui écrit depuis un nouveau numéro : c'est"
                             " l'arnaque du faux proche en détresse.", technique=False))  # fmt: skip
    if argent and (nouveau or pression.SECRET.search(t) or pression.URGENCE.search(t)):
        sortie.append(Signal("proche:argent", 25, "Il te demande de l'argent en urgence : appelle ton proche sur son"
                             " numéro habituel avant de faire quoi que ce soit.", technique=False))  # fmt: skip
    elif nouveau and _SERVICE.search(t):
        sortie.append(Signal("proche:service", 15, "Il te demande un service urgent sans dire lequel : c'est l'amorce"
                             " habituelle avant une demande d'argent.", technique=False))  # fmt: skip
    return sortie
