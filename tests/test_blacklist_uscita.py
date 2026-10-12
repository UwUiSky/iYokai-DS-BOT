"""
M 13.2 (REVIEW §12, 17.5): un server in blacklist fa uscire TUTTI i bot, non
solo quello principale: anche i cinque worker musicali.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core.blacklist_exit import esci_da_server_in_blacklist, esci_dettaglio


def _bot_con_server(guild_id: int | None, *, errore: Exception | None = None):
    bot = MagicMock()
    if guild_id is None:
        bot.get_guild.return_value = None
        return bot, None
    server = MagicMock()
    server.id = guild_id
    server.leave = AsyncMock(side_effect=errore)
    bot.get_guild.side_effect = lambda gid: server if gid == guild_id else None
    return bot, server


def _flotta(*worker):
    flotta = MagicMock()
    flotta.worker_bots = list(worker)
    return flotta


@pytest.mark.asyncio
async def test_escono_il_principale_e_tutti_i_worker_presenti():
    principale, s0 = _bot_con_server(77)
    w1, s1 = _bot_con_server(77)
    w2, s2 = _bot_con_server(None)  # questo worker nel server non c'è
    w3, s3 = _bot_con_server(77)
    principale.music_fleet = _flotta(w1, w2, w3)

    usciti = await esci_da_server_in_blacklist(principale, 77)

    assert usciti == 3
    for server in (s0, s1, s3):
        server.leave.assert_awaited_once()


@pytest.mark.asyncio
async def test_un_worker_che_fallisce_non_ferma_gli_altri():
    principale, s0 = _bot_con_server(77)
    rotto, _ = _bot_con_server(
        77, errore=discord.HTTPException(MagicMock(status=500, reason="x"), "boom")
    )
    sano, s2 = _bot_con_server(77)
    principale.music_fleet = _flotta(rotto, sano)

    usciti = await esci_da_server_in_blacklist(principale, 77)

    assert usciti == 2
    s2.leave.assert_awaited_once()


@pytest.mark.asyncio
async def test_senza_flotta_esce_solo_il_principale():
    principale, s0 = _bot_con_server(77)
    principale.music_fleet = None

    assert await esci_da_server_in_blacklist(principale, 77) == 1
    s0.leave.assert_awaited_once()


@pytest.mark.asyncio
async def test_il_comando_blacklist_server_add_fa_uscire_tutti(monkeypatch):
    import cogs.utility.owner_premium as modulo

    chiamate = []

    risultato = [(4, 0)]

    async def finto(bot, guild_id):
        chiamate.append(guild_id)
        return risultato[0]

    monkeypatch.setattr(modulo, "esci_dettaglio", finto)
    repo = MagicMock()
    repo.add_guild = AsyncMock()
    import core.repositories.blacklist_repo as blacklist_modulo

    monkeypatch.setattr(blacklist_modulo, "blacklist_repo", repo)

    cog = modulo.OwnerPremiumCog(MagicMock())
    interazione = MagicMock()
    interazione.user.id = 1
    interazione.response.send_message = AsyncMock()

    await cog.blacklist_guild_add.callback(cog, interazione, "77", "spam")

    assert chiamate == [77]
    testo = interazione.response.send_message.await_args.args[0]
    assert "4" in testo

    # se i leave() falliscono il messaggio non finge che sia andato tutto bene
    risultato[0] = (0, 2)
    await cog.blacklist_guild_add.callback(cog, interazione, "77", "spam")
    testo = interazione.response.send_message.await_args.args[0]
    assert "ATTENZIONE" in testo and "2 bot non sono riusciti" in testo


@pytest.mark.asyncio
async def test_il_dettaglio_conta_anche_i_falliti():
    principale, _ = _bot_con_server(
        77, errore=discord.HTTPException(MagicMock(status=500, reason="x"), "boom")
    )
    w, _ = _bot_con_server(77, errore=discord.HTTPException(MagicMock(status=500, reason="x"), "boom"))
    principale.music_fleet = _flotta(w)

    assert await esci_dettaglio(principale, 77) == (0, 2)
