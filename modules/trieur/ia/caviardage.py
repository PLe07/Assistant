"""Le caviardage (§6) : ce qui pourrait t'identifier est remplacé avant que le texte parte chez Claude.

Masqués : courriels, IBAN, numéros de carte (clé de Luhn), numéro de sécurité sociale, numéros fiscaux et tout
long numéro (client, contrat, dossier), téléphones, adresses (rue et code postal + ville), le nom qui suit
« Titulaire : », « Patient : »…, et les mots de ta liste (reglages → ia.mots_masques : ton nom, par exemple).
Gardés : les dates, les montants, les noms des entreprises, les mots du document.
"""

from __future__ import annotations

import re

COURRIEL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[  ]?[A-Z0-9]){11,30}\b")
NIR = re.compile(r"(?<!\d)[12][  .]?\d{2}[  .]?(?:0[1-9]|1[0-2]|[2-9]\d)[  .]?(?:\d{2}|2A|2B)"
                 r"[  .]?\d{3}[  .]?\d{3}(?:[  .]?\d{2})?(?!\d)")  # fmt: skip
CHIFFRES = re.compile(r"(?<![\d,.])\d(?:[  .-]?\d){8,}(?![\d,])")  # 9 chiffres ou plus, groupés ou non
TELEPHONE = re.compile(r"(?:\+33[  .]?|0033[  .]?|(?<!\d)0)[1-9](?:[  .-]?\d{2}){4}(?!\d)")
RUE = re.compile(
    r"\b\d{1,4}(?:[  ]?(?:bis|ter|b))?,?[  ]+(?:rue|avenue|av\.|boulevard|bd|place|chemin|all[ée]e|impasse|"
    r"quai|route|cours|square|r[ée]sidence|lotissement|lieu-dit|passage|voie|sentier|hameau)\b[^\n·|]*",
    re.IGNORECASE,
)
CODE_POSTAL = re.compile(r"(?<!\d)(?:F-)?\d{5}[  ]+(?:cedex\b[ \d]*)?[A-ZÀ-Ýa-zà-ÿ][\wÀ-ÿ'’ -]{1,40}", re.IGNORECASE)
APRES_ETIQUETTE = re.compile(
    r"(?P<etiquette>\b(?:titulaire|patient|patiente|salari[ée]e?|locataire|passager|passag[èe]re|adh[ée]rent|"
    r"assur[ée]e?|allocataire|client|b[ée]n[ée]ficiaire|nom|pr[ée]noms?|n[ée]\(?e?\)? le|destinataire|"
    r"[ée]l[èe]ve|[ée]tudiant)\b\s*:\s*)(?P<valeur>[^\n:]{2,60})",
    re.IGNORECASE,
)


def luhn(chiffres: str) -> bool:
    total = 0
    for i, c in enumerate(reversed(chiffres)):
        n = int(c)
        if i % 2:
            n = n * 2 - 9 if n * 2 > 9 else n * 2
        total += n
    return total % 10 == 0


def _numero(m: re.Match[str]) -> str:
    chiffres = re.sub(r"\D", "", m.group(0))
    if 13 <= len(chiffres) <= 19 and luhn(chiffres):
        return "[carte]"
    return "[numéro]"


NOM_PROPRE = re.compile(r"^[A-ZÀ-Ý][\wÀ-ÿ'’-]+(?:[ \u00a0]+[A-ZÀ-Ý][\wÀ-ÿ'’-]+){1,3}$")


def _nom_avant_adresse(texte: str) -> str:
    """Le bloc du destinataire (« Prénom Nom », puis la rue) : la ligne au-dessus d'une adresse est masquée si elle
    ressemble à un nom de personne."""
    lignes = texte.split("\n")
    for i in range(len(lignes) - 1):
        if lignes[i + 1].strip().startswith("[adresse]") and NOM_PROPRE.match(lignes[i].strip()):
            lignes[i] = "[nom]"
    return "\n".join(lignes)


def caviarder(texte: str, mots: list[str] | None = None, longueur_max: int | None = None) -> str:
    t = COURRIEL.sub("[courriel]", texte)
    t = IBAN.sub("[iban]", t)
    t = NIR.sub("[n° sécu]", t)
    t = TELEPHONE.sub("[téléphone]", t)
    t = CHIFFRES.sub(_numero, t)
    t = RUE.sub("[adresse]", t)
    t = CODE_POSTAL.sub("[ville]", t)
    t = APRES_ETIQUETTE.sub(lambda m: m.group("etiquette") + "[nom]", t)
    t = _nom_avant_adresse(t)
    for mot in mots or []:
        if mot.strip():
            t = re.sub(re.escape(mot.strip()), "[nom]", t, flags=re.IGNORECASE)
    if longueur_max is not None and len(t) > longueur_max:
        t = t[:longueur_max]
    return t
