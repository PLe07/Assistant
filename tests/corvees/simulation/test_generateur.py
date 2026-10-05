"""Le simulateur lui-même : déterministe, réaliste, et ses pièges sont bien là (sinon les tests ne prouvent rien)."""

import collections

from tests.corvees.simulation.generateur import CORVEES_A, SECRETS, generer


def test_meme_graine_meme_monde():
    a, b = generer(3, jours=7), generer(3, jours=7)
    assert [(e.ts, e.token) for e in a.evenements] == [(e.ts, e.token) for e in b.evenements]
    assert [e.token for e in generer(4, jours=7).evenements] != [e.token for e in a.evenements]


def test_beaucoup_de_bruit_et_des_evenements_tries():
    m = generer(1)
    assert 300 * 28 < len(m.evenements) < 1000 * 28
    assert all(x.ts <= y.ts for x, y in zip(m.evenements, m.evenements[1:], strict=False))
    sortes = collections.Counter(e.kind for e in m.evenements)
    assert {"app", "url", "fen", "clip", "cmd", "fcreate", "fmove", "fren", "fconv", "inactif"} <= set(sortes)
    assert len({e.token for e in m.evenements}) > 1000


def test_les_corvees_plantees_sont_dans_les_evenements():
    m = generer(1)
    tokens = " ".join(e.token for e in m.evenements)
    assert len([c for c in m.corvees if not c.refusee]) == len(CORVEES_A) == 10
    for c in m.corvees:
        assert sum(1 for motif in c.motifs if __import__("re").search(motif, tokens)) >= c.k, c.nom


def test_les_pieges_sont_poses():
    m = generer(1)
    brut = " ".join(e.token + str(e.attrs) for e in m.evenements)
    assert "1Password" in brut and "boursorama" in brut and "app:Spotify" in brut
    assert sum(1 for s in SECRETS if s in brut or s.replace(" ", "") in brut) >= 5  # avant la vie privée : bien là
    assert any(c.refusee for c in m.corvees)


def test_retrouvee_par_un_candidat():
    c = next(c for c in generer(1, jours=2).corvees if c.nom.startswith("routine du matin"))
    assert c.retrouvee_par({"tokens": ["url:mail.google.com/mail", "url:calendar.google.com/calendar"]})
    assert not c.retrouvee_par({"tokens": ["url:mail.google.com/mail", "app:Safari"]})


def test_densite_pour_les_mesures_de_performance():
    assert len(generer(1, jours=30, densite=30).evenements) >= 200_000
