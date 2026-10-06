"""Les familles d'arnaques qui circulent en France, chacune avec sa phrase d'explication.

Une famille est reconnue quand le message en parle (thème), qu'il pousse à agir (accroche) et qu'il donne un
moyen d'agir (lien, numéro à appeler, demande de données) : un vrai SMS de livraison sans demande d'argent,
une vraie alerte bancaire sans lien ni numéro ne sont pas des arnaques.

Les règles cherchent dans le texte normalisé (minuscules, sans accents). Une accroche dans une phrase négative
(« ne communiquez jamais vos coordonnées bancaires ») ne compte pas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bouclier.arnaque.signaux import Signal

_NEGATION = re.compile(r"(\bne\b|\bn'|jamais|aucun|\bsans\b|\bpas\b)[^.!?\n]{0,40}$")
_SEPARATEUR = re.compile(r",|;|:|\bet\b|\bpuis\b|\bmais\b|\bou\b|\bpour\b")


def trouver(motif: re.Pattern[str], texte: str, negation: bool = True) -> re.Match[str] | None:
    """La première occurrence qui n'est pas dans une phrase négative (« ne … jamais », « aucun »)."""
    for m in motif.finditer(texte):
        if negation:
            avant = texte[max(0, m.start() - 60) : m.start()]
            debut_phrase = max(avant.rfind("."), avant.rfind("!"), avant.rfind("?"), avant.rfind("\n"))
            proposition = _SEPARATEUR.split(avant[debut_phrase + 1 :])[-1]
            if _NEGATION.search(proposition):
                continue
        return m
    return None


@dataclass(frozen=True)
class Famille:
    id: str
    nom: str
    theme: str
    accroches: tuple[str, ...]
    phrase: str
    poids: int = 25
    vecteur_requis: bool = True
    fortes: tuple[str, ...] = ()  # une seule suffit pour un poids plus fort

    def motif_theme(self) -> re.Pattern[str]:
        return _compile(self.theme)


_CACHE: dict[str, re.Pattern[str]] = {}


def _compile(motif: str) -> re.Pattern[str]:
    if motif not in _CACHE:
        _CACHE[motif] = re.compile(motif)
    return _CACHE[motif]


FAMILLES: tuple[Famille, ...] = (
    Famille(
        "colis",
        "faux message de livraison",
        r"\bcolis\b|\blivr(aison|er|e|ee|eur)\b|\bpaquet\b|\benvoi\b|point relais|douane|entrepot|affranchissement"
        r"|\brecommande\b|avis de passage|\bexpedi",
        (
            r"\bfrais\b",
            r"\bpay(er|ez)\b|\bregl(er|ez|ant)\b|\bpaiement\b",
            r"reprogramm|\bprogramm(ez|er)\b|nouvelle (date|presentation)|choisir une date|\bcreneau\b",
            r"confirm(er|ez) (vos coordonnees|l'adresse|votre adresse|vos informations)|mett(re|ez) a jour"
            r"|complet(ez|er) (votre adresse|vos)",
            r"droits d'importation|dedouanement|\btaxe\b",
            r"stockage|frais de garde|\bgarde\b|prolong|\bdetruit\b|\bretourne\b|renvoye|retrait expire",
            r"\bbloque\b|\bretenu\b|en attente|echec de livraison|n'a pas pu etre (livre|distribue)"
            r"|livraison (impossible|echouee)|tente de (vous )?livrer|n'a pas trouve",
            r"\b(appelez|rappelez)\b",
            r"etiquette (est )?illisible|adresse (in)?complete|numero de rue",
        ),
        "Il te demande {action} pour un colis : La Poste et les transporteurs ne font jamais ça par SMS ou par mail.",
    ),
    Famille(
        "amende",
        "fausse amende ou faux péage",
        r"\bantai\b|\bamende|contravention|crit'? ?air|vignette|\bpeage|\bfps\b|forfait post-stationnement"
        r"|exces de vitesse|feu rouge|fourriere|permis de conduire|\bpoints?\b.{0,40}\bpermis|stationnement"
        r"|titre de transport|telepeage|recouvrement|huissier|\bnavigo\b",
        (
            r"\bpay(er|ez)\b|\bregl(er|ez|ant)\b|reglement|paiement",
            r"majoration|\bmajore",
            r"\bevit(er|ez)\b",
            r"avant (le|ce|demain)|sous \d+ ?h|\bdemain\b",
            r"commandez|renouvel",
            r"impaye|non (regle|paye)|en retard de paiement|defaut de paiement|non payee?",
            r"suspendu|suspension|enleve|saisie|desactive",
            r"contestation impossible",
        ),
        "Il te réclame une amende, un péage ou une pénalité à payer tout de suite par un lien : c'est un grand"
        " classique des arnaques.",
    ),
    Famille(
        "sante",
        "faux message Ameli ou mutuelle",
        r"\bameli\b|assurance maladie|carte vitale|\bvitale\b|mutuelle|ordonnance|mon espace sante"
        r"|attestation de (droits|mutuelle)|\bcpam\b|dossier medical",
        (
            r"command(ez|er)",
            r"renouvel",
            r"mett(re|ez) a jour|mise a jour",
            r"confirm(ez|er)",
            r"coordonnees bancaires|\biban\b|\brib\b|carte bancaire|numero de carte|16 chiffres",
            r"\bfrais\b",
            r"expir",
            r"suspendu|ne sera plus valable|ne seront plus pris en charge|sera ferme",
            r"incomplet|complet(ez|er)",
            r"rembourse.{0,40}(en attente|vous attend|disponible)|en attente",
            r"\bpay(er|ez)\b|\bregl(er|ez)\b",
        ),
        "Il parle de ta carte Vitale, de ta mutuelle ou d'un remboursement santé et te pousse à agir par un lien :"
        " c'est le scénario des faux messages Ameli.",
    ),
    Famille(
        "impots",
        "faux message des impôts",
        r"\bimpots?\b|impots\.gouv|\bdgfip\b|finances publiques|tresor public|taxe (fonciere|d'habitation)"
        r"|trop.?percu|credit d'impot|prelevement a la source|\burssaf\b|maprimerenov|cheque energie|avis d'impot",
        (
            r"rembours",
            r"eligible",
            r"formulaire",
            r"confirm(ez|er)",
            r"\brib\b|\biban\b|coordonnees bancaires|infos? (bancaires|banquaires)|carte bancaire|numero de carte"
            r"|cryptogramme",
            r"impaye|regularis|penalite|poursuites|majoration",
            r"\bfrais\b",
            r"activez|debloqu|\bvalid(er|ez)\b|soumettre",
            r"attribues?|accordee?|exceptionnel|en votre faveur|vous attend|disponible",
        ),
        "Il te promet un remboursement ou te menace au sujet de tes impôts et te pousse à agir par un lien : c'est"
        " le scénario classique des faux messages des impôts.",
    ),
    Famille(
        "formation",
        "arnaque au CPF",
        r"\bcpf\b|compte (personnel de )?formation|moncompteformation|droits? (a la |de )?formation"
        r"|formation (financee|gratuite)",
        (
            r"expir",
            r"perd(u|re|ront)\b|suppression|supprime",
            r"utilis(ez|er)",
            r"activ(ez|ation)",
            r"inscri",
            r"\b(appelez|rappelez)\b",
            r"\bcode\b",
            r"il vous reste|derniers? rappel|\b72 ?h|ce soir|avant demain",
            r"identifiants|france ?connect|numero de securite sociale",
        ),
        "Il te presse d'utiliser tes droits à la formation (CPF) avant qu'ils « expirent » : c'est l'arnaque au"
        " CPF, très répandue.",
    ),
    Famille(
        "banque",
        "faux conseiller bancaire",
        r"\bbanque|bancaire|\bcompte\b|\bcarte\b|virement|operation|paiement|plafond|beneficiaire|conseill(er|ere)"
        r"|service (fraude|securite|client)|certicode|securipass|secur'? ?pass|appareil|transaction|\bpaypal\b"
        r"|\bn26\b|identifiants?",
        (
            r"suspect|fraud|inhabituel|piratage|compromis",
            r"\bbloque|suspendu|desactive|cloture|\bgele\b|\blimite\b|restreint",
            r"annul(er|ez|ation)",
            r"reactiv|debloq|retabli",
            r"confirm(ez|er) (votre identite|vos informations|vos infos|vos identifiants)"
            r"|verifi(ez|er) (vos informations|votre identite|vos infos)",
            r"mise a jour obligatoire|mett(re|ez) a jour",
            r"nouvel appareil|nouveau beneficiaire|connexion (depuis|inhabituelle)|appareil inconnu",
            r"si (ce n'est|ce n'etait) pas vous|si vous n'etes pas a l'origine",
            r"\b(appelez|rappelez)\b",
            r"securis",
            r"remboursement",
            r"en attente( de validation)?",
        ),
        "Il parle d'une opération suspecte ou d'un compte bloqué et te pousse à agir par un lien ou un appel :"
        " c'est la méthode des faux conseillers bancaires.",
    ),
    Famille(
        "annonce",
        "faux acheteur ou faux paiement sur une annonce",
        r"\bvinted\b|le ?bon ?coin|\blbc\b|annonce|acheteur|\bvendu\b|\bvente\b|\barticle\b|transporteur|airbnb"
        r"|booking|billet|reservation|caution|j'achete|interesse par",
        (
            r"paiement securise",
            r"recev(oir|ez|rez) (l'argent|les fonds|votre argent|le paiement|mes|les \d|vos \d|\d)",
            r"confirm(ez|er) (vos coordonnees|votre carte|vos informations)|coordonnees bancaires|carte bancaire"
            r"|saisi(r|ssez) (votre|vos)|numero de carte",
            r"(validez|valider|activez) la reception",
            r"code de validation",
            r"payer directement|hors (de la )?plateforme|par virement|\biban\b|\brib\b",
            r"a l'etranger",
            r"recevrez un (mail|e-mail|sms|lien) pour valider",
            r"votre adresse (mail|e-mail)|donnez-moi votre (adresse|mail|numero)",
            r"suspendu|supprime|verifi(ez|er) votre identite",
            r"(mon|un) transporteur passera|livreur passera",
            r"erreur (est survenue )?lors du paiement|paiement .{0,20}bloque|debloquer",
            r"compte vendeur",
        ),
        "Un faux acheteur ou un faux service de paiement te demande tes coordonnées ou de cliquer pour « recevoir"
        " l'argent » : sur les sites d'annonces, tout se passe dans l'appli, jamais par un lien reçu.",
        fortes=(r"rembourser la difference", r"recevrez un (mail|e-mail|lien) pour valider"),
    ),
    Famille(
        "support",
        "faux support ou faux service",
        r"microsoft|windows|\bapple\b|icloud|identifiant apple|virus|ordinateur|\bpc\b|netflix|abonnement|facture"
        r"|\bligne\b|forfait|fidelite|stockage|antivirus|logiciel|spotify|disney|canal|licence|\bedf\b|engie|\beau\b"
        r"|electricite|veolia|totalenergies|\borange\b|\bsfr\b|\bfree\b|bouygues|technicien|support",
        (
            r"\bbloque|verrouill",
            r"infect|virus|logiciels? espions?|piratage|pirate",
            r"suspendu|resili|coupee?\b|coupure|\bferme\b|desactiv",
            r"supprim",
            r"expir",
            r"impaye|refuse|n'avons pas pu (valider|prelever)|paiement (refuse|echoue)|impossible de renouveler",
            r"\b(appelez|rappelez)\b",
            r"mett(re|ez) a jour|mise a jour",
            r"renouvel",
            r"convertissez|points? (de )?fidelite",
            r"rembours",
            r"offre (fidelite|exclusive)|\ba vie\b|gratuits?|\b1 ?€ par mois",
            r"ne (l'eteignez|redemarrez) pas|n'eteignez pas",
            r"regularis",
            r"annuler",
        ),
        "Il imite un service connu (abonnement, facture, assistance) pour te faire payer, appeler un faux support"
        " ou donner tes informations.",
    ),
    Famille(
        "sextorsion",
        "chantage à la vidéo intime",
        r"webcam|camera|videos? (de (vous|toi)|intimes?|compromettantes?)|images? compromettantes?|j'ai pirate"
        r"|je vous ai pirate|vous observe|logiciel (espion|installe)|sites? (pour )?adultes|pedopornograph"
        r"|contenu (pour )?adultes|convocation|saisie informatique",
        (
            r"bitcoin|\bbtc\b|crypto",
            r"envo(ie|yer|yez)|vers(ez|er)|pay(ez|er)|transfer|regler|amende",
            r"contacts|famille|proches|publi",
            r"\d+ ?(h|heures|jours)\b",
            r"n'en parl|ne contactez pas|police",
        ),
        "C'est un chantage (« j'ai une vidéo de toi », fausse convocation) avec une demande d'argent : ne paie pas"
        " et ne réponds pas, ces menaces sont envoyées en masse.",
        poids=45,
        vecteur_requis=False,
    ),
    Famille(
        "loterie",
        "faux gain ou faux héritage",
        r"gagn(e|ant|ez)|tire au sort|tirage|felicitations|cadeau|\blot\b|heritage|heritier|beneficiaire"
        r"|\d[\d ]*e visiteur|millionieme|bon d'achat|\bsejour\b",
        (
            r"frais (de port|de dossier|de transfert|de notaire|de livraison|d'envoi)|\bfrais\b",
            r"\bpay(ez|er)\b|\bregl(ez|er)\b",
            r"reclam(ez|er)|recuper(ez|er)|recev(oir|ez)|debloqu",
            r"repond(ez|re) a \d+ questions",
            r"avant (minuit|ce soir)|aujourd'hui seulement",
            r"piece d'identite|\biban\b|\brib\b",
            r"\b(appelez|rappelez)\b",
        ),
        "Il t'annonce un gain ou un cadeau… à condition de payer ou de donner tes informations : un vrai gain ne"
        " demande jamais de payer.",
        poids=30,
    ),
    Famille(
        "crypto",
        "faux placement miracle",
        r"crypto|bitcoin|\bbtc\b|trading|placement|investi|rendement|livret|portefeuille|capital|\bgains?\b|giveaway",
        (
            r"garanti",
            r"sans (aucun )?risque",
            r"doubl",
            r"\d+ ?% (par|chaque) (semaine|mois|jour|an)|\d+ ?% par an",
            r"places? limitees|seulement \d+ places|reservee? a \d+|\d+ places|offre limitee|duree limitee",
            r"recevez-en|en retour|distribue",
            r"frais de (retrait|deblocage)|pour (les )?retirer|debloquer le retrait",
            r"envoyez .{0,20}(btc|bitcoin)",
            r"\d[\d ]* ?€ par (mois|jour|semaine)",
        ),
        "Il promet de gros gains « garantis » ou demande des frais pour récupérer ton argent : aucun placement"
        " sérieux ne garantit ça.",
        poids=35,
        vecteur_requis=False,
    ),
    Famille(
        "emploi",
        "faux recrutement ou « like » payé",
        r"recrut|emploi|travail|\bjob\b|mission|\bposte\b|teletravail|a domicile|candidature|\bcv\b|liker|likez"
        r"|\blike\b|taches|evaluez des produits|remuner",
        (
            r"\d+ ?€ ?(/|par) ?(jour|semaine|heure)|\d+ (a|à) \d+ ?€|\d+ ?€ (par|/) ?mois",
            r"whatsapp|telegram|wa\.me|t\.me",
            r"aucune experience",
            r"\bkit\b|frais d'inscription|achetez",
            r"\brib\b|\biban\b|carte d'identite|piece d'identite",
            r"reexpedi|receptionner (et|des) (re)?expedier|receptionner .{0,20}colis",
            r"repond(ez|re) oui",
            r"likez|liker|like des|taches simples|evaluez",
        ),
        "Une offre d'emploi trop facile (gros salaire, tâches simples, contact sur WhatsApp) : c'est une arnaque au"
        " faux recrutement.",
        poids=30,
    ),
    Famille(
        "regularisation",
        "faux impayé",
        r".",
        (r"regularis(ez|er)|defaut de paiement|facture (impayee|en retard)|\bimpaye", r"desactiv|coupure|suspen"),
        "Il te réclame un paiement « en retard » par un lien : vérifie toujours en allant toi-même sur le site ou"
        " l'appli officiels.",
    ),
)


@dataclass(frozen=True)
class Reconnaissance:
    famille: Famille
    accroches: int
    forte: bool


def reconnaitre(texte_normalise: str, vecteur: bool) -> list[Reconnaissance]:
    trouvees = []
    for f in FAMILLES:
        if not f.motif_theme().search(texte_normalise):
            continue
        if f.vecteur_requis and not vecteur:
            continue
        n = sum(1 for a in f.accroches if trouver(_compile(a), texte_normalise))
        forte = any(trouver(_compile(a), texte_normalise) for a in f.fortes)
        if n or forte:
            trouvees.append(Reconnaissance(f, n, forte))
    return trouvees


def signal_famille(r: Reconnaissance, action: str) -> Signal:
    poids = r.famille.poids + 8 * min(2, max(0, r.accroches - 1)) + (15 if r.forte else 0)
    return Signal(f"famille:{r.famille.id}", poids, r.famille.phrase.format(action=action), technique=False)
