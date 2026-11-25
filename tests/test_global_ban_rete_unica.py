"""
tests/test_global_ban_rete_unica.py
===================================
Ban globale e rete di protezione sono una rete sola (blocco A, voce 1): cancelli di affidabilità,
proposta con i tasti Banna/Ignora al server che riceve, ban automatico solo se scelto e con punteggio alto,
niente propagazione durante un raid o un nuke, registro di ogni tentativo.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import discord

import cogs.security.global_ban as modulo
from core import security_raid_state as stato
from core.repositories.global_ban_repo import global_ban_repo
from core.repositories.rete_repo import rete_repo
from tests.test_global_ban_117 import MOTIVO, USER, _bot, _server, ambiente, automatico  # noqa: F401


async def _aderiscono(ambiente, *ids):
    ambiente.update(ids)
    for gid in ids:
        await global_ban_repo.set_direction(gid, send=True, receive=True)


async def test_di_base_arriva_una_proposta_e_non_un_ban(ambiente, clean_db):
    a, b = _server(1), _server(2)
    await _aderiscono(ambiente, 1, 2)  # modo di base: proposta
    assert await modulo.propagate_ban(_bot(a, b), a, USER, MOTIVO, con_prova=True) == [2]
    b.ban.assert_not_awaited()
    riga = await clean_db.fetchrow("SELECT stato, categoria, punteggio FROM rete_ban_proposte WHERE guild_dest = 2")
    assert riga["stato"] == "proposta" and riga["categoria"] == "ban_globale" and riga["punteggio"] >= 55
    b.owner.send.assert_awaited_once()  # avviso con i tasti allo staff
    assert b.owner.send.call_args.kwargs["view"] is not None


async def test_il_ban_automatico_serve_scelta_e_punteggio_alto(ambiente):
    a, b, c = _server(1), _server(2), _server(3)
    await _aderiscono(ambiente, 1, 2, 3)
    await rete_repo.imposta(2, ban_modo="automatico")
    c.member_count = 600
    await modulo.propagate_ban(_bot(a, b, c), a, USER, MOTIVO, con_prova=True)
    b.ban.assert_awaited_once()
    c.ban.assert_not_awaited()  # non ha scelto l'automatico: solo proposta


async def test_punteggio_medio_resta_proposta_anche_se_automatico(ambiente):
    a, b = _server(1), _server(2)
    a.member_count = 60  # piccolo ma ammesso
    a.created_at = discord.utils.utcnow() - timedelta(days=60)
    a.me.joined_at = discord.utils.utcnow() - timedelta(days=10)
    await _aderiscono(ambiente, 1, 2)
    await rete_repo.imposta(2, ban_modo="automatico")
    assert await modulo.propagate_ban(_bot(a, b), a, USER, MOTIVO, con_prova=True) == [2]
    b.ban.assert_not_awaited()


async def test_server_piccolo_o_bot_nuovo_non_propaga_e_lascia_traccia(ambiente, clean_db):
    a, b = _server(1), _server(2)
    a.member_count = 10
    await _aderiscono(ambiente, 1, 2)
    assert await modulo.propagate_ban(_bot(a, b), a, USER, MOTIVO, con_prova=True) == []
    assert await clean_db.fetchval("SELECT esito FROM global_ban_episodi") == "rifiutato:punteggio"


async def test_durante_un_raid_o_un_nuke_non_si_propaga(ambiente):
    a, b = _server(1), _server(2)
    await _aderiscono(ambiente, 1, 2)
    await automatico(2)
    stato.segna_raid(1)
    try:
        assert await modulo.propagate_ban(_bot(a, b), a, USER, MOTIVO, con_prova=True) == []
    finally:
        stato.azzera(1)
    stato.segna_nuke(1)
    try:
        assert await modulo.propagate_ban(_bot(a, b), a, USER, MOTIVO, con_prova=True) == []
    finally:
        stato._ultimo_nuke.delete(1)
    b.ban.assert_not_awaited()


async def test_ban_a_raffica_dello_stesso_server_viene_fermato(ambiente):
    a, b = _server(1), _server(2)
    await _aderiscono(ambiente, 1, 2)
    risultati = [await modulo.propagate_ban(_bot(a, b), a, 5000 + i, MOTIVO, con_prova=True) for i in range(8)]
    assert risultati[0] == [2]
    assert risultati[-1] == []  # oltre il ritmo ammesso


async def test_un_server_bloccato_dal_proprietario_del_bot_non_propaga(ambiente):
    a, b = _server(1), _server(2)
    await _aderiscono(ambiente, 1, 2)
    await rete_repo.blocca(1, 1, "prova")
    assert await modulo.propagate_ban(_bot(a, b), a, USER, MOTIVO, con_prova=True) == []


async def test_la_conferma_di_un_altro_server_alza_il_punteggio(ambiente, clean_db):
    a, c = _server(1), _server(3)
    await global_ban_repo.registra_episodio(3, USER, 70, [], "propagato")
    punteggio_con, _, _ = await modulo.calcola_affidabilita(a, USER, MOTIVO, False)
    punteggio_senza, _, _ = await modulo.calcola_affidabilita(a, USER + 1, MOTIVO, False)
    assert punteggio_con > punteggio_senza


async def test_la_revoca_chiude_le_proposte_aperte(ambiente, clean_db):
    a, b = _server(1), _server(2)
    await _aderiscono(ambiente, 1, 2)
    bot = _bot(a, b)
    await modulo.propagate_ban(bot, a, USER, MOTIVO, con_prova=True)
    await modulo.revoca_ban_propagati(bot, 1, USER)
    assert await clean_db.fetchval("SELECT stato FROM rete_ban_proposte WHERE guild_dest = 2") == "annullato"


async def test_tetto_di_proposte_al_giorno_per_il_server_che_riceve(ambiente):
    a, b = _server(1), _server(2)
    await _aderiscono(ambiente, 1, 2)
    modulo.TETTO_PROPOSTE_AL_GIORNO, vecchio = 1, modulo.TETTO_PROPOSTE_AL_GIORNO
    try:
        assert await modulo.propagate_ban(_bot(a, b), a, 7001, MOTIVO, con_prova=True) == [2]
        assert await modulo.propagate_ban(_bot(a, b), a, 7002, MOTIVO, con_prova=True) == []
    finally:
        modulo.TETTO_PROPOSTE_AL_GIORNO = vecchio


def test_la_propagazione_ha_un_tetto_di_parallelismo():
    assert modulo.TETTO_PROPAGAZIONI_INSIEME >= 1
    assert modulo._coda_propagazioni._value == modulo.TETTO_PROPAGAZIONI_INSIEME
