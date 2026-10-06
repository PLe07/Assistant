"""La pression psychologique et les demandes dangereuses (code, RIB, carte, identifiants…).

Ces signaux viennent du texte : ils ne peuvent qu'ajouter des points, jamais en retirer.
Une demande dans une phrase négative (« ne communiquez jamais ce code ») est une mise en garde, pas une demande.
"""

from __future__ import annotations

import re

from bouclier.arnaque.familles import trouver
from bouclier.arnaque.signaux import Signal


def _c(motif: str) -> re.Pattern[str]:
    return re.compile(motif)


URGENCE = _c(
    r"immediatement|sans delai|tout de suite|sous (12|24|48|72) ?h|dans les (24|48|72) ?h|avant (ce soir|minuit|demain"
    r"|aujourd'hui|\d+ ?h|le \d)|dernier (rappel|avis|delai|avertissement)|il (vous|te) reste|plus que \d"
    r"|expirent? (aujourd'hui|ce soir|demain|bientot)|\baujourd'hui\b|ce soir|\bvite\b|urgent|rapidement|presse"
    r"|des maintenant|d'ici demain"
)
MENACE = _c(
    r"suspendu|suspension|\bbloque|\bferme\b|cloture|desactiv|supprim|poursuites|huissier|saisie|majoration|majore"
    r"|penalite|coupure|coupee|resili|perdu|detruit|gendarmerie|police|plainte|judiciaire|enleve"
)
GAIN = _c(
    r"\bgagne|gagnant|cadeau|offert|gratuit|rembourse|remboursement|trop-?percu|\bprime\b|bonus|\bgains?\b"
    r"|felicitations|heritage|\btoucher\b|percevoir"
)
SECRET = _c(
    r"n'en parle(z)? (a personne|pas)|ne dites rien|confidentiel|ne contactez pas|ne raccrochez pas"
    r"|ne redemarrez pas|n'eteignez pas|ne l'eteignez pas|garde(z)? (le|ca) pour (vous|toi)"
)
_VERBE_DONNER = r"\b(communiqu|donn|transmet|transmett|lis|lire|lisez|dict|envoy|indiqu|saisi|entr|tap|fourni|precis)"

DEMANDE_CODE = _c(
    _VERBE_DONNER + r"\w*\b[^.!?\n]{0,40}\bcode\b"
    r"|\bcode\b[^.!?\n]{0,30}(a votre conseiller|au conseiller|a la conseillere|par telephone)"
    r"|activez[- ]les avec le code|avec (le|votre) code (recu|de validation|secret)"
    r"|preparez[- ]la avec votre code|avec votre code dans"
)
VALIDER_OPERATION = _c(
    r"\b(validez|acceptez|confirmez) (l'|cette |votre |la )?(operation|transaction|notification)"
    r"|\bvalidez[^.!?\n]{0,30}sur (votre|l') ?(application|appli)"
)
DEMANDE_CARTE = _c(
    r"numero de (votre |ta )?carte|cryptogramme|date d'expiration|\bcvv\b|\bcvc\b|16 chiffres"
    r"|\b(saisi\w*|confirm\w*|entr\w*|verifi\w*) (votre|ta|ma) carte|carte n'a pas pu etre verifiee"
    r"|vos informations bancaires|informations de paiement"
    r"|moyen de paiement|votre carte bancaire et"
)
DEMANDE_RIB = _c(
    r"\b(confirm|indiqu|saisi|transmet|transmett|envoy|donn|communiqu|mett|complet|renseign|fourni|precis|valid)\w*"
    r"[^.!?\n]{0,40}(\brib\b|\biban\b|coordonnees bancaires|informations bancaires|infos? ban[qc]aires?)"
    r"|(\brib\b|\biban\b)[^.!?\n]{0,25}(pour|afin)"
)
DEMANDE_IDENTIFIANTS = _c(
    r"\b(confirm|saisi|connect|entr|indiqu|communiqu|verifi|conserv)\w*[^.!?\n]{0,40}(identifiants|mot de passe"
    r"|code secret|code confidentiel|france ?connect)"
    r"|(identifiants|mot de passe)[^.!?\n]{0,30}(ici|en vous connectant)"
)
# Se connecter : suspect seulement si le message fournit le lien pour le faire.
CONNEXION_PAR_LIEN = _c(r"en vous (identifiant|connectant)|identifiez-vous|(re)?connectez-vous")
# « Validez votre compte » par un lien : on te fait passer par une fausse page de connexion.
DEMANDE_COMPTE = _c(
    r"\b(validez|verifiez|confirmez|activez|reactivez|debloquez|retablissez) (votre|ton) (compte|acces)"
    r"|retablissez l'acces|retablir (votre|l') ?acces"
)
# Envoyer de l'argent directement (« rembourser la différence », « faites-moi un virement »).
DEMANDE_VIREMENT = _c(
    r"\b(faire|faites|me faire|m'envoyer|envoyez|envoie|rembourser|remboursez|me rembourser|verser|versez)"
    r"[^.!?\n]{0,30}(virement|la difference|de l'argent|\d ?€)"
)
# « Prolongez la garde pour 1 € » : un ordre suivi d'un petit montant.
ORDRE_ET_MONTANT = _c(r"\b\w+ez\b[^.!?\n]{0,40}\bpour \d+([,.]\d+)? ?(€|eur)")
DEMANDE_IDENTITE = _c(
    r"(copie|photo|envoy\w*)[^.!?\n]{0,30}(piece d'identite|carte d'identite|passeport)"
    r"|numero de securite sociale"
)
COURSIER = _c(r"coursier|passer (chez vous|chez toi) (recuperer|chercher)|recuperer votre carte")
COUPONS = _c(r"carte pcs|transcash|neosurf|paysafecard|\bcoupons?\b|recharges? (pcs|de \d)")
VERBES_PAIEMENT = _c(
    r"\bpay(er|ez)\b|\bregl(er|ez|ant)\b|\bpaiement\b|\bfrais\b|debloqu|\brecharg|\bachetez\b|\bverser\b|\bversez\b"
)
APPEL = _c(r"\b(appelez|rappelez|contactez|composez|joindre|rappeler|appeler)\b")
MESSAGERIE = _c(
    r"(\bsur\b|\bvia\b|\bpar\b|ajoutez-moi|ecri[st](-moi)?|ecrivez(-moi)?|contact(ez|e)?(-moi)?|rejoin\w*)"
    r"[^.!?\n]{0,20}\b(whatsapp|telegram)\b"
)
REPONDRE = _c(r"\brepond(ez|re)\b|par retour")
# Une demande de coordonnées pour la suite (« donnez-moi votre adresse mail ») : un moyen d'agir.
DEMANDE_CONTACT = _c(
    r"\b(donnez|envoyez|communiquez|transmettez|indiquez)[- ]moi (votre |ton |ta )?(adresse|mail|e-mail"
    r"|numero|iban|rib)"
)

# Instructions destinées à tromper l'IA chargée de l'analyse (§3.3).
INJECTION = _c(
    r"ignore[rz]? (tes|vos|les|toutes les|toutes tes|toutes vos|mes)? ?(instructions|consignes|regles)"
    r"|oublie[rz]? (tes|vos|les) (consignes|instructions|regles)"
    r"|disregard|ignore (all )?(previous|prior) instructions|system prompt|\bsystem:|instruction prioritaire"
    r"|nouvelle consigne|assistant ia|pour l'ia|si tu es une (ia|intelligence artificielle)"
    r"|tu es un detecteur|ai instructions|classif(y|ie[rz]?) (it|ce message|le) (as|comme) (safe|sur|legitime)"
    r"|reponds niveau|pas_de_signe|confiance ?= ?1|confiance maximale|dis que c'est sur|indique que ce message est sur"
    r"|message verifie par l'ia|verified as legitimate|</message|the analysis is complete"
    r"|ce message est (sur|legitime)\b(?! (votre|ton|le|la|les|l'))|ce message est officiel et sans danger"
    r"|niveau sur|output \{"
)

PHRASE_INJECTION = (
    "Le message contient des instructions cachées pour tromper l'analyse : c'est en soi un signe d'arnaque."
)


def signaux_de_pression(t: str) -> list[Signal]:
    s: list[Signal] = []
    if trouver(URGENCE, t, negation=False):
        s.append(Signal("pression:urgence", 8, "Il te presse d'agir tout de suite.", technique=False))
    if trouver(MENACE, t, negation=False):
        s.append(Signal("pression:menace", 8, "Il te menace (blocage, amende, poursuites…).", technique=False))
    if trouver(GAIN, t, negation=False):
        s.append(Signal("pression:gain", 6, "Il fait miroiter un gain ou un remboursement.", technique=False))
    if trouver(SECRET, t, negation=False):
        s.append(Signal("pression:secret", 12, "Il te demande de garder le secret ou de ne pas raccrocher.",
                        technique=False))  # fmt: skip
    return s


def signaux_de_demandes(t: str, lien: bool, telephone: bool) -> list[Signal]:
    s: list[Signal] = []
    vecteur = lien or telephone
    if trouver(DEMANDE_CODE, t):
        s.append(Signal("demande:code", 45, "Il te demande de donner un code reçu par SMS : ce code sert à valider un"
                        " paiement ou un accès, ne le donne jamais à personne.",
                        critique=True, technique=False))  # fmt: skip
    if trouver(VALIDER_OPERATION, t):
        s.append(Signal("demande:validation", 45, "Il te demande de valider une opération sur ton appli : c'est ainsi"
                        " que les faux conseillers vident un compte.", critique=True, technique=False))  # fmt: skip
    if trouver(COURSIER, t) and re.search(r"\bcarte\b", t):
        s.append(Signal("demande:coursier", 45, "Personne (ni banque, ni police) n'envoie un coursier chercher ta"
                        " carte bancaire.", critique=True, technique=False))  # fmt: skip
    if trouver(DEMANDE_CARTE, t):
        s.append(Signal("demande:carte", 35, "Il te demande les numéros de ta carte bancaire : ne les saisis jamais à"
                        " partir d'un message reçu.", critique=lien, technique=False))  # fmt: skip
    if trouver(DEMANDE_RIB, t):
        s.append(Signal("demande:rib", 30, "Il te demande ton RIB ou tes coordonnées bancaires par message : c'est"
                        " ainsi que les escrocs préparent un vol.", technique=False))  # fmt: skip
    if trouver(DEMANDE_IDENTIFIANTS, t) or (lien and trouver(CONNEXION_PAR_LIEN, t)):
        s.append(Signal("demande:identifiants", 25, "Il te demande tes identifiants ou ton mot de passe : ne les"
                        " saisis jamais à partir d'un lien reçu.", technique=False))  # fmt: skip
    if trouver(DEMANDE_IDENTITE, t):
        s.append(Signal("demande:identite", 20, "Il te demande une copie de ta pièce d'identité ou ton numéro de"
                        " sécurité sociale.", technique=False))  # fmt: skip
    if trouver(COUPONS, t):
        s.append(Signal("demande:coupons", 35, "On te demande d'acheter des recharges ou coupons (PCS, Transcash…) et"
                        " d'en donner le code : c'est toujours une arnaque.", technique=False))  # fmt: skip
    if vecteur and (
        (trouver(VERBES_PAIEMENT, t) and re.search(r"\d\s?(€|eur\b|euros?\b)", t)) or trouver(ORDRE_ET_MONTANT, t)
    ):
        s.append(Signal("demande:paiement", 15, "Il te demande de payer par un lien ou un appel.", technique=False))
    if trouver(DEMANDE_VIREMENT, t):
        s.append(Signal("demande:virement", 20, "Il te demande de lui envoyer de l'argent.", technique=False))
    if lien and trouver(DEMANDE_COMPTE, t):
        s.append(Signal("demande:compte", 15, "Il te demande de « valider » ou de « débloquer » ton compte par un"
                        " lien : c'est souvent une fausse page de connexion.", technique=False))  # fmt: skip
    if trouver(MESSAGERIE, t, negation=False):
        s.append(Signal("demande:messagerie", 15, "Il veut continuer sur WhatsApp ou Telegram, loin des protections"
                        " habituelles.", technique=False))  # fmt: skip
    return s


def signal_injection(t: str) -> Signal | None:
    if INJECTION.search(t):
        return Signal("injection", 50, PHRASE_INJECTION, critique=True, technique=False)
    return None
