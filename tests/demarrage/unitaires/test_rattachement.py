from modules.demarrage.mesure.rattachement import Proc, rattacher
from modules.demarrage.modele import Fiche


def proc(pid, comm, ppid=1):
    return Proc(pid, ppid, 501, 0.0, 1000, 10.0, 1.0, comm)


def test_ordre_de_rattachement():
    docker = "/Applications/Docker.app"
    agent = Fiche(
        id="agent", label="com.docker.socket", source="agent_utilisateur",
        programme=f"{docker}/Contents/MacOS/backend", app_parente=docker,
    )  # fmt: skip
    ouverture = Fiche(
        id="ouv", label="com.docker.docker", source="ouverture", programme=f"{docker}/Contents/MacOS/Docker",
        app_parente=docker,
    )  # fmt: skip
    script = Fiche(id="script", label="com.script", source="agent_utilisateur", programme="/Users/u/run.sh")
    procs = [
        proc(10, "/bin/bash"),  # lancé par launchd pour com.script : son PID le dit
        proc(11, "/usr/bin/caffeinate", ppid=10),  # fils du script
        proc(20, "/Applications/Docker.app/Contents/MacOS/backend"),  # par son exécutable
        proc(21, "/Applications/Docker.app/Contents/MacOS/vm", ppid=20),  # fils
        proc(22, "/Applications/Docker.app/Contents/MacOS/petitfils", ppid=21),  # petit-fils
        proc(30, "/Applications/Docker.app/Contents/XPCServices/x.xpc/Contents/MacOS/x"),  # bundle → app d'ouverture
        proc(31, "/Applications/Docker.app/Contents/MacOS/autre", ppid=999),  # parent inconnu : rien
        proc(40, "/usr/libexec/inconnu"),
    ]
    r = rattacher(procs, [agent, ouverture, script], {"com.script": 10, "com.absent": 77, "inconnu": 40})
    assert r == {10: "script", 11: "script", 20: "agent", 21: "agent", 22: "agent", 30: "ouv"}


def test_apple_en_dernier_et_cycle():
    apple = Fiche(id="pomme", label="com.apple.x", source="apple", est_apple=True, app_parente="/Applications/A.app")
    tiers = Fiche(id="tiers", label="com.a", source="agent_utilisateur", app_parente="/Applications/A.app")
    procs = [proc(5, "/Applications/A.app/Contents/MacOS/A"), proc(6, "/x", ppid=7), proc(7, "/y", ppid=6)]
    assert rattacher(procs, [apple, tiers], {}) == {5: "tiers"}  # et la boucle 6 ↔ 7 ne bloque pas
