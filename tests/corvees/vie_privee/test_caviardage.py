"""Le caviardage : chaque secret disparaît, et ce qui n'est pas un secret reste intact."""

import pytest

from modules.corvees.privacy import caviarder, caviarder_valeur

POSITIFS = [
    ("écris à prenom.nom@exemple.fr demain", "écris à [e-mail] demain"),
    ("appelle le 06 12 34 56 78", "appelle le [téléphone]"),
    ("tel:+33612345678", "tel:[téléphone]"),
    ("0033 1 23 45 67 89 standard", "[téléphone] standard"),
    ("virement FR76 3000 6000 0112 3456 7890 189 ok", "virement [IBAN] ok"),
    ("RIB_FR7630006000011234567890189.pdf", "RIB_[IBAN].pdf"),
    ("carte 4111 1111 1111 1111 exp", "carte [carte] exp"),
    ("4111-1111-1111-1111", "[carte]"),
    ("export ANTHROPIC_API_KEY=sk-ant-api03-AbCdEf123456", "export ANTHROPIC_API_KEY=[secret]"),
    ("clé sk-ant-api03-ZZZZZZZZZZZZZZZZ fin", "clé [secret] fin"),
    ("OPENAI sk-proj1234567890abcdefXYZ", "OPENAI [secret]"),
    ("git clone https://ghp_abcdefghijklmnopqrstuvwxyz0123@github.com/x/y", "git clone https://github.com/x/y"),
    ("token ghp_abcdefghijklmnopqrstuvwxyz0123", "token [secret]"),
    ("mysql -u root -pS3cret! base", "mysql -u root -p [secret] base"),
    ("mysql -u root -p 'mot de passe' base", "mysql -u root -p [secret] base"),
    ("sshpass -p hunter2 ssh serveur", "sshpass -p [secret] ssh serveur"),
    ("curl --password=hunter2 x", "curl --password=[secret] x"),
    ("app --token abc123def x", "app --token [secret] x"),
    ("PASSWORD=hunter2 ./lancer.sh", "PASSWORD=[secret] ./lancer.sh"),
    ("export DB_PASSWORD='x y'", "export DB_PASSWORD=[secret]"),
    ("TOKEN=abc ./go", "TOKEN=[secret] ./go"),
    ("https://site.fr/page?utm_source=x&id=42#ancre", "https://site.fr/page"),
    ("https://moi:secret@serveur.fr/depot", "https://serveur.fr/depot"),
    ("hash 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08", "hash [secret]"),
    ("cle QWxhZGRpbjpvcGVuIHNlc2FtZQQWxhZGRpbjpvcGVuIHNl==", "cle [secret]"),
    ("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N", "jwt [secret]"),
    ("Authorization: Bearer abcdef0123456789.xyz", "Authorization: [secret]"),
    ("-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----", "[clé privée]"),
]

NEGATIFS = [
    "mkdir -p ~/Projets/assistant",
    "git log --oneline -n 20",
    "python main.py --port 8080",
    "Facture_2026-10-03.pdf",
    "IMG_20261003_143210.HEIC",
    "https://mail.google.com/mail/u/0/",
    "cd ~/Projets/assistant && git pull && python main.py",
    "ls -la ~/Documents",
    "Note du 12/10 : réviser le chapitre 4",
    "1234 5678 9012 3456",  # n'a pas la forme d'une vraie carte (Luhn faux)
    "FR12 3456",  # trop court pour un IBAN
    "version 2.4.1 publiée",
    "ssh -p 2222 serveur",
    "psql -p 5432 base",
]


@pytest.mark.parametrize(("brut", "attendu"), POSITIFS)
def test_chaque_secret_disparait(brut, attendu):
    assert caviarder(brut) == attendu


@pytest.mark.parametrize("brut", NEGATIFS)
def test_ce_qui_n_est_pas_secret_reste_intact(brut):
    assert caviarder(brut) == brut


def test_caviardage_dans_une_structure():
    v = caviarder_valeur({"titre": "à moi@x.fr", "liste": ["06 12 34 56 78", 3], "n": 2.5, "rien": None})
    assert v == {"titre": "à [e-mail]", "liste": ["[téléphone]", 3], "n": 2.5, "rien": None}


def test_texte_vide():
    assert caviarder("") == ""
