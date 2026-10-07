"""n8n, dans Docker : `docker ps`, `docker inspect`, `docker stats --no-stream`, et `GET /healthz` en local.

- Docker absent de la machine et aucun conteneur n8n connu : « pas installé ».
- Docker éteint alors que n8n a déjà été vu : n8n est injoignable (c'est bien ce que tu verrais).
"""

from __future__ import annotations

from tableau.adaptateurs.base import Adaptateur, Etape
from tableau.adaptateurs.contexte import Contexte
from tableau.module import DefModule, Observation, StatsProcessus


class N8n(Adaptateur):
    nom = "n8n"

    def etapes(self) -> list[tuple[str, Etape]]:
        return [("docker", self.lire_docker)]

    def est_installe(self, defn: DefModule, ctx: Contexte) -> bool:
        etat = ctx.docker_etat([defn.conteneur or "n8n"])
        if etat.disponible and (defn.conteneur or "n8n") in etat.conteneurs:
            ctx.base.ecrire_meta(f"vu:{defn.id}", str(ctx.maintenant))
            return True
        # Docker éteint : n8n est « installé » s'il a déjà été vu (il est alors injoignable, pas absent).
        return not etat.disponible and ctx.base.lire_meta(f"vu:{defn.id}") is not None

    def lire_docker(self, defn: DefModule, ctx: Contexte, obs: Observation) -> None:
        nom = defn.conteneur or "n8n"
        etat = ctx.docker_etat([nom])
        repond, detail = ctx.healthz(defn.port or 5678)
        obs.n8n = {"docker": etat.disponible, "docker_erreur": etat.erreur, "repond": repond, "healthz": detail}
        c = etat.conteneurs.get(nom)
        if c is None:
            obs.n8n["etat"] = "docker éteint" if not etat.disponible else "absent"
            return
        obs.n8n.update({"etat": c.etat, "sante": c.sante, "relances_docker": c.relances, "image": c.image})
        if c.cpu_pct is not None or c.memoire_mo is not None:
            obs.processus = StatsProcessus(pids=[], cpu_pct=c.cpu_pct, rss_mo=c.memoire_mo or 0.0, depuis_s=None)
        if repond:
            obs.activite = ("n8n a répondu", ctx.maintenant)
