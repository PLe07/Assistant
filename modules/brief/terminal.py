"""Le brief dans le Terminal : python assistant.py brief"""

from modules.brief import brief


def lancer() -> int:
    print("☀️ Je lis ton agenda, tes mails à traiter et tes rappels (sur ton Mac, sans Claude)…\n")
    print(brief.composer())
    return 0
