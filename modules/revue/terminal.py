"""La revue dans le Terminal : python assistant.py revue [derniere]"""

from core.cerveau import ClaudeIndisponible
from modules.revue import revue


def lancer(args: list[str]) -> int:
    if args and args[0] in ("derniere", "dernière"):
        texte = revue.derniere()
        print(texte or "🗓 Pas encore de revue : python assistant.py revue")
        return 0
    if args:
        print("Usage : python assistant.py revue            fait le bilan de ta semaine (1 appel à Claude)\n"
              "        python assistant.py revue derniere   relit la dernière revue (0 appel)")
        return 1
    print("🗓 Je rassemble ta semaine sur ton Mac, puis Claude écrit son mot (20 à 40 s)…\n")
    try:
        print(revue.texte_revue(revue.composer()))
    except ClaudeIndisponible as e:
        print(f"⛔ {e}")
        return 1
    return 0
