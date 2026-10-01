"""Le concierge ciné dans le Terminal : python assistant.py cine "envie de rire, 1h30" """

from core.cerveau import ClaudeIndisponible
from modules.cine import cine


def lancer(demande: str | None) -> int:
    print("🎬 Claude cherche 3 idées pour ce soir (10 à 20 s)…\n")
    try:
        print(cine.texte_proposition(cine.proposer(demande or "", "terminal")))
    except ClaudeIndisponible as e:
        print(f"⛔ {e}")
        return 1
    return 0
