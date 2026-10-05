"""S7 extensions, S8 assistants privilégiés, S9 cron, S10 fichiers zsh."""

from pathlib import Path

from modules.demarrage.collecteurs import extensions, helpers, planifie, shell
from modules.demarrage.modele import Fiche
from tests.demarrage.conftest import fixture
from tests.demarrage.outils import programme


def test_extensions():
    fiches = extensions.analyser(fixture("systemextensionsctl_list.txt"))
    par_label = {f.label: f for f in fiches}
    assert set(par_label) == {"com.exemple.vpn.tunnel", "com.exemple.pilote", "com.exemple.securite.extension"}
    vpn = par_label["com.exemple.vpn.tunnel"]
    assert vpn.nom == "Exemple VPN" and vpn.equipe == "AB12CD34EF" and vpn.actif and vpn.charge
    assert vpn.details["categorie"] == "network_extension" and vpn.details["version"] == "4.2.1/421"
    pilote = par_label["com.exemple.pilote"]
    assert pilote.actif is False and pilote.desactive and pilote.charge
    espaces = extensions.analyser("*  *  AB12CD34EF  com.x.y (1.0/1)  Nom Long  [activated enabled]\n")
    assert espaces[0].label == "com.x.y" and espaces[0].nom == "Nom Long"


def test_extensions_collecter(mac):
    mac.repondre(["systemextensionsctl", "list"], fixture("systemextensionsctl_list.txt"))
    assert len(extensions.collecter(mac)[0]) == 3
    mac.repondre(["systemextensionsctl", "list"], "", code=1, erreur="refusé")
    assert extensions.collecter(mac) == ([], ["systemextensionsctl : refusé"])
    mac.commandes.discard("systemextensionsctl")
    assert extensions.collecter(mac) == ([], ["systemextensionsctl absent"])


def test_assistants_privilegies(mac, monkeypatch):
    assert helpers.collecter(mac, []) == ([], [])
    programme(mac, "/Library/PrivilegedHelperTools/com.vpn.helper")
    programme(mac, "/Library/PrivilegedHelperTools/com.ancien.helper")
    mac.fichier("/Library/PrivilegedHelperTools/.DS_Store", b"")
    aide = "/Library/PrivilegedHelperTools/com.vpn.helper"
    daemon = Fiche(
        id="d", label="com.vpn.daemon", source="daemon_global", programme=aide, actif=True, charge=True, pids=[5]
    )
    fiches, erreurs = helpers.collecter(mac, [daemon])
    par_label = {f.label: f for f in fiches}
    assert erreurs == [] and set(par_label) == {"com.vpn.helper", "com.ancien.helper"}
    assert par_label["com.vpn.helper"].details["lance_par"] == "com.vpn.daemon" and par_label[
        "com.vpn.helper"
    ].pids == [5]
    assert par_label["com.ancien.helper"].details["sans_plist"] and par_label["com.ancien.helper"].actif is False

    def refus(self):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "iterdir", refus)
    assert "illisible" in helpers.collecter(mac, [])[1][0]


def test_cron(mac):
    programme(mac, "/Users/utilisateur/bin/sauvegarde.sh")
    programme(mac, "/usr/bin/true")
    fiches = planifie.analyser(mac, fixture("crontab.txt") + "* * *\n@weekly 'guillemet\n")
    par_label = {f.label: f for f in fiches}
    assert set(par_label) == {"cron : sauvegarde.sh", "cron : exemple-au-demarrage", "cron : true", "cron : 'guillemet"}
    sauvegarde = par_label["cron : sauvegarde.sh"]
    assert sauvegarde.programme_existe and sauvegarde.details["horaire"] == "*/30 * * * *"
    reboot = par_label["cron : exemple-au-demarrage"]
    assert (
        reboot.declencheurs.au_chargement
        and reboot.programme_existe is False
        and reboot.details["horaire"] == "au démarrage"
    )
    assert par_label["cron : 'guillemet"].details["horaire"] == "chaque semaine"


def test_cron_collecter(mac):
    mac.repondre(["crontab", "-l"], "", code=1, erreur=fixture("crontab_vide.txt"))
    assert planifie.collecter(mac) == ([], [])
    mac.repondre(["crontab", "-l"], "", code=1, erreur="autre souci")
    assert planifie.collecter(mac) == ([], ["crontab -l : autre souci"])
    mac.repondre(["crontab", "-l"], "@reboot /bin/x\n")
    assert len(planifie.collecter(mac)[0]) == 1
    mac.commandes.discard("crontab")
    assert planifie.collecter(mac) == ([], ["crontab absent"])


def test_shell(mac):
    mac.fichier("/Users/utilisateur/.zshrc", (
        'export NVM_DIR="$HOME/.nvm"\n[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"\n'
        "# source $ZSH/oh-my-zsh.sh  (commenté : ignoré)\nsource $ZSH/oh-my-zsh.sh\nautoload -U compinit; compinit\n"
        "compinit -C\nexport API_TOKEN=secret-ne-pas-garder\neval \"$(pyenv init -)\"\n"
    ))  # fmt: skip
    mac.fichier("/Users/utilisateur/.zprofile", 'eval "$(/opt/homebrew/bin/brew shellenv)"\n')
    rapport, erreurs = shell.collecter(mac)
    assert erreurs == [] and rapport["fichiers"] == {".zprofile": 1, ".zshrc": 8}
    causes = [(s["fichier"], s["ligne"], s["cause"]) for s in rapport["suspects"]]
    assert ("~/.zshrc", 1, "nvm (Node.js)") in causes and ("~/.zshrc", 4, "oh-my-zsh") in causes
    assert ("~/.zshrc", 5, "compinit (complétion recalculée à chaque Terminal)") in causes
    assert not any(ligne == 6 for _, ligne, _ in causes)  # compinit -C : déjà rapide
    assert ("~/.zprofile", 1, "brew shellenv") in causes and ("~/.zshrc", 8, "pyenv") in causes
    assert "secret" not in repr(rapport)  # jamais le texte des lignes


def test_shell_cas_limites(mac, monkeypatch):
    assert shell.collecter(mac) == ({"fichiers": {}, "suspects": []}, [])
    gros = mac.fichier("/Users/utilisateur/.zshenv", b"#")
    monkeypatch.setattr(shell, "TAILLE_MAX", 0)
    assert "trop gros" in shell.collecter(mac)[1][0]
    monkeypatch.setattr(shell, "TAILLE_MAX", 10)
    gros.write_bytes(b"x")

    def refus(self, *a, **k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "read_text", refus)
    assert "illisible" in shell.collecter(mac)[1][0]
