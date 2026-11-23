"""
tests/test_azioni_programmate_utl111.py
=======================================
UTL-111 (D121): azioni sicure programmate, al massimo 5 per server, eseguite una volta sola con i permessi di chi le ha
messe riletti in quel momento. Database vero, Discord finto.
"""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from core import azioni_programmate as ap
from core import azioni_sicure as az
from core.database import db
from tests.test_azioni_sicure_utl024_111 import G, _scena


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    yield


def _bot(guild):
    bot = MagicMock()
    bot.get_guild.return_value = guild
    return bot


def _togli_ruolo():
    return az.da_dict({"tipo": "togli_ruolo", "ruolo_id": 10, "utente_id": 6})


async def test_al_massimo_5_per_server_e_attesa_da_1_minuto_a_30_giorni():
    for _ in range(az.MAX_PROGRAMMATE):
        await ap.programma(G, 5, _togli_ruolo(), timedelta(hours=1))
    with pytest.raises(ap.TroppeProgrammate):
        await ap.programma(G, 5, _togli_ruolo(), timedelta(hours=1))
    await ap.programma(G + 1, 5, _togli_ruolo(), timedelta(hours=1))  # un altro server ha il suo tetto
    for attesa in (timedelta(seconds=10), timedelta(days=31)):
        with pytest.raises(ap.AttesaNonValida):
            await ap.programma(G + 2, 5, _togli_ruolo(), attesa)


async def test_un_tipo_dei_tag_che_non_e_programmabile_non_si_salva():
    with pytest.raises(az.AzioneNonValida):
        await ap.programma(G, 5, az.da_dict({"tipo": "reazione", "emoji": "👍"}), timedelta(hours=1))


async def test_alla_scadenza_si_fa_una_volta_sola_anche_se_lo_scheduler_riprova():
    guild, canale, esec, utente = _scena()
    nuovo = await ap.programma(G, 5, _togli_ruolo(), timedelta(hours=1))
    assert await ap.alla_scadenza(_bot(guild), G, 5, {"id": nuovo}) is None
    assert await ap.alla_scadenza(_bot(guild), G, 5, {"id": nuovo}) is None  # secondo tentativo: niente
    utente.remove_roles.assert_awaited_once()
    assert await ap.elenco(G) == []


async def test_chi_l_ha_messa_ha_perso_il_permesso_non_si_fa_e_si_dice():
    guild, canale, esec, utente = _scena()
    nuovo = await ap.programma(G, 5, _togli_ruolo(), timedelta(hours=1))
    import discord

    esec.guild_permissions = discord.Permissions.none()
    assert await ap.alla_scadenza(_bot(guild), G, 5, {"id": nuovo}) is not None
    utente.remove_roles.assert_not_awaited()


async def test_togliere_dall_elenco_ferma_l_esecuzione():
    guild, canale, esec, utente = _scena()
    nuovo = await ap.programma(G, 5, _togli_ruolo(), timedelta(hours=1))
    assert await ap.togli(G, nuovo) is True
    assert await ap.togli(G, nuovo) is False
    await ap.alla_scadenza(_bot(guild), G, 5, {"id": nuovo})
    utente.remove_roles.assert_not_awaited()
    assert await ap.togli(G + 1, nuovo) is False


async def test_se_chi_l_ha_messa_e_uscita_dal_server_non_si_fa():
    guild, canale, esec, utente = _scena()
    nuovo = await ap.programma(G, 99, _togli_ruolo(), timedelta(hours=1))  # 99 non è nel server
    assert await ap.alla_scadenza(_bot(guild), G, 99, {"id": nuovo}) is not None
    utente.remove_roles.assert_not_awaited()


async def test_server_non_raggiungibile_lascia_la_riga_per_il_riprovo():
    nuovo = await ap.programma(G, 5, _togli_ruolo(), timedelta(hours=1))
    bot = MagicMock()
    bot.get_guild.return_value = None
    assert await ap.alla_scadenza(bot, G, 5, {"id": nuovo}) == "server non raggiungibile"
    assert len(await ap.elenco(G)) == 1
