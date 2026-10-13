"""Un catalogue de référence (les apps d'un Mac courant, dossiers, sites, alias, routines, playlists) pour les tests
et les corpus : déterministe, sans dépendre de ce qui est installé sur la machine de construction."""

from __future__ import annotations

from pathlib import Path

from voix.nlu.alias import Commandes, lire
from voix.nlu.catalogue import Catalogue, Objet, apps_connues, dossiers, objet_app, sites

MAISON = Path("/Users/exemple")

# Les apps installées sur ce Mac imaginaire (bundle id, nom du paquet .app).
APPS = [
    ("com.apple.Safari", "Safari"), ("com.apple.mail", "Mail"), ("com.apple.MobileSMS", "Messages"),
    ("com.apple.FaceTime", "FaceTime"), ("com.apple.Notes", "Notes"), ("com.apple.reminders", "Reminders"),
    ("com.apple.iCal", "Calendar"), ("com.apple.AddressBook", "Contacts"), ("com.apple.Maps", "Maps"),
    ("com.apple.Photos", "Photos"), ("com.apple.Music", "Music"), ("com.apple.podcasts", "Podcasts"),
    ("com.apple.TV", "TV"), ("com.apple.iBooksX", "Books"), ("com.apple.AppStore", "App Store"),
    ("com.apple.systempreferences", "System Settings"), ("com.apple.calculator", "Calculator"),
    ("com.apple.TextEdit", "TextEdit"), ("com.apple.Preview", "Preview"), ("com.apple.Terminal", "Terminal"),
    ("com.apple.ActivityMonitor", "Activity Monitor"), ("com.apple.finder", "Finder"),
    ("com.apple.shortcuts", "Shortcuts"), ("com.apple.weather", "Weather"), ("com.apple.clock", "Clock"),
    ("com.apple.VoiceMemos", "VoiceMemos"), ("com.apple.freeform", "Freeform"),
    ("com.apple.QuickTimePlayerX", "QuickTime Player"), ("com.apple.iWork.Numbers", "Numbers"),
    ("com.apple.iWork.Pages", "Pages"), ("com.apple.iWork.Keynote", "Keynote"), ("com.apple.dt.Xcode", "Xcode"),
    ("com.microsoft.VSCode", "Visual Studio Code"), ("com.googlecode.iterm2", "iTerm"), ("notion.id", "Notion"),
    ("com.spotify.client", "Spotify"), ("com.google.Chrome", "Google Chrome"), ("org.mozilla.firefox", "Firefox"),
    ("com.tinyspeck.slackmacgap", "Slack"), ("com.hnc.Discord", "Discord"), ("net.whatsapp.WhatsApp", "WhatsApp"),
    ("us.zoom.xos", "zoom.us"), ("com.microsoft.teams2", "Microsoft Teams"), ("com.microsoft.Word", "Microsoft Word"),
    ("com.microsoft.Excel", "Microsoft Excel"), ("com.microsoft.Powerpoint", "Microsoft PowerPoint"),
    ("com.openai.chat", "ChatGPT"), ("com.anthropic.claudefordesktop", "Claude"), ("md.obsidian", "Obsidian"),
    ("com.figma.Desktop", "Figma"), ("org.videolan.vlc", "VLC"), ("ru.keepcoder.Telegram", "Telegram"),
    ("com.1password.1password", "1Password"), ("com.docker.docker", "Docker"),
    ("com.example.Inconnue", "Grapheur Pro 3"),  # une app sans forme connue : formes générées seulement
]  # fmt: skip

COMMANDES = """
[[alias]]
nom = "la compta"
cible = "~/Documents/Compta.numbers"
formes = ["ma compta", "comptabilite"]

[[alias]]
nom = "mes cours"
cible = "~/Documents/Cours"

[[playlist]]
nom = "Révisions"
lecteur = "musique"

[[playlist]]
nom = "Jazz du soir"
lecteur = "spotify"
uri = "spotify:playlist:37i9dQZF1DXbITWG1ZJKYt"

[[routine]]
nom = "révision"
phrases = ["lance ma révision", "mode révision", "on révise"]
etapes = [{ intention = "app.ouvrir", app = "Notion" }]

[[routine]]
nom = "fin de journée"
phrases = ["fin de journée", "je termine ma journée"]
sensible = true
etapes = [{ intention = "app.fermer_tout" }]
"""

RACCOURCIS = ["Envoyer au Mac", "Activer concentration", "Désactiver concentration", "Mode lecture", "Heure du café"]


def commandes() -> Commandes:
    return lire(COMMANDES, MAISON)


def catalogue(classes: bool = True) -> Catalogue:
    connues = apps_connues()
    objets = [objet_app(b, nom, f"/Applications/{nom}.app", connues) for b, nom in APPS]
    objets += dossiers(MAISON, existe=lambda _p: classes)
    objets += sites()
    objets += [Objet("raccourci", r, r, f"raccourci:{r}", (r.lower(),)) for r in RACCOURCIS]
    objets += commandes().objets()
    return Catalogue(objets)
