from modules.demarrage.mesure import zsh
from modules.demarrage.systeme import Resultat

ZPROF = """num  calls                time                       self            name
-----------------------------------------------------------------------------------
 1)    1         245.12   245.12   60.25%    245.12   245.12   60.25%  nvm_auto
 2)    2          80.00    40.00   19.66%     70.00    35.00   17.20%  compinit
 3)    1          20.00    20.00    4.92%     20.00    20.00    4.92%  _omz_source
 4)    5          10.00     2.00    2.46%     10.00     2.00    2.46%  ma_fonction
"""


def test_analyser_zprof():
    lignes = zsh.analyser_zprof(ZPROF + "ligne parasite\n")
    assert [x["cause"] for x in lignes] == [
        "nvm (Node.js)",
        "compinit (complétion)",
        "oh-my-zsh et ses plugins",
        "ma_fonction",
    ]
    assert lignes[0]["ms"] == 245.12 and lignes[1]["ms"] == 70.0 and lignes[0]["part"] == 60.25
    assert zsh.cause_de("conda_init") == "conda" and zsh.cause_de("pyenv_x") == "pyenv"


def test_chronometrer(mac):
    durees = iter([0.2, 0.5, 0.25, 0.3, 0.9])
    mac.repondre(["zsh", "-i", "-c", "exit"], lambda c, m: Resultat(0, "", "", next(durees)))
    t = zsh.chronometrer(mac)
    assert t.mediane_ms == 300.0 and t.essais_ms == [200.0, 500.0, 250.0, 300.0, 900.0]
    mac.repondre(["zsh", "-i", "-c", "exit"], Resultat(2, "", "zsh: bad option", 0.1))
    assert zsh.chronometrer(mac).erreur.startswith("zsh a échoué (code 2)")
    mac.repondre(["zsh", "-i", "-c", "exit"], Resultat(124, "", "pas de réponse", 20.0))
    assert zsh.chronometrer(mac).erreur.startswith("zsh ne s'ouvre pas")
    mac.commandes.discard("zsh")
    assert zsh.chronometrer(mac).erreur == "zsh absent"


def test_profiler_isole_et_sans_trace(mac, tmp_path):
    zshrc = mac.fichier("/Users/utilisateur/.zshrc", "source ~/.nvm/nvm.sh\n")
    vus = {}

    def lancer(commande, m):
        copie = m.environnements[-1]["ZDOTDIR"]
        from pathlib import Path

        vus["zshenv"] = (Path(copie) / ".zshenv").read_text()
        vus["zshrc"] = (Path(copie) / ".zshrc").read_text()
        return Resultat(0, ZPROF, "", 0.5)

    mac.repondre(["zsh", "-i", "-c", "exit"], lancer)
    causes = zsh.profiler(mac, tmp_path / "temp")
    assert causes[0]["cause"] == "nvm (Node.js)"
    assert vus["zshenv"] == "zmodload zsh/zprof\n" and vus["zshrc"].endswith("\nzprof\n") and "nvm.sh" in vus["zshrc"]
    assert zshrc.read_text() == "source ~/.nvm/nvm.sh\n"  # ton fichier n'a pas bougé
    assert list((tmp_path / "temp").iterdir()) == []  # la copie est effacée


def test_mesurer_ne_profile_qu_au_dessus_du_seuil(mac, tmp_path):
    mac.repondre(["zsh", "-i", "-c", "exit"], Resultat(0, ZPROF, "", 0.1))
    assert zsh.mesurer(mac, tmp_path).causes == [] and len(mac.lancees("zsh")) == 5
    mac.repondre(["zsh", "-i", "-c", "exit"], Resultat(0, ZPROF, "", 0.4))
    t = zsh.mesurer(mac, tmp_path)
    assert t.mediane_ms == 400.0 and t.causes and len(mac.lancees("zsh")) == 11
