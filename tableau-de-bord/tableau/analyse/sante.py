"""La santé d'un module : sa pastille, sa phrase en français simple, et les problèmes à signaler (§4.1).

🟢 tout va bien · 🟡 quelque chose à regarder · 🔴 il ne fait plus son travail · ⚪ pas installé, éteint ou en pause.

Les problèmes portent leur message de notification (calme, avec quoi faire) et leur message de résolution. Un état
qu'on ne sait pas lire (launchd muet) donne 🟡 « état inconnu », jamais une alerte.
"""

from __future__ import annotations

from typing import Any

from tableau import textes
from tableau.analyse.attentes import Verdict
from tableau.analyse.credits import projeter
from tableau.config import Reglages
from tableau.db import Base
from tableau.module import DefModule, EtatModule, Observation, Pastille, Probleme
from tableau.planif import debut_du_jour, temps_eveille
from tableau.sondes import tailles


def _conseil(defn: DefModule) -> str:
    return f" Tape « {defn.aide} » pour voir pourquoi." if defn.aide else " Le détail est dans le tableau de bord."


def relances(base: Base, module: str, depuis: float) -> int:
    return int(base.valeur("SELECT COUNT(*) FROM relances WHERE module = ? AND ts >= ?", (module, depuis), 0))


def cpu_moyen(base: Base, module: str, depuis: float) -> tuple[float | None, int]:
    r = base.ligne("SELECT AVG(cpu), COUNT(cpu) FROM echantillons WHERE module = ? AND ts >= ?", (module, depuis))
    if r is None or not r[1]:
        return None, 0
    return float(r[0]), int(r[1])


def _tourne(defn: DefModule, obs: Observation) -> bool | None:
    """Le module tourne-t-il ? None : on ne sait pas."""
    if obs.n8n is not None:
        return obs.n8n.get("etat") == "running"
    if obs.superviseur is not None and "statut" in obs.superviseur:
        if obs.superviseur.get("superviseur_en_marche") is False:
            return False
        if obs.processus is not None:
            return True
        statut = obs.superviseur.get("statut")
        return None if statut is None else False
    if defn.labels:
        principal = next((e for e in obs.launchd if e.label == defn.labels[0]), None)
        if principal is None:
            return None if "launchd" in obs.inconnus else False
        return bool(principal.charge and principal.pid)
    return None


def problemes(
    defn: DefModule,
    obs: Observation,
    verdicts: list[Verdict],
    base: Base,
    reglages: Reglages,
    maintenant: float,
    integrite: dict[str, Any] | None = None,
) -> list[Probleme]:
    s = reglages["seuils"]
    nom = defn.nom
    conseil = _conseil(defn)
    p: list[Probleme] = []

    def ajouter(genre: str, gravite: str, message: str, resolution: str, phrase: str, **autres: Any) -> None:
        p.append(Probleme(defn.id, genre, gravite, message, resolution, phrase=phrase, **autres))

    tourne = _tourne(defn, obs)
    # Plantages en boucle (vus par launchd ou dans le journal du superviseur).
    fenetre = int(s["boucle_fenetre_min"]) * 60
    recentes = relances(base, defn.id, maintenant - fenetre)
    if recentes >= int(s["boucle_relances"]):
        cpu = obs.processus.cpu_pct if obs.processus and obs.processus.cpu_pct else 0.0
        aujourdhui = textes.pluriel(relances(base, defn.id, debut_du_jour(maintenant)), "fois", "fois")
        ajouter(
            "boucle",
            "grave",
            f"🔴 {nom} s'est arrêté {recentes} fois en {fenetre // 60} min.{conseil}",
            f"✅ {nom} tourne de nouveau sans s'arrêter.",
            f"{nom} s'est arrêté {aujourdhui} aujourd'hui",
            nuit_permise=recentes >= 2 * int(s["boucle_relances"]) or cpu >= 25,
        )
    elif defn.doit_tourner and tourne is False:
        if obs.n8n is not None:
            etat_n8n = obs.n8n.get("etat")
            raison = "Docker est éteint" if not obs.n8n.get("docker") else f"son conteneur est « {etat_n8n} »"
            ajouter(
                "n8n",
                "grave",
                f"🔴 n8n ne répond plus : {raison}.{conseil}",
                "✅ n8n répond de nouveau.",
                f"n8n ne répond plus ({raison})",
            )
        else:
            sup_arrete = (obs.superviseur or {}).get("superviseur_en_marche") is False
            pourquoi = " (le superviseur de l'assistant ne tourne pas)" if sup_arrete else ""
            ajouter(
                "arrete",
                "grave",
                f"🔴 {nom} est arrêté alors qu'il devrait tourner{pourquoi}.{conseil}",
                f"✅ {nom} tourne de nouveau.",
                f"Arrêté alors qu'il devrait tourner{pourquoi}",
            )
    elif obs.n8n is not None and tourne and not obs.n8n.get("repond"):
        ajouter(
            "n8n",
            "grave",
            f"🔴 n8n tourne mais ne répond pas ({obs.n8n.get('healthz')}).",
            "✅ n8n répond de nouveau.",
            "Tourne, mais ne répond pas",
        )
    # Figé : il tourne, mais son battement ne bouge plus (en temps éveillé).
    if tourne and obs.battement_ts and obs.battement_periode_s and not any(x.genre in ("boucle", "arrete") for x in p):
        age = temps_eveille(base, obs.battement_ts, maintenant)
        seuil = max(180.0, float(s["battement_facteur"]) * obs.battement_periode_s)
        if age > seuil:
            ajouter(
                "fige",
                "grave",
                f"🔴 {nom} semble figé : aucun signe de vie depuis {textes.duree(age)}.{conseil}",
                f"✅ {nom} donne de nouveau signe de vie.",
                f"Figé : aucun signe de vie depuis {textes.duree(age)}",
            )
    # Un agent périodique dont le dernier passage a échoué.
    principal = obs.launchd[0] if obs.launchd else None
    if not defn.doit_tourner and principal and principal.dernier_code not in (None, 0) and not principal.pid:
        code = principal.dernier_code
        ajouter(
            "echec",
            "attention",
            f"🟡 {nom} a échoué à son dernier passage (code {code}).",
            f"✅ {nom} a refait un passage sans erreur.",
            f"Dernier passage en échec (code {code})",
        )
    # Attentes manquées (sauf si le module est arrêté, figé ou en boucle : c'en est la conséquence, et l'alerte de
    # l'arrêt dit déjà tout ; le détail du module continue de les montrer).
    en_panne = any(x.genre in ("boucle", "arrete", "fige", "n8n") for x in p)
    for v in [] if en_panne else verdicts:
        if v.statut != "manquee":
            continue
        a = v.attente
        if a.genre == "quotidienne" and a.heure:
            pourquoi = f"attendu vers {textes.heure_texte(a.heure)}"
        else:
            pourquoi = v.detail
        ajouter(
            "attente",
            "attention",
            f"🟡 {nom} : « {a.libelle} » n'a pas eu lieu ({pourquoi}).{conseil}",
            f"✅ {nom} : « {a.libelle} » a de nouveau eu lieu.",
            f"« {a.libelle} » : {v.detail}",
            sous_cle=a.id,
        )
    # Files bloquées.
    for f in obs.files:
        seuil_min = f.seuil_min or int(s["file_bloquee_min"])
        if f.n > 0 and f.plus_vieux_s > seuil_min * 60:
            verbe = "attendent" if f.n > 1 else "attend"
            attente = f"{textes.pluriel(f.n, 'document')} {verbe} depuis {textes.duree(f.plus_vieux_s)}"
            ajouter(
                "file",
                "attention",
                f"🟡 {nom} : {attente} dans « {f.nom} ».{conseil}",
                f"✅ {nom} : la file « {f.nom} » s'est vidée.",
                f"{attente} dans « {f.nom} »",
                sous_cle=f.nom,
            )
    # Pic d'erreurs, sauf pendant une boucle de plantages et dans l'heure qui suit : chaque plantage écrit son erreur,
    # ces erreurs-là sont celles de la boucle (déjà annoncée, et sa fin aussi).
    boucle_dans_l_heure = relances(base, defn.id, maintenant - 3600) >= int(s["boucle_relances"])
    if obs.logs is not None and not boucle_dans_l_heure and not any(x.genre == "boucle" for x in p):
        moyenne = float(obs.technique.get("moyenne_erreurs_horaire_7j") or 0.0)
        e1h = obs.logs.erreurs_1h
        if e1h >= int(s["pic_erreurs_min_par_heure"]) and e1h >= float(s["pic_erreurs_facteur"]) * moyenne:
            habitude = f" (d'habitude {moyenne:.1f} par heure)".replace(".", ",") if moyenne >= 0.1 else ""
            ajouter(
                "pic_erreurs",
                "attention",
                f"🟡 {nom} écrit beaucoup d'erreurs : {e1h} dans la dernière heure{habitude}.{conseil}",
                f"✅ {nom} est revenu à la normale côté erreurs.",
                f"{e1h} erreurs dans la dernière heure{habitude}",
            )
    # Budget de crédits.
    if obs.credits is not None and obs.credits.mois_usd is not None and obs.credits.plafond_usd:
        pct = obs.credits.mois_usd / obs.credits.plafond_usd * 100
        montant = f"{textes.dollars(obs.credits.mois_usd)} sur {textes.dollars(obs.credits.plafond_usd)}"
        if pct >= float(s["budget_depasse_pct"]):
            ajouter(
                "budget100",
                "grave",
                f"🔴 {nom} a dépassé son budget Claude du mois ({montant}).{conseil}",
                f"✅ {nom} est revenu sous son budget Claude.",
                f"Budget du mois dépassé ({montant})",
            )
        elif pct >= float(s["budget_attention_pct"]):
            ajouter(
                "budget80",
                "attention",
                f"🟡 {nom} a utilisé {pct:.0f} % de son budget Claude du mois ({montant}).",
                f"✅ {nom} est revenu sous {s['budget_attention_pct']} % de son budget.",
                f"{pct:.0f} % du budget du mois ({montant})",
            )
    # Données qui gonflent.
    total, croissance = tailles.croissance_semaine(base, defn.id, maintenant)
    if total is not None:
        mo_total = total / (1024 * 1024)
        trop = mo_total > float(s["donnees_max_mo"])
        gonfle = croissance is not None and croissance > float(s["donnees_croissance_pct_semaine"]) and mo_total > 50
        if trop or gonfle:
            detail = f"{textes.mo(mo_total)}" + (f", +{croissance:.0f} % en une semaine" if gonfle else "")
            ajouter(
                "donnees",
                "attention",
                f"🟡 Les données de {nom} pèsent {detail}.",
                f"✅ Les données de {nom} ont retrouvé une taille normale.",
                f"Ses données pèsent {detail}",
            )
    # Processeur très élevé, longtemps.
    duree_min = int(s["cpu_eleve_min"])
    moyen, n = cpu_moyen(base, defn.id, maintenant - duree_min * 60)
    if moyen is not None and n >= max(2, duree_min // 2) and moyen >= float(s["cpu_eleve_pct"]):
        ajouter(
            "cpu",
            "attention",
            f"🟡 {nom} utilise beaucoup le processeur ({moyen:.0f} % en moyenne depuis {duree_min} min).",
            f"✅ {nom} est revenu à un usage normal du processeur.",
            f"Processeur élevé : {moyen:.0f} % depuis {duree_min} min",
        )
    # Intégrité du code.
    if integrite and integrite.get("ecarts"):
        n_fichiers = len(integrite["ecarts"])
        modifies = textes.pluriel(n_fichiers, "fichier modifié", "fichiers modifiés")
        ajouter(
            "integrite",
            "attention",
            f"⚠️ Le code de {nom} a changé : {modifies}. C'était voulu ?",
            f"✅ Le code de {nom} est de nouveau celui de la référence.",
            f"Code changé : {textes.pluriel(n_fichiers, 'fichier', 'fichiers')} à vérifier",
        )
    return p


def evaluer(
    defn: DefModule,
    obs: Observation,
    verdicts: list[Verdict],
    base: Base,
    reglages: Reglages,
    maintenant: float,
    integrite: dict[str, Any] | None = None,
) -> EtatModule:
    etat = EtatModule(id=defn.id, nom=defn.nom, emoji=defn.emoji, pastille=Pastille.VERT, phrase="", maj=maintenant)
    etat.technique = {
        "launchd": [vars(e) for e in obs.launchd],
        "superviseur": obs.superviseur,
        "inconnus": obs.inconnus,
        "n8n": obs.n8n,
        **{k: v for k, v in obs.technique.items() if k != "erreurs"},
        "erreurs_de_lecture": obs.technique.get("erreurs", {}),
        "relances_10min": relances(base, defn.id, maintenant - 600),
    }
    if not obs.installe:
        etat.pastille = Pastille.GRIS
        etat.phrase = "Pas installé" if defn.attendu else "Plus installé (désinstallé ou renommé ?)"
        return etat
    _remplir_mesures(etat, obs, maintenant)
    etat.attentes = [v.en_dict() for v in verdicts]
    etat.integrite = "changé" if integrite and integrite.get("ecarts") else ("référence" if integrite else None)
    prochaines = [v for v in verdicts if v.prochaine and v.attente.genre == "quotidienne" and v.statut != "inactive"]
    if prochaines:
        v = min(prochaines, key=lambda x: x.prochaine or 0)
        etat.prochaine = (
            f"{v.attente.libelle.split(' chaque')[0].split(' vers')[0]} {textes.quand(v.prochaine or 0, maintenant)}"
        )
    if obs.actif is False:
        etat.pastille = Pastille.GRIS
        etat.phrase = f"Éteint : {obs.raison_inactif}" if obs.raison_inactif else "Éteint"
        integ = [x for x in problemes(defn, obs, [], base, reglages, maintenant, integrite) if x.genre == "integrite"]
        etat.problemes = integ
        return etat
    etat.problemes = problemes(defn, obs, verdicts, base, reglages, maintenant, integrite)
    graves = [x for x in etat.problemes if x.gravite == "grave"]
    attention = [x for x in etat.problemes if x.gravite != "grave"]
    if graves:
        etat.pastille = Pastille.ROUGE
        etat.phrase = graves[0].phrase or graves[0].message
    elif attention:
        etat.pastille = Pastille.JAUNE
        etat.phrase = attention[0].phrase or attention[0].message
    elif _tourne(defn, obs) is None and defn.doit_tourner and ("launchd" in obs.inconnus or not obs.launchd):
        etat.pastille = Pastille.JAUNE
        muet = " (launchd ne répond pas)" if "launchd" in obs.inconnus else ""
        etat.phrase = f"État inconnu pour l'instant{muet}"
    else:
        etat.phrase = _phrase_tout_va_bien(obs, maintenant)
    if len(etat.problemes) > 1:
        etat.phrase += f" (et {textes.pluriel(len(etat.problemes) - 1, 'autre chose', 'autres choses')})"
    return etat


def _remplir_mesures(etat: EtatModule, obs: Observation, maintenant: float) -> None:
    if obs.activite is not None:
        etat.derniere_activite = f"{obs.activite[0]} {textes.il_y_a(obs.activite[1], maintenant)}"
        etat.derniere_activite_ts = obs.activite[1]
    elif obs.logs is not None and obs.logs.derniere_ligne_ts:
        etat.derniere_activite = f"dernière ligne de journal {textes.il_y_a(obs.logs.derniere_ligne_ts, maintenant)}"
        etat.derniere_activite_ts = obs.logs.derniere_ligne_ts
    if obs.logs is not None:
        etat.erreurs_24h = obs.logs.erreurs_24h
        if obs.logs.derniere_erreur:
            etat.technique["derniere_erreur"] = obs.logs.derniere_erreur
            etat.technique["derniere_erreur_ts"] = obs.logs.derniere_erreur_ts
    if obs.processus is not None:
        etat.cpu_pct = obs.processus.cpu_pct
        etat.rss_mo = obs.processus.rss_mo
        etat.technique["depuis_s"] = obs.processus.depuis_s
        etat.technique["pids"] = obs.processus.pids
    if obs.credits is not None:
        etat.credits_mois = obs.credits.mois_usd
        etat.plafond_usd = obs.credits.plafond_usd
        if obs.credits.mois_usd is not None:
            etat.projection_usd = projeter(obs.credits.mois_usd, obs.credits.plafond_usd, maintenant).projection_usd
        etat.technique["credits_source"] = obs.credits.source
        etat.technique["credits_detail"] = obs.credits.detail
    etat.files = [
        {"nom": f.nom, "n": f.n, "plus_vieux_s": f.plus_vieux_s, "pas_encore_telecharges": f.pas_encore_telecharges}
        for f in obs.files
    ]
    if obs.tailles is not None:
        etat.technique["tailles"] = {"donnees": obs.tailles[0], "journaux": obs.tailles[1]}


def _phrase_tout_va_bien(obs: Observation, maintenant: float) -> str:
    morceaux = []
    if obs.processus is not None and obs.processus.depuis_s:
        morceaux.append(f"Tourne depuis {textes.duree(obs.processus.depuis_s)}")
    if obs.activite is not None:
        morceaux.append(f"{obs.activite[0]} {textes.il_y_a(obs.activite[1], maintenant)}")
    if not morceaux:
        return "Tout va bien"
    phrase = " · ".join(morceaux)
    return phrase[0].upper() + phrase[1:]
