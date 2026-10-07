"""La ligne de commande `quotidien` (complétée phase après phase).

quotidien menu                      le menu de la semaine (créé s'il n'existe pas encore) et la liste de courses
quotidien menu --regenerer          un autre menu pour la même semaine
quotidien menu remplacer jeudi      un autre plat pour jeudi (les restes qui en dépendent suivent)
quotidien noter jeudi 👍            noter le repas de jeudi (👍 ou 👎) : le prochain menu en tient compte
quotidien envie "mexicain et léger" une envie pour le prochain menu
quotidien frigo "2 courgettes, feta" 3 recettes réalisables tout de suite (texte compris en local, 0 crédit)
quotidien frigo photo.jpg           la même chose depuis une photo (lue par l'IA, budget du pack)
quotidien frigo ce-soir 2           met la recette n°2 au menu de ce soir
quotidien frigo vider               oublie tout ce que tu m'as dit avoir
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from quotidien import __version__, config, reseau
from quotidien.db import Base
from quotidien.systeme import Systeme


@dataclass
class Environnement:
    reglages: config.Reglages
    db: Base
    systeme: Systeme
    horloge: Callable[[], float]

    def maintenant(self) -> datetime:
        return datetime.fromtimestamp(self.horloge())

    def aujourdhui(self) -> date:
        return self.maintenant().date()


def _ecrire(texte: str) -> None:
    print(texte)


# --- Menu, notes, envies (n°34) ----------------------------------------------------------------------------------


def cmd_menu(args: argparse.Namespace, env: Environnement) -> int:
    from quotidien.repas import planificateur as pl
    from quotidien.repas import service
    from quotidien.repas.base import charger

    base = charger()
    debut = service.semaine_affichee(env.reglages, env.maintenant())
    if args.action == "remplacer":
        if not args.jour:
            _ecrire("Quel jour ? Exemple : quotidien menu remplacer jeudi")
            return 2
        menu = service.menu_de(env.db, debut) or service.produire(env.db, env.reglages, debut, base=base).menu
        try:
            jour = service.jour_dans_menu(menu, args.jour)
            _, nouveau = pl.remplacer(env.db, env.reglages, jour, "dejeuner" if args.midi else "diner", base,
                                      env.horloge())  # fmt: skip
        except (service.JourInconnu, pl.JourIntrouvable) as e:
            _ecrire(f"❌ {e}")
            return 1
        _ecrire(f"✅ Nouveau plat : {service.ligne_repas(base, nouveau)}")
        resultat = service.produire(env.db, env.reglages, date.fromisoformat(menu.debut), base=base)
    else:
        resultat = service.produire(env.db, env.reglages, debut, regenerer=args.regenerer, base=base,
                                    maintenant=env.horloge())  # fmt: skip
    _ecrire(service.resume(resultat, base))
    return 0


def cmd_noter(args: argparse.Namespace, env: Environnement) -> int:
    from quotidien.repas import planificateur as pl
    from quotidien.repas import service
    from quotidien.repas.base import charger

    note = args.note.strip()
    if note in ("👍", "+", "+1", "bien", "oui", "j'aime", "aime"):
        valeur = 1
    elif note in ("👎", "-", "-1", "bof", "non", "pas aime"):
        valeur = -1
    else:
        _ecrire("La note est 👍 ou 👎 (ou + / -). Exemple : quotidien noter jeudi 👍")
        return 2
    try:
        jour = service.jour_passe(args.jour, env.aujourdhui())
        recette = pl.noter(env.db, jour, valeur, "dejeuner" if args.midi else "diner", env.horloge())
    except (service.JourInconnu, pl.JourIntrouvable) as e:
        _ecrire(f"❌ {e}")
        return 1
    nom = charger().recettes[recette].nom
    _ecrire(f"{'👍' if valeur > 0 else '👎'} Noté : {nom}. "
            + ("Il reviendra plus souvent." if valeur > 0 else "Il ne reviendra plus dans tes menus."))  # fmt: skip
    return 0


def cmd_envie(args: argparse.Namespace, env: Environnement) -> int:
    from quotidien.repas import envies
    from quotidien.repas import planificateur as pl

    texte = " ".join(args.texte).strip()
    if not texte:
        _ecrire('Écris ton envie : quotidien envie "mexicain et léger"')
        return 2
    criteres = envies.comprendre(env.db, env.reglages.reglages, texte, lire_trousseau=env.systeme.trousseau_lire)
    if criteres.vide():
        _ecrire("🤔 Je n'ai pas compris cette envie (essaie « italien », « léger », « pas de poisson »…).")
        return 1
    pl.ajouter_envie(env.db, criteres, env.horloge())
    _ecrire(f"✅ Envie notée pour le prochain menu : « {texte} »"
            + (" (comprise par l'IA)" if criteres.par_ia else ""))  # fmt: skip
    return 0


# --- Vide-frigo (n°35) ------------------------------------------------------------------------------------------


def cmd_frigo(args: argparse.Namespace, env: Environnement) -> int:
    from quotidien.frigo import service
    from quotidien.repas.base import charger

    mots = [m for m in args.texte if m.strip()]
    if not mots:
        _ecrire('Dis-moi ce que tu as : quotidien frigo "2 courgettes, un reste de riz, feta" (ou une photo)')
        return 2
    base = charger()
    if mots[0] == "ce-soir":
        if len(mots) != 2 or not mots[1].isdigit():
            _ecrire("Quelle recette ? Exemple : quotidien frigo ce-soir 2")
            return 2
        try:
            repas = service.ajouter_ce_soir(env.db, env.reglages, int(mots[1]), env.aujourdhui(), base,
                                            env.horloge())  # fmt: skip
        except service.ChoixImpossible as e:
            _ecrire(f"❌ {e}")
            return 1
        _ecrire(f"✅ Au menu ce soir : {base.recettes[repas.recette].nom}. La liste de courses suit.")
        return 0
    if mots == ["vider"]:
        service.vider(env.db)
        _ecrire("🧊 Frigo oublié : dis-moi ce que tu as la prochaine fois.")
        return 0
    chemin = Path(mots[0]).expanduser()
    if len(mots) == 1 and service.est_une_image(chemin):
        if not chemin.is_file():
            _ecrire(f"❌ Je ne trouve pas l'image {chemin.name}.")
            return 1
        reponse = service.depuis_photo(env.db, env.reglages, chemin, base, not args.sans_garder, env.horloge(),
                                       lire_trousseau=env.systeme.trousseau_lire)  # fmt: skip
    else:
        reponse = service.depuis_texte(env.db, env.reglages, " ".join(mots), base, not args.sans_garder,
                                       env.horloge())  # fmt: skip
    if args.creatif and not reponse.propositions and reponse.elements:
        reponse.creative, message = service.creer(env.db, env.reglages, reponse, base,
                                                  lire_trousseau=env.systeme.trousseau_lire)  # fmt: skip
        if message:
            reponse.message = "\n".join(x for x in (reponse.message, message) if x)
    _ecrire(service.formater(reponse, base, court=args.court))
    return 0 if reponse.propositions or reponse.creative is not None else 1


# --- Analyse des arguments ----------------------------------------------------------------------------------------

Commande = Callable[[argparse.Namespace, Environnement], int]


def analyseur() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="quotidien", description="Ton brief du quotidien : météo, menu, frigo, "
                                "anniversaires.")  # fmt: skip
    p.add_argument("--version", action="version", version=f"quotidien {__version__}")
    sous = p.add_subparsers(dest="commande", metavar="commande")

    m = sous.add_parser("menu", help="le menu de la semaine et la liste de courses")
    m.add_argument("action", nargs="?", choices=["remplacer"], help="remplacer le plat d'un jour")
    m.add_argument("jour", nargs="?", help="le jour à remplacer (lundi … dimanche)")
    m.add_argument("--regenerer", action="store_true", help="un autre menu pour cette semaine")
    m.add_argument("--midi", action="store_true", help="le déjeuner plutôt que le dîner")
    m.set_defaults(fonction=cmd_menu)

    n = sous.add_parser("noter", help="noter un repas 👍 ou 👎")
    n.add_argument("jour")
    n.add_argument("note")
    n.add_argument("--midi", action="store_true")
    n.set_defaults(fonction=cmd_noter)

    e = sous.add_parser("envie", help="une envie pour le prochain menu (« mexicain et léger »)")
    e.add_argument("texte", nargs="*")
    e.set_defaults(fonction=cmd_envie)

    f = sous.add_parser("frigo", help="ce que tu as → 3 recettes réalisables tout de suite")
    f.add_argument("texte", nargs="*", help="« 2 courgettes, feta », une photo, « ce-soir 2 » ou « vider »")
    f.add_argument("--creatif", action="store_true", help="si rien ne va, une idée originale par l'IA")
    f.add_argument("--sans-garder", action="store_true", help="ne pas retenir ce frigo pour le menu")
    f.add_argument("--court", action="store_true", help="réponse courte (pour l'iPhone)")
    f.set_defaults(fonction=cmd_frigo)
    return p


def preparer(systeme: Systeme | None = None, horloge: Callable[[], float] | None = None) -> Environnement:
    reseau.installer_garde()
    reglages = config.charger()
    return Environnement(reglages, Base(config.chemin_base()), systeme or Systeme(), horloge or time.time)


def main(argv: Sequence[str] | None = None, systeme: Systeme | None = None,
         horloge: Callable[[], float] | None = None) -> int:  # fmt: skip
    p = analyseur()
    args = p.parse_args(argv)
    fonction: Commande | None = getattr(args, "fonction", None)
    if fonction is None:
        p.print_help()
        return 0
    env = preparer(systeme, horloge)
    try:
        for a in env.reglages.avertissements:
            print(f"⚠️ {a}", file=sys.stderr)
        return fonction(args, env)
    finally:
        env.db.fermer()
