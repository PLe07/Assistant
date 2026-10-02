"""Le coach dans le Terminal : python assistant.py coach [cours|bilan]."""

import subprocess
import sys

from core.cerveau import ClaudeIndisponible
from modules.coach import cours
from modules.coach import parametres as p
from modules.coach import seance


def afficher_cours() -> int:
    """Les cours trouvés et lus, UE par UE (sur ton Mac, aucun appel à Claude)."""
    nouveau = not p.COURS.exists()
    cours.creer_dossiers()
    fichiers = seance.indexer()
    print(f"📚 Tes cours : {p.COURS}")
    print("   Un dossier par UE (déjà créés). COPIE-y tes cours : PDF, Word, RTF ou texte.\n")
    par_ue = {ue: [f for f in fichiers if f["matiere"] == ue] for ue in p.UE}
    for ue, liste in par_ue.items():
        if not liste:
            print(f"   {ue} : pas de cours (questions sur le programme officiel)")
            continue
        print(f"   {ue} :")
        for f in liste:
            nom = f["chemin"][len(str(p.COURS)) + 1:]
            print(f"     ✅ {nom} : {f['morceaux']} morceau(x) d'une page" if not f["erreur"] else f"     ⚠️  {nom} : {f['erreur']}")
    perdus = [f for f in fichiers if not f["matiere"]]
    for f in perdus:
        print(f"   ⚠️  {f['chemin'][len(str(p.COURS)) + 1:]} : {f['erreur']}")
    print("\nPour ouvrir le dossier :  open ~/Assistant/donnees/coach/cours")
    if nouveau and sys.platform == "darwin":
        subprocess.run(["open", str(p.COURS)], check=False)
    return 0


def afficher_bilan() -> int:
    print("🎓 Ton bilan\n" + seance.texte_bilan())
    return 0


def _lire(invite: str) -> str:
    try:
        return input(invite).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def seance_terminal() -> int:
    """Choisis une UE et un nombre de questions, réponds ici, puis la correction."""
    print("🎓 Sur quelle UE veux-tu être interrogé ?")
    for i, ue in enumerate(p.UE, 1):
        revoir = seance.a_revoir(ue)
        print(f"   {i:>2}. {ue}" + (f"  ({revoir} à revoir)" if revoir else ""))
    choix = _lire("➜ Numéro de l'UE (Entrée = annuler) : ")
    if not choix.isdigit() or not 1 <= int(choix) <= len(p.UE):
        print("Annulé.")
        return 0
    ue = p.UE[int(choix) - 1]
    cle = seance.en_cours(ue)
    if cle:
        print(f"\nTu as une séance de {ue} pas finie : on la reprend.")
    else:
        n = p.nombre(_lire(f"➜ Combien de questions ? ({p.MIN_QUESTIONS} à {p.MAX_QUESTIONS}, Entrée = {p.PAR_DEFAUT}) : "))
        print(f"\n🎓 Je prépare {n} questions de {ue} (10 à 30 s)…")
        try:
            cle = seance.preparer(ue, n)
        except ClaudeIndisponible as e:
            print(f"⛔ {e}")
            return 1
    s_liste = seance.seance(cle)
    a_repondre = [s for s in s_liste if s["statut"] == "posee"]
    if a_repondre:
        print("Réponds puis Entrée. Entrée sans rien écrire = plus tard (tes réponses déjà données sont gardées).")
    for s in a_repondre:
        print(f"\n━━ Question {s['ordre']}/{len(s_liste)} · {s['matiere']} ━━\n{seance.texte_question(s)}")
        reponse = _lire("➜ ")
        if not reponse:
            print("\nÀ plus tard : reprends avec  python assistant.py coach  (même UE)")
            return 0
        seance.repondre(s["seance"], reponse)
    if any(s["statut"] == "repondue" for s in seance.seance(cle)):
        print("\n🎓 Correction (10 à 30 s)…")
        try:
            seance.corriger(cle)
        except ClaudeIndisponible as e:
            print(f"⛔ {e}  (tes réponses sont gardées : relance  python assistant.py coach  plus tard)")
            return 1
    print("\n" + seance.texte_correction(seance.seance(cle)))
    return 0
