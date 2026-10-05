"""Le coût d'un relevé, avec le vrai « ps » de cette machine, et ce qu'il donne en moyenne sur une journée."""

import resource
import time
import tracemalloc

from modules.demarrage.db import Base
from modules.demarrage.mesure.echantillonneur import Echantillonneur
from modules.demarrage.systeme import Mac

BUDGET_CPU_PCT = 0.3


def cpu_consomme() -> float:
    soi, fils = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return soi.ru_utime + soi.ru_stime + fils.ru_utime + fils.ru_stime


def test_cout_d_un_releve(tmp_path, reglages):
    base = Base(tmp_path / "d.db")
    ech = Echantillonneur(Mac(), base, reglages, lambda: [])
    ech.prendre("mesure")  # premier relevé : référence
    n = 20
    tracemalloc.start()
    debut, horloge = cpu_consomme(), time.perf_counter()
    for _ in range(n):
        assert ech.prendre("croisiere") is not None
    par_releve = (cpu_consomme() - debut) / n
    _, pic = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    base.fermer()
    e = reglages["echantillonnage"]
    session = (e["session_minutes"] * 60 / e["session_pas_s"]) * par_releve
    croisiere = ((86400 - e["session_minutes"] * 60) / e["croisiere_pas_s"]) * par_releve
    moyenne_pct = 100 * (session + croisiere) / 86400
    print(f"\n   relevé : {par_releve * 1000:.1f} ms de processeur, {time.perf_counter() - horloge:.2f} s pour {n} ;"
          f" pic mémoire Python {pic / 1e6:.2f} Mo ; moyenne projetée sur 24 h : {moyenne_pct:.3f} %")  # fmt: skip
    assert par_releve < 0.2
    assert moyenne_pct < BUDGET_CPU_PCT
    assert pic < 10e6
