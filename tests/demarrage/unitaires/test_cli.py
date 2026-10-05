from modules.demarrage import cli


def contexte(reglages, mac):
    lignes: list[str] = []
    return cli.Contexte(reglages, mac, lignes.append), lignes


def test_aide(capsys):
    assert cli.main([]) == 0
    assert "doctor" in capsys.readouterr().out


def test_doctor_tout_va_bien(reglages, mac):
    mac.repondre(["uname", "-m"], "arm64\n")
    mac.repondre(["sw_vers", "-productVersion"], "26.0\n")
    ctx, lignes = contexte(reglages, mac)
    assert cli.main(["doctor"], ctx) == 0
    texte = "\n".join(lignes)
    assert "macOS 26.0 · arm64" in texte and "❌" not in texte and "absente" not in texte


def test_doctor_mode_degrade(reglages, mac):
    mac.commandes -= {"sfltool", "pmset"}
    ctx, lignes = contexte(reglages, mac)
    assert cli.main(["doctor"], ctx) == 0
    texte = "\n".join(lignes)
    assert "sfltool" in texte and "2 commande(s) absente(s)" in texte
