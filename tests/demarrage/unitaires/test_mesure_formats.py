"""ps, top et pmset : les analyseurs de sortie."""

from modules.demarrage.mesure import energie, veille
from modules.demarrage.mesure.echantillonneur import analyser_ps, duree_ps, temps_ps
from tests.demarrage.conftest import fixture


def test_ps():
    procs = {p.pid: p for p in analyser_ps(fixture("ps.txt"))}
    assert len(procs) == 16  # les deux lignes cassées sont ignorées
    keystone = procs[1234]
    assert (keystone.ppid, keystone.uid, keystone.cpu_pct, keystone.rss_ko) == (1, 501, 12.5, 52300)
    assert keystone.age_s == 2 * 3600 + 15 * 60 + 1 and abs(keystone.cpu_s - 252.33) < 1e-6
    assert procs[2215].comm.endswith("Spotify Helper (Renderer)")  # espaces et parenthèses gardés
    assert procs[6001].comm == "/Applications/Éditeur Café.app/Contents/MacOS/Éditeur Café"
    assert procs[4512].age_s == 86400 + 4 * 3600 and procs[1].cpu_s == 12 * 60 + 34.56
    assert procs[9999].comm == "(sh)"


def test_durees_ps():
    assert duree_ps("00:05") == 5 and duree_ps("45:10") == 2710 and duree_ps("02:15:01") == 8101
    assert duree_ps("03-02:11:45") == 3 * 86400 + 7905 and duree_ps("abc") is None
    assert temps_ps("0:04.97") == 4.97 and temps_ps("123:45.67") == 123 * 60 + 45.67
    assert temps_ps("1:02:03.50") == 3723.5 and temps_ps("2-01:00:00") == 2 * 86400 + 3600
    assert temps_ps("12.5") == 12.5
    assert temps_ps("x:1") is None and temps_ps("a-1:00") is None and temps_ps("1:2:3:4") is None


def test_ps_valeurs_bizarres():
    texte = (
        "  1  0  0  0,5  100  00:01  0:00.10 /a\n"
        "  2  1  x  0.0  100  00:01  0:00.10 /b\n"
        "  3  1  0  0.0  100  ??  0:00.10 /c\n"
    )
    procs = analyser_ps(texte)
    assert [p.pid for p in procs] == [1] and procs[0].cpu_pct == 0.5


def test_top():
    e = energie.analyser(fixture("top.txt"))
    assert e[1234].puissance == 18.2 and e[1234].cpu == 14.1  # le 2e relevé, pas le 1er
    assert e[2215].commande == "Spotify Helper (" and e[2215].memoire_ko == 176 * 1024
    assert e[2210].memoire_ko == 402 * 1024 and e[8888].memoire_ko == 2928
    assert e[4512].memoire_ko == int(1.2 * 1024 * 1024)
    assert energie.analyser("pas de top ici") == {}
    assert energie.analyser("PID    COMMAND          %CPU MEM    POWER\n1 x a 2M 3\n2 y 1.0 ??? 3\n3 z\n") == {}


def test_pmset():
    assertions = veille.analyser(fixture("pmset_assertions.txt"))
    par_pid = {a.pid: a for a in assertions}
    assert set(par_pid) == {391, 4321, 5555, 1234, 6001}
    cafe = par_pid[4321]
    assert cafe.type == "PreventUserIdleSystemSleep" and cafe.au_nom_de == 4320 and cafe.empeche_la_veille
    assert not par_pid[5555].empeche_la_veille  # l'écran seulement
    assert par_pid[6001].empeche_la_veille and par_pid[6001].processus == "Éditeur Café"
    assert veille.pids_qui_empechent(assertions) == {4321, 4320, 1234, 6001}
    assert veille.analyser("rien\n") == []
