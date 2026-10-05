"""L'index des apps installées : identifiant de bundle → chemin. Sert à trouver l'app parente d'un élément, à
savoir si elle a été désinstallée, et à parcourir les agents embarqués (S4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modules.demarrage.collecteurs.plists import lire
from modules.demarrage.systeme import Systeme


@dataclass
class App:
    chemin: str
    bundle_id: str | None
    nom: str
    executable: str | None = None  # chemin complet de Contents/MacOS/<CFBundleExecutable>


@dataclass
class Index:
    apps: list[App] = field(default_factory=list)

    def par_bundle(self, bundle_id: str) -> App | None:
        cible = bundle_id.casefold()
        return next((a for a in self.apps if a.bundle_id and a.bundle_id.casefold() == cible), None)

    def par_chemin(self, chemin: str) -> App | None:
        return next((a for a in self.apps if a.chemin == chemin), None)


def dossiers_apps(maison: str) -> list[str]:
    return ["/Applications", f"{maison}/Applications", "/System/Applications"]


def lire_app(systeme: Systeme, chemin: str) -> App:
    info, _ = lire(systeme.chemin(f"{chemin}/Contents/Info.plist"))
    info = info or {}
    nom = info.get("CFBundleDisplayName") or info.get("CFBundleName")
    executable = info.get("CFBundleExecutable")
    return App(
        chemin=chemin,
        bundle_id=info.get("CFBundleIdentifier") if isinstance(info.get("CFBundleIdentifier"), str) else None,
        nom=nom if isinstance(nom, str) and nom.strip() else chemin.rsplit("/", 1)[-1].removesuffix(".app"),
        executable=f"{chemin}/Contents/MacOS/{executable}" if isinstance(executable, str) else None,
    )


def indexer(systeme: Systeme) -> Index:
    """Les .app de premier niveau, et ceux rangés un niveau plus bas (/Applications/Utilities, dossiers d'éditeur)."""
    index = Index()
    for dossier in dossiers_apps(systeme.maison):
        racine = systeme.chemin(dossier)
        try:
            entrees = sorted(racine.iterdir())
        except OSError:
            continue
        for e in entrees:
            if e.name.endswith(".app"):
                index.apps.append(lire_app(systeme, f"{dossier}/{e.name}"))
            elif e.is_dir() and not e.name.startswith("."):
                try:
                    sous = sorted(x for x in e.iterdir() if x.name.endswith(".app"))
                except OSError:
                    continue
                index.apps += [lire_app(systeme, f"{dossier}/{e.name}/{x.name}") for x in sous]
    return index
