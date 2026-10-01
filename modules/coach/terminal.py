"""Le coach dans le Terminal : python assistant.py coach [cours|bilan]."""

import subprocess
import sys

from core.cerveau import ClaudeIndisponible
from modules.coach import parametres as p
from modules.coach import seance


def afficher_cours() -> int:
    """Les cours trouvés et lus (sur ton Mac, aucun appel à Claude)."""
    nouveau = not p.COURS.exists()
    p.COURS.mkdir(parents=True, exist_ok=True)
    fichiers = seance.indexer()
    print(f"📚 Tes cours : {p.COURS}")
    if not fichiers:
        print("   (vide) Crée un dossier par matière et COPIE-y tes cours (PDF, Word, RTF, texte).")
        print("   Exemple : « DCG UE11 Contrôle de gestion », « Droit des sociétés », « AMF ».")
        print("   Pour ouvrir le dossier dans le Finder :  open ~/Assistant/donnees/coach/cours")
        if nouveau and sys.platform == "darwin":
            subprocess.run(["open", str(p.COURS)], check=False)
    matiere = None
    for f in fichiers:
        if f["matiere"] != matiere:
            matiere = f["matiere"]
            print(f"\n   {matiere}")
        nom = f["chemin"][len(str(p.COURS)) + 1:]
        print(f"     ✅ {nom} : {f['morceaux']} morceau(x) d'une page" if not f["erreur"] else f"     ⚠️  {nom} : {f['erreur']}")
    sans = [m for m in p.sans_support() if m not in {f["matiere"] for f in fichiers if f["morceaux"]}]
    if sans:
        print(f"\n   Sans cours (questions du programme général, « à vérifier ») : {', '.join(sans)}")
    print(f"\nQuestions du jour : {p.nombre()} à {p.heure()} (si le coach est activé : python assistant.py activer coach)")
    return 0


def afficher_bilan() -> int:
    b = seance.bilan()
    if not any(m["reponses"] for m in b["matieres"]):
        print("🎓 Pas encore de bilan : réponds à ta première série (python assistant.py coach).")
        return 0
    print(f"🎓 Ton bilan · {b['serie_jours']} jour(s) d'affilée · {b['a_revoir']} question(s) à revoir d'ici demain\n")
    for m in b["matieres"]:
        moyenne = f"{m['moyenne']:.1f}/5" if m["moyenne"] is not None else "pas encore de note"
        print(f"   {m['matiere']} : {m['reponses']} réponse(s) corrigée(s) · moyenne {moyenne}")
        for notion, note, n in m["faibles"]:
            print(f"      ⚠️  à retravailler : {notion} ({note:.1f}/5 sur {n} réponse(s))")
    return 0


def seance_terminal() -> int:
    """Pose les questions du jour ici, puis corrige."""
    if not seance.serie():
        print("🎓 Je prépare tes questions du jour (10 à 30 s)…")
        try:
            seance.preparer()
        except (ClaudeIndisponible, seance.PasDeCours) as e:
            print(f"⛔ {e}")
            return 1
    s_liste = seance.serie()
    a_repondre = [s for s in s_liste if s["statut"] == "posee"]
    if a_repondre:
        print("Réponds puis Entrée. Entrée sans rien écrire = plus tard (tes réponses déjà données sont gardées).")
    for s in a_repondre:
        print(f"\n━━ Question {s['ordre']}/{len(s_liste)} · {s['matiere']} ━━\n{seance.texte_question(s)}")
        try:
            reponse = input("➜ ").strip()
        except (EOFError, KeyboardInterrupt):
            reponse = ""
        if not reponse:
            print("\nÀ plus tard : reprends avec  python assistant.py coach")
            return 0
        seance.repondre(s["seance"], reponse)
    if any(s["statut"] == "repondue" for s in seance.serie()):
        print("\n🎓 Correction (10 à 30 s)…")
        try:
            seance.corriger()
        except ClaudeIndisponible as e:
            print(f"⛔ {e}  (tes réponses sont gardées : relance  python assistant.py coach  plus tard)")
            return 1
    print("\n" + seance.texte_correction(seance.serie()))
    return 0
