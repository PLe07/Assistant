from modules.demarrage.anonymat import Secrets, anonymiser, fuites, sans_accents

SECRETS = Secrets(
    maison="/Users/jdupont",
    compte="jdupont",
    nom_complet="Jérôme Dupont",
    ordinateurs=["MacBook Air de Jérôme", "MacBook-Air-de-Jerome"],
)


def test_remplace_maison_compte_nom_ordinateur():
    texte = (
        "path = /Users/jdupont/Library/LaunchAgents/x.plist\n"
        "jdupont  console  Mon Oct  5 06:54\n"
        "Nom : Jérôme Dupont sur MacBook Air de Jérôme (MacBook-Air-de-Jerome.local)\n"
        "label com.jdupont.outil\n"
    )
    propre = anonymiser(texte, SECRETS)
    assert "/Users/utilisateur/Library/LaunchAgents/x.plist" in propre
    assert "utilisateur  console" in propre
    assert "com.utilisateur.outil" in propre
    assert "Utilisateur Exemple" in propre
    assert fuites(propre, SECRETS) == []


def test_e_mails_et_uuid():
    un, deux = "8A1C0B2D-1111-2222-3333-444455556666", "9B1C0B2D-1111-2222-3333-444455556666"
    texte = f"contact jerome.dupont@exemple-perso.com {un} et {un.lower()} puis {deux}"
    propre = anonymiser(texte, SECRETS)
    assert "adresse@exemple.fr" in propre and "@exemple-perso" not in propre
    assert propre.count("00000000-0000-0000-0000-000000000001") == 2  # le même UUID, la même valeur
    assert "00000000-0000-0000-0000-000000000002" in propre


def test_le_prenom_sans_accent_aussi():
    propre = anonymiser("Jerome a lancé l'outil", SECRETS)
    assert "Jerome" not in propre and fuites(propre, SECRETS) == []


def test_fuites_detecte_ce_qui_reste():
    assert "jdupont" in fuites("le dossier jdupontine", SECRETS)  # prudence : même dans un autre mot
    assert "/Users/jdupont" in fuites("/USERS/JDUPONT/x", SECRETS)
    assert fuites("écrire à quelqu.un@ailleurs.org", SECRETS) == ["quelqu.un@ailleurs.org"]


def test_mots_courts_et_generiques_ignores():
    s = Secrets(maison="/Users/al", compte="al", nom_complet="Al Bo", ordinateurs=["Mac mini"])
    assert s.mots() == ["Mac mini"]  # le nom entier compte, ses mots génériques non
    assert anonymiser("Al sur Mac mini Studio", s) == "Al sur Mac Studio"


def test_masquer_a_la_main():
    s = Secrets(maison="/Users/x", compte="xx", autres=["Société Secrète"])
    propre = anonymiser("chez Société Secrète", s)
    assert "Secrète" not in propre and fuites(propre, s) == []


def test_sans_accents():
    assert sans_accents("Éléonore à l'île") == "Eleonore a l'ile"
