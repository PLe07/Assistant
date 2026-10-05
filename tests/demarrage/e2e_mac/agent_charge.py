"""L'agent de charge du test de bout en bout (§9.5), lancé par launchd sous nice :
environ 25 % d'un cœur (25 ms de calcul, 75 ms de pause), un `caffeinate -i -t 240` en processus fils, et un arrêt
tout seul au bout de 4 minutes au plus. Il note son PID et celui de caffeinate pour le nettoyage."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

DUREE_MAX_S = 240


def main() -> None:
    trace = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    cafe = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-t", str(DUREE_MAX_S)])
    if trace:
        with trace.open("a", encoding="utf-8") as f:  # une relance (restaurer) s'ajoute, n'efface pas
            f.write(f"{os.getpid()} {cafe.pid}\n")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # bootout : on passe par le finally
    fin = time.monotonic() + DUREE_MAX_S
    try:
        while time.monotonic() < fin:
            debut = time.perf_counter()
            while time.perf_counter() - debut < 0.025:
                pass
            time.sleep(0.075)
    finally:
        cafe.terminate()
        try:
            cafe.wait(5)
        except subprocess.TimeoutExpired:
            cafe.kill()


if __name__ == "__main__":
    main()
