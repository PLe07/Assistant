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
quotidien anniversaires             les prochains anniversaires (demande l'accès aux Contacts la première fois)
quotidien anniversaires message Léa les 3 messages prêts pour Léa
quotidien anniversaires ouvrir Léa 2  ouvre Messages avec le message n°2 (c'est toi qui appuies sur Envoyer)
quotidien brief                     le brief du jour, tout de suite (et la page « Ma journée »)
quotidien doctor                    l'état de chaque brique, les autorisations, le budget IA, les prochaines tâches
quotidien demon                     la boucle du démon (lancée par launchd ; --une-fois pour un seul tour)
quotidien installation …            ce que install.sh et uninstall.sh utilisent
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

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
    _synchroniser_courses(env, resultat.liste, base)
    return 0


def _synchroniser_courses(env: Environnement, liste: Any, base: Any) -> None:
    """Ta liste « Courses (menu) » dans Rappels suit chaque changement du menu (mode dégradé : rien)."""
    from quotidien import rappels_apple

    ajoutes = rappels_apple.synchroniser_courses(env.db, env.systeme, env.reglages.reglages, liste, base)
    if ajoutes:
        _ecrire(f"📝 Rappels « Courses (menu) » : {ajoutes} article(s) ajouté(s).")


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
    from quotidien.repas import service

    texte = " ".join(args.texte).strip()
    ok, message = service.noter_envie(env.db, env.reglages, texte, env.horloge(),
                                      lire_trousseau=env.systeme.trousseau_lire)  # fmt: skip
    _ecrire(message)
    return 0 if ok else (2 if not texte else 1)


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
        from quotidien.repas import planificateur as pl
        from quotidien.repas import service as menus

        menu = pl.menu_couvrant(env.db, env.aujourdhui())
        if menu is not None:  # la page du menu et la liste de Rappels suivent le changement
            resultat = menus.produire(env.db, env.reglages, date.fromisoformat(menu.debut), base=base)
            _synchroniser_courses(env, resultat.liste, base)
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


# --- Anniversaires (n°37) ----------------------------------------------------------------------------------------


def cmd_anniversaires(args: argparse.Namespace, env: Environnement) -> int:
    from quotidien.anniversaires import contacts, dates, proches, service
    from quotidien.repas.envies import normaliser
    from quotidien.repas.page import date_longue

    r = env.reglages.reglages
    aujourdhui = dates.aujourdhui(env.horloge(), r["lieu"]["fuseau"])
    if args.action is None and r["anniversaires"]["contacts"]:
        contacts.demander_acces()  # la fenêtre de macOS, une seule fois, depuis le Terminal
    a = service.annuaire(env.reglages, aujourdhui)
    for avertissement in a.avertissements:
        print(f"⚠️ {avertissement}", file=sys.stderr)
    regle = r["anniversaires"]["date_29_fevrier"]
    if args.action is None:
        etat = contacts.STATUTS.get(a.statut_contacts, "désactivés dans reglages.toml")
        avec = sum(1 for p in a.personnes if p.source == "contacts")
        _ecrire(f"Contacts : {etat} · {avec} anniversaire(s) trouvé(s) ; proches.toml : "
                f"{sum(1 for p in a.personnes if p.source == 'proches')}")  # fmt: skip
        prochains = service.a_venir(a.personnes, aujourdhui, 366, regle)[:20]
        if not prochains:
            _ecrire(
                f"Aucun anniversaire connu. Ajoute tes proches dans {proches.chemin()} (voir proches.example.toml)."
            )
        for jour, p in prochains:
            age = dates.age(p.naissance, jour)
            details = [f"{p.prenom}" + (f" ({age} ans)" if age else "")]
            if p.relation:
                details.append(p.relation.replace("_", " "))
            _ecrire(f"  {date_longue(jour)} · " + " · ".join(details))
        return 0
    if not args.prenom:
        _ecrire(f"De qui ? Exemple : quotidien anniversaires {args.action} Léa")
        return 2
    trouves = [x for x in service.a_venir(a.personnes, aujourdhui, 366, regle)
               if normaliser(x[1].prenom) == normaliser(args.prenom)]  # fmt: skip
    if not trouves:
        _ecrire(f"❌ Personne ne s'appelle {args.prenom} dans tes anniversaires.")
        return 1
    jour, personne = trouves[0]  # le plus proche
    m = service.message_pret(env.db, r, personne, jour, env.horloge(), lire_trousseau=env.systeme.trousseau_lire)
    if args.action == "message":
        _ecrire(f"🎂 {personne.prenom}, {date_longue(jour)} — 3 messages prêts :")
        for i, v in enumerate(m.variantes, 1):
            _ecrire(f"\n{i}. " + v.replace("\n", "\n   "))
        _ecrire(f"\nPour l'ouvrir dans Messages : quotidien anniversaires ouvrir {personne.prenom} 1 (ou 2, 3).")
        return 0
    if not 1 <= args.numero <= len(m.variantes):
        _ecrire("Le numéro du message va de 1 à 3.")
        return 2
    service.proposer_envoi(env.db, r, env.systeme, personne, jour, env.horloge(), args.numero)
    _ecrire("💬 Messages est ouvert avec ton message (il est aussi copié). Relis-le, puis appuie sur Envoyer.")
    return 0


# --- Brief, doctor, démon, installation (§7) ----------------------------------------------------------------------


def cmd_brief(args: argparse.Namespace, env: Environnement) -> int:
    from quotidien import brief, daemon
    from quotidien.anniversaires import service as anniv

    d = daemon.Demon(env.db, env.systeme, env.horloge)
    r = d.reglages()
    if args.notifier:  # exactement comme le démon à 7 h 15
        d._brief(r)
        _ecrire(env.db.lire_meta("brief:dernier") or "Rien de particulier aujourd'hui.")
        return 0
    jour = d.aujourdhui(r)
    a = d.annuaire(r)
    regle = r.reglages["anniversaires"]["date_29_fevrier"]
    b = brief.produire(env.db, r, jour, env.horloge(),
                       meteo=lambda: daemon._ligne_meteo(env.db, r, jour, env.horloge, d.c.telecharger),
                       anniversaires=lambda: anniv.ligne_brief(a.personnes, jour, regle))  # fmt: skip
    page = brief.publier(b)
    _ecrire(b.texte or "Rien de particulier aujourd'hui.")
    _ecrire(f"Page : {page}")
    return 0


def cmd_doctor(args: argparse.Namespace, env: Environnement) -> int:
    from quotidien import doctor

    lignes = doctor.bilan(env.db, env.reglages, env.systeme, env.horloge())
    _ecrire(doctor.texte(lignes))
    return 1 if any(x.etat == doctor.PROBLEME for x in lignes) else 0


def cmd_demon(args: argparse.Namespace, env: Environnement) -> int:  # pragma: no cover - lancé par launchd
    from quotidien import daemon

    if args.une_fois:
        t = daemon.Demon(env.db, env.systeme, env.horloge).tour()
        for f in t.fait:
            _ecrire(f"✅ {f}")
        for e in t.erreurs:
            _ecrire(f"❌ {e}")
        return 1 if t.erreurs else 0
    env.db.fermer()
    return daemon.principal()


def cmd_installation(args: argparse.Namespace, env: Environnement) -> int:
    from pathlib import Path as Chemin

    from quotidien import installation, rappels_apple

    r = env.reglages.reglages
    if args.etape == "label":
        print(installation.label(r))
        return 0
    if args.etape == "preparer":
        b = installation.preparer(r, Chemin(args.python), Chemin(args.projet))
    elif args.etape == "raccourcis":
        b = installation.raccourcis(config.dossier_support() / "raccourcis")
    elif args.etape == "verifier":  # pragma: no cover - sur le Mac, après l'installation
        b = installation.verifier_reel(r, env.db, env.systeme)
    elif args.etape == "listes":
        nos = rappels_apple.Rappels(env.db, env.systeme, r).nos_listes()
        _ecrire("\n".join(nos) if nos else "(aucune liste créée par Quotidien)")
        return 0
    elif args.etape == "supprimer-listes":
        retirees = rappels_apple.Rappels(env.db, env.systeme, r).supprimer_nos_listes()
        _ecrire("Listes supprimées : " + (", ".join(retirees) or "aucune"))
        return 0
    else:
        b = installation.desinstaller(r, tout=args.tout)
    for x in b.fait:
        _ecrire(f"  ✅ {x}")
    for x in b.avertissements:
        _ecrire(f"  ⚠️ {x}")
    for x in b.refus:
        _ecrire(f"  ❌ {x}")
    return 1 if b.refus else 0


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

    a = sous.add_parser("anniversaires", help="les prochains anniversaires et leurs messages prêts")
    a.add_argument("action", nargs="?", choices=["message", "ouvrir"])
    a.add_argument("prenom", nargs="?")
    a.add_argument("numero", nargs="?", type=int, default=1)
    a.set_defaults(fonction=cmd_anniversaires)

    b = sous.add_parser("brief", help="le brief du jour, tout de suite")
    b.add_argument("--notifier", action="store_true", help="comme le démon : notification et page")
    b.set_defaults(fonction=cmd_brief)

    sous.add_parser("doctor", help="l'état de chaque brique").set_defaults(fonction=cmd_doctor)

    d = sous.add_parser("demon", help="la boucle du démon (launchd)")
    d.add_argument("--une-fois", action="store_true")
    d.set_defaults(fonction=cmd_demon)

    i = sous.add_parser("installation", help="étapes de install.sh et uninstall.sh")
    i.add_argument("etape", choices=["label", "preparer", "raccourcis", "verifier", "listes", "supprimer-listes",
                                      "desinstaller"])  # fmt: skip
    i.add_argument("--python", default=sys.executable)
    i.add_argument("--projet", default=str(config.racine_projet()))
    i.add_argument("--tout", action="store_true")
    i.set_defaults(fonction=cmd_installation)
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
