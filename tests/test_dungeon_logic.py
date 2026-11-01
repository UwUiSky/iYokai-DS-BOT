"""
tests/test_dungeon_logic.py
===========================
Dungeon di gruppo (§25.53–§25.55, §25.99): probabilità secondo classi e livelli, voti, storie dell'AI.
"""

import json
import random

from core import dungeon_logic as d


def test_la_classe_giusta_e_il_livello_aiutano():
    solo_forza = [("forza", 5), ("forza", 5)]
    misto = [("forza", 5), ("astuzia", 5), ("magia", 5)]
    assert d.probabilita_successo("forza", 3, solo_forza) > d.probabilita_successo("forza", 3, misto)
    assert d.probabilita_successo("magia", 3, solo_forza) < d.probabilita_successo("forza", 3, solo_forza)
    assert d.probabilita_successo("forza", 3, [("forza", 60)]) > d.probabilita_successo("forza", 3, [("forza", 1)])
    assert d.probabilita_successo("forza", 5, []) >= 0.1 and d.probabilita_successo("forza", 1, [("forza", 99)]) <= 0.95


def test_voto_a_maggioranza_e_pareggio_deciso_dalla_sorte():
    assert d.scelta_vincente({1: 0, 2: 1, 3: 1}, 3, random.Random(0)) == 1
    esiti = {d.scelta_vincente({1: 0, 2: 1}, 3, random.Random(s)) for s in range(30)}
    assert esiti == {0, 1}
    assert d.scelta_vincente({}, 2, random.Random(1)) in (0, 1)
    assert d.scelta_vincente({1: 9}, 2, random.Random(1)) in (0, 1)  # voto fuori intervallo ignorato


def test_classi_per_tema():
    assert [p for _, p in d.classi_del_tema("fantasy")] == ["forza", "astuzia", "magia"]
    assert d.prova_della_classe("fantasy", "Mago") == "magia" and d.prova_della_classe("fantasy", "Samurai") is None
    assert d.classi_del_tema("boh") == d.CLASSI["yokai"]


STORIA_AI = {
    "titolo": "La torre <@1>",
    "inizio": "A",
    "nodi": [
        {"id": "A", "testo": "Una torre. https://x.example", "scelte": [
            {"testo": "Sali", "prova": "forza", "difficolta": 9, "successo": "B", "fallimento": "C"},
            {"testo": "Entra", "prova": "boh", "successo": "B", "fallimento": "manca"},
            {"testo": "Aspetta", "prova": "magia", "successo": "B", "fallimento": "C"},
            {"testo": "Quarta scelta di troppo", "successo": "B", "fallimento": "C"}]},
        {"id": "B", "testo": "Vittoria!", "finale": True, "esito": "vittoria"},
        {"id": "C", "testo": "Sconfitta.", "finale": True, "esito": "sconfitta"},
        {"id": "B", "testo": "doppione"},
        {"id": "D", "testo": "Una sola scelta", "scelte": [{"testo": "Unica", "successo": "B", "fallimento": "C"}]},
    ],
}


def test_storia_dell_ai_resa_sicura():
    s = d.leggi_storia("Ecco: " + json.dumps(STORIA_AI))
    assert s.inizio == "a" and s.titolo == "La torre 1"
    a = s.nodo("a")
    assert len(a.scelte) == d.MAX_SCELTE and a.scelte[0].difficolta == 5 and a.scelte[1].prova in d.PROVE
    assert "http" not in a.testo
    assert s.nodo("b").esito == "vittoria" and s.nodo("b").testo == "Vittoria!"
    assert s.nodo("d").finale  # una stanza con una sola scelta chiude la storia
    assert s.rami_mancanti() == ["manca"]


def test_storie_non_valide_si_scartano():
    assert d.leggi_storia("niente") is None
    senza_finale = {"inizio": "a", "nodi": [{"id": "a", "testo": "x", "scelte": [
        {"testo": "1", "successo": "a", "fallimento": "a"}, {"testo": "2", "successo": "a", "fallimento": "a"}]}]}
    assert d.leggi_storia(json.dumps(senza_finale)) is None
    assert d.leggi_storia(json.dumps({"inizio": "zzz", "nodi": [{"id": "a", "testo": "x", "finale": True}]})) is None
    lunga = {"inizio": "n0", "nodi": [{"id": f"n{i}", "testo": "t", "finale": True} for i in range(40)]}
    assert len(d.leggi_storia(json.dumps(lunga)).nodi) == d.MAX_NODI


def test_storia_pronta_completa_e_senza_rami_mancanti():
    for tema in list(d.CLASSI) + [None]:
        s = d.storia_pronta(tema)
        assert s.rami_mancanti() == [] and s.nodo(s.inizio)
        assert any(n.esito == "vittoria" for n in s.nodi) and any(n.esito == "sconfitta" for n in s.nodi)
        assert all(len(sc.testo) <= d.MAX_TESTO_SCELTA for n in s.nodi for sc in n.scelte)


def test_nodo_continuato_dall_ai_e_finale_locale():
    n = d.leggi_nodo({"testo": "Nuova stanza", "scelte": [{"testo": "a"}, {"testo": "b"}]}, id_forzato="a_0s")
    assert n.id == "a_0s" and len(n.scelte) == 2 and n.scelte[0].successo == "a_0s_0s"
    assert d.nodo_finale_locale("x", "vittoria").esito == "vittoria"
