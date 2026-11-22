"""
tests/test_catalogo_r2mod_blocco.py
===================================
Blocco del server (#115, r2mod): a tempo (MOD-093) e comando di stato (MOD-097). Database vero.
"""

from datetime import datetime, timedelta, timezone

import discord
import pytest

from core import lockdown_logic as logica
from core import lockdown_service as servizio
from core.repositories.lockdown_repo import lockdown_repo
from tests.test_lockdown import GUILD_ID, PROPRIETARIO, _comando, _server, _tre_canali, cog, db  # noqa: F401


# MOD-093
async def test_il_blocco_a_tempo_ha_una_fine_e_non_supera_un_giorno():
    server = _server(list(_tre_canali()))
    await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova", durata_minuti=30)
    stato = await lockdown_repo.get_stato(GUILD_ID)
    assert timedelta(minutes=29) < stato.finisce_il - datetime.now(timezone.utc) <= timedelta(minutes=30)
    await servizio.togli(server)
    await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova", durata_minuti=99999)
    stato = await lockdown_repo.get_stato(GUILD_ID)
    assert stato.finisce_il - datetime.now(timezone.utc) <= timedelta(minutes=logica.MAX_SBLOCCO_MINUTI)
    await servizio.togli(server)


# MOD-093
async def test_il_blocco_senza_durata_non_ha_fine():
    server = _server(list(_tre_canali()))
    await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova")
    assert (await lockdown_repo.get_stato(GUILD_ID)).finisce_il is None
    await servizio.togli(server)


# MOD-097
async def test_il_comando_stato_dice_se_il_server_e_bloccato_e_chiede_il_permesso(cog):
    server = _server(list(_tre_canali()))
    i = _comando(server)
    await cog.blocco_stato.callback(cog, i)
    assert "non e' bloccato" in i.response.send_message.await_args.args[0]
    await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova", durata_minuti=10)
    i = _comando(server)
    await cog.blocco_stato.callback(cog, i)
    testo = i.response.send_message.await_args.args[0]
    assert "blocco totale" in testo and "Si riapre" in testo
    senza = _comando(server, gestisce=False)
    await cog.blocco_stato.callback(cog, senza)
    assert "Si riapre" not in senza.response.send_message.await_args.args[0]
    await servizio.togli(server)
