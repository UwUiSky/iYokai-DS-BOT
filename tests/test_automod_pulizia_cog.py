"""
tests/test_automod_pulizia_cog.py
=================================
Comando `/admin-automod pulizia`, ciclo dei giri e canale cancellato (AMD-073, 074).
"""

from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest
from discord import app_commands

import cogs.automod.pulizia as modulo
import cogs.moderation._shared as condiviso
from core import automod_pulizia_service as servizio
from core.automod_pulizia import EsitoGiro
from core.database import Database
from core.repositories.automod_pulizie_repo import automod_pulizie_repo as repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_text_channel

G = 666


@pytest.fixture
def cog(clean_db, monkeypatch):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    db_finto.get_guild_setting.return_value = None
    monkeypatch.setattr(condiviso, "db", db_finto)
    monkeypatch.setattr(modulo, "db", db_finto)
    monkeypatch.setattr(repo, "_pool_provider", lambda: clean_db)
    bot = MagicMock()
    return modulo.PuliziaAutomodCog(bot)


def inter():
    i = fake_interaction(guild=fake_guild(guild_id=G))
    i.guild.me.guild_permissions = discord.Permissions.all()
    return i


def canale(cid=111):
    c = fake_text_channel(cid)
    c.guild = fake_guild(guild_id=G)
    c.permissions_for = MagicMock(return_value=discord.Permissions.all())
    return c


def scelta(v):
    return app_commands.Choice(name=v, value=v)


async def test_il_comando_crea_mostra_e_toglie(cog):
    c = canale()
    i = inter()
    await cog.pulizia.callback(cog, i, c, "6h", scelta("link"), None, None, False)
    assert (await repo.leggi(G, 111)).ogni_secondi == 21600
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    i2 = inter()
    await cog.pulizia.callback(cog, i2, c, None, None, None, None, False)  # solo lo stato
    assert "6h" in i2.response.send_message.await_args.args[0]
    i3 = inter()
    await cog.pulizia.callback(cog, i3, c, None, None, None, None, True)
    assert await repo.leggi(G, 111) is None


async def test_intervallo_storto_o_mancante_non_scrive(cog):
    c = canale()
    for ogni in ("5m", None):
        i = inter()
        await cog.pulizia.callback(cog, i, c, ogni, None, None, None, False)
        assert await repo.conta(G) == 0
        i.response.send_message.assert_awaited_once()


async def test_giro_pulisce_le_dovute_e_spegne_dopo_i_403(cog, clean_db, monkeypatch):
    await servizio.imposta(G, 111, ogni="1h")
    await servizio.imposta(G, 222, ogni="1h")
    await clean_db.execute("UPDATE automod_pulizie SET ultimo_giro = now() - interval '2 hours'")
    canali = {111: canale(111), 222: canale(222)}
    cog.bot.get_channel = lambda cid: canali.get(cid)
    fermo = EsitoGiro()
    for _ in range(3):
        fermo.vieta()
    esiti = {111: EsitoGiro(), 222: fermo}
    monkeypatch.setattr(modulo, "pulisci", AsyncMock(side_effect=lambda c, p, *a: esiti[p.canale_id]))
    avvisa = AsyncMock()
    monkeypatch.setattr(cog, "_avvisa", avvisa)
    assert await cog.giro() == 2
    assert (await repo.leggi(G, 111)).attiva is True
    assert (await repo.leggi(G, 222)).attiva is False
    avvisa.assert_awaited_once()
    assert await cog.giro() == 0  # il giro è già segnato


async def test_modulo_spento_o_canale_sconosciuto_non_si_pulisce(cog, clean_db, monkeypatch):
    await servizio.imposta(G, 111, ogni="1h")
    await clean_db.execute("UPDATE automod_pulizie SET ultimo_giro = now() - interval '2 hours'")
    cog.bot.get_channel = lambda cid: None
    pulisci = AsyncMock()
    monkeypatch.setattr(modulo, "pulisci", pulisci)
    assert await cog.giro() == 0
    pulisci.assert_not_awaited()


async def test_canale_cancellato_toglie_la_riga(cog):
    await servizio.imposta(G, 111, ogni="1h")
    await cog.on_guild_channel_delete(canale(111))
    assert await repo.conta(G) == 0


async def test_errore_su_un_canale_non_fa_perdere_il_giro_degli_altri(cog, clean_db, monkeypatch):
    """I giri sono già segnati: un errore su un canale non deve saltare gli altri del ciclo."""
    await servizio.imposta(G, 111, ogni="1h")
    await servizio.imposta(G, 222, ogni="1h")
    await clean_db.execute("UPDATE automod_pulizie SET ultimo_giro = now() - interval '2 hours'")
    canali = {111: canale(111), 222: canale(222)}
    cog.bot.get_channel = lambda cid: canali.get(cid)

    async def pulisci(c, p, *a):
        if p.canale_id == 111:
            raise discord.HTTPException(MagicMock(status=500), "errore")
        return EsitoGiro()

    finto = AsyncMock(side_effect=pulisci)
    monkeypatch.setattr(modulo, "pulisci", finto)
    assert await cog.giro() == 1
    assert {c.args[1].canale_id for c in finto.await_args_list} == {111, 222}
