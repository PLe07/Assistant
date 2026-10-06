"""« Mes infos » de la fiche urgence : un fichier TOML commenté que tu remplis toi-même (`bouclier urgence editer`).

Tout est facultatif ; un champ vide n'apparaît pas sur la fiche. **Pas de données de santé** : un texte qui en
contient n'est pas imprimé (la Fiche médicale de l'app Santé de l'iPhone est faite pour ça, lisible depuis l'écran
verrouillé)."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

MODELE = """# Mes infos pour la fiche urgence de Bouclier.
# Tout est facultatif : ce qui reste vide n'apparaît pas sur la fiche.
# Ne mets AUCUNE donnée de santé ici (allergies, traitements, groupe sanguin…) : utilise plutôt la
# « Fiche médicale » de l'app Santé de l'iPhone, prévue pour ça et visible depuis l'écran verrouillé.
# Après une modification : bouclier urgence generer

# Ton nom, tel qu'il apparaîtra en haut de la fiche (ex. "Camille Martin").
nom = ""

# Jusqu'à 3 personnes à prévenir (copie le bloc pour en ajouter).
[[contacts]]
nom = ""          # ex. "Julie (sœur)"
telephone = ""    # ex. "06 12 34 56 78"

[operateur]
nom = ""                 # ton opérateur mobile, ex. "Free"
service_client = ""      # son numéro (pour suspendre la ligne si le téléphone est volé)

[banque]
nom = ""                 # ex. "La Banque Postale"
numero_carte_perdue = "" # le numéro écrit AU DOS de ta carte bancaire (pour faire opposition)

[ecran_verrouille]
# Le texte de l'image d'écran verrouillé, ex. "En cas d'urgence : appeler Julie au 06 12 34 56 78".
# Vide : le premier contact ci-dessus est utilisé.
texte = ""
"""

SANTE = re.compile(
    r"allerg|diab[eè]t|asthm|[ée]pilep|traitement|m[ée]dicament|groupe sanguin|\b(a|b|ab|o)\s?[+-]|insulin|cardiaque"
    r"|pathologie|maladie|handicap|enceinte|grossesse|vaccin",
    re.IGNORECASE,
)


@dataclass
class Contact:
    nom: str
    telephone: str


@dataclass
class MesInfos:
    nom: str = ""
    contacts: list[Contact] = field(default_factory=list)
    operateur: str = ""
    operateur_tel: str = ""
    banque: str = ""
    banque_tel: str = ""
    ecran: str = ""
    ecartes: list[str] = field(default_factory=list)  # textes écartés car ils ressemblent à des données de santé
    erreur: str | None = None

    @property
    def vide(self) -> bool:
        return not (self.nom or self.contacts or self.operateur_tel or self.banque_tel or self.ecran)


def _texte(valeur: object, nom_champ: str, infos: MesInfos) -> str:
    texte = str(valeur or "").strip()[:120]
    if texte and SANTE.search(texte):
        infos.ecartes.append(nom_champ)
        return ""
    return texte


def ecrire_modele_si_absent(chemin: Path) -> bool:
    if chemin.exists():
        return False
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(MODELE, encoding="utf-8")
    os.chmod(chemin, 0o600)
    return True


def charger(chemin: Path) -> MesInfos:
    infos = MesInfos()
    if not chemin.exists():
        return infos
    try:
        with chemin.open("rb") as f:
            brut = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        infos.erreur = f"{chemin.name} ne se lit pas ({e}) : corrige-le avec  bouclier urgence editer"
        return infos
    infos.nom = _texte(brut.get("nom"), "nom", infos)
    for c in brut.get("contacts") or []:
        if isinstance(c, dict):
            nom, tel = _texte(c.get("nom"), "contact", infos), _texte(c.get("telephone"), "contact", infos)
            if nom or tel:
                infos.contacts.append(Contact(nom, tel))
    infos.contacts = infos.contacts[:3]
    op, banque, ecran = brut.get("operateur") or {}, brut.get("banque") or {}, brut.get("ecran_verrouille") or {}
    infos.operateur = _texte(op.get("nom"), "opérateur", infos)
    infos.operateur_tel = _texte(op.get("service_client"), "opérateur", infos)
    infos.banque = _texte(banque.get("nom"), "banque", infos)
    infos.banque_tel = _texte(banque.get("numero_carte_perdue"), "banque", infos)
    infos.ecran = _texte(ecran.get("texte"), "écran verrouillé", infos)
    return infos
