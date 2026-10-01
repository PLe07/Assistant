"""Paramètres du rédacteur. Tout ce qui te concerne reste dans donnees/redacteur/ (jamais sur GitHub)."""

from core import config

DOSSIER = config.DONNEES / "redacteur"
STYLE = DOSSIER / "style.md"  # ta fiche de style (tu peux la retoucher à la main)
PROFIL = DOSSIER / "profil.md"  # tes infos pour les lettres de motivation (c'est toi qui les écris)
MES_TEXTES = DOSSIER / "mes_textes"  # des textes à toi, en plus de tes mails (posts, lettres…)
BROUILLONS = DOSSIER / "brouillons"

MAILS_MAX = 25  # tes derniers mails envoyés, lus sur ton Mac
EXTRAIT_MAX = 6000  # caractères de tes textes envoyés UNE fois à Claude pour faire la fiche
TEXTE_MAX = 1200  # par mail ou texte
TEXTE_MINI = 60  # un mail plus court (« ok merci ») n'apprend rien sur ton style

SIGNATURE = "Prénom et nom (pour signer)"
PROFIL_MODELE = f"""# Mon profil (pour signer, et pour les lettres de motivation)

Ce fichier reste sur ton Mac. Complète ce que tu veux après les deux-points ; le rédacteur
n'invente rien, une info absente devient [À COMPLÉTER] dans la lettre.

{SIGNATURE} :
Formation actuelle (diplôme, année) :
École / université :
Alternance recherchée (poste, rythme école/entreprise, date de début) :
Expériences (jobs, stages, associatif) :
Compétences et outils :
Ce qui me motive (secteur, métier visé, projet) :
Qualités que je veux mettre en avant :
"""
