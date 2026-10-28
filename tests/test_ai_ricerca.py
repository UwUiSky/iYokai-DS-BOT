"""
tests/test_ai_ricerca.py
========================
Assistente che cerca i comandi (§25.12, §25.25, §25.28–§25.31, §25.34, §25.101): strada, stato,
comandi vicini, scoperta, piano. Logica pura più un controllo sull'albero vero.
"""

import json

from core import command_search_logic as ricerca
from core import ai_ricerca_logic as r
from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed


def cmd(percorso, descr="x", moduli=()):
    return ricerca.ComandoInfo(percorso=percorso, descrizione=descr, gruppo=percorso.split()[0], opzioni=(), moduli=tuple(moduli))


COMANDI = [
    cmd("modban ban", "Banna permanentemente un membro."),
    cmd("mod timeout", "Mette in timeout un membro."),
    cmd("fun gioca", "Gioca"),
    cmd("level balance", "Mostra i tuoi coin."),
    cmd("clan crea", "Crea un clan"),
]


def test_scoperta_prima_di_tutto():
    for frase in ("cosa posso fare qui?", "What can I do here", "che c'è da fare"):
        assert r.scegli_strada(frase, COMANDI).strada is r.Strada.SCOPERTA


def test_faq_esatta_ignora_parole_vuote():
    voci = [("Regole del server", "Sii gentile.")]
    d = r.scegli_strada("le regole del server?", COMANDI, voci)
    assert d.strada is r.Strada.FAQ and d.testo == "Sii gentile."
    assert r.scegli_strada("regole del server e premi", COMANDI, voci).strada is not r.Strada.FAQ


def test_ricerca_sicura_solo_se_un_comando_e_evidente():
    assert r.scegli_strada("/modban ban", COMANDI).strada is r.Strada.RICERCA
    lunga = "voglio sapere come fare per fermare chi scrive troppo veloce nel canale generale"
    assert r.scegli_strada(lunga, COMANDI).strada is r.Strada.AI
    assert r.scegli_strada("qualcosa di strano", COMANDI).strada is r.Strada.AI


def test_stato_in_ordine_di_gravita():
    S = r.stato_comando
    assert S(r.ContestoComando()).codice == "disponibile"
    assert S(r.ContestoComando(configurato=True)).codice == "configurato"
    assert S(r.ContestoComando(moduli_spenti=("tickets",))).modulo_da_attivare == "tickets"
    assert S(r.ContestoComando(moduli_spenti=("a",), premium_bloccato=True)).codice == "premium"
    assert S(r.ContestoComando(premium_bloccato=True, moduli_mancanti=("z",))).codice == "manca_modulo"
    assert S(r.ContestoComando(permesso=False, moduli_mancanti=("z",))).codice == "permesso"


def test_moduli_da_proporre_senza_doppioni_e_al_massimo_3():
    stati = [r.StatoComando("spento", "", m) for m in ("a", "a", "b", "c", "d")] + [r.StatoComando("disponibile", "")]
    assert r.moduli_da_proporre(stati) == ["a", "b", "c"]


def test_vicini_esistenti_e_non_citati():
    esistenti = {c.percorso: c for c in COMANDI + [cmd("modban tempban"), cmd("modban softban")]}
    v = r.vicini_di("modban ban", esistenti, gia_citati=["modban softban"])
    assert [c.percorso for c, _ in v] == ["modban tempban", "mod timeout"]
    assert r.vicini_di("non esiste", esistenti) == []


def test_scoperta_elenco_anche_senza_ai():
    t = r.elenco_scoperta(COMANDI, eventi=["Boss: Oni"])
    assert "Boss: Oni" in t and "/fun gioca" in t and "/modban" not in t
    assert "-cerca-comando" in r.elenco_scoperta([])


def test_piano_solo_comandi_veri_senza_doppioni_max_5():
    passi = [{"comando": "/mod timeout", "valori": "10 minuti <@1>"}] * 2 + [{"comando": "inventato"}]
    passi += [{"comando": c.percorso, "modulo": "leveling"} for c in COMANDI]
    out = r.leggi_piano("ecco " + json.dumps({"passi": passi}), COMANDI)
    assert [p.comando.percorso for p in out] == ["mod timeout", "modban ban", "fun gioca", "level balance", "clan crea"]
    assert "<" not in out[0].valori and "@" not in out[0].valori
    assert r.leggi_piano("niente json", COMANDI) == []
    assert r.moduli_del_piano(out, ["leveling", "altro"]) == ["leveling"]


def test_richiesta_composta():
    assert r.richiesta_composta("chi entra riceve il ruolo Membro e poi un messaggio privato di benvenuto")
    assert not r.richiesta_composta("come banno qualcuno")


def test_elenco_per_ai_segna_i_moduli_spenti():
    t = r.elenco_per_ai(COMANDI[:2], {"mod timeout": "moderation_actions"})
    assert "(modulo moderation_actions spento" in t.splitlines()[1] and "spento" not in t.splitlines()[0]


async def test_comandi_vicini_puntano_a_comandi_veri():
    creato = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti
        from tests.test_command_tree_invariants import _radici

        veri = {c.percorso for c in ricerca.raccogli_comandi(_radici(bot))}
        for chiave, vicini in r.COMANDI_VICINI.items():
            assert chiave in veri, chiave
            for v, frase in vicini:
                assert v in veri and frase, (chiave, v)
    finally:
        await close_full_bot(bot)
        if creato:
            from core.database import db

            await db.close()
