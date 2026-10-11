"""
tests/test_log_config.py
========================
/log crea-canali, /log crea-forum, /log ignora, /log canale su un forum e
/log stato (NF-01, NF-02). I comandi si provano sul gruppo vero.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.logging.log_config as modulo
import core.channel_router as router
from cogs.logging.basic_logs import BasicLogsCog
from core.message_log_logic import Ignorati, IGNORATI_MAX_PER_SERVER, scegli_bersaglio
from core.repositories.log_ignora_repo import LogIgnoraRepository
from core.repositories.output_channel_repo import OutputChannelRepository
from tests.support.discord_fakes import (
    fake_forum_channel,
    fake_guild,
    fake_interaction,
    fake_text_channel,
)


class _Db:
    def __init__(self, generale=None):
        self.scritti = {}
        self.generale = generale

    async def set_guild_setting(self, guild_id, key, value, changed_by=None):
        self.scritti[(guild_id, key)] = value

    async def get_guild_setting(self, guild_id, key):
        return self.scritti.get((guild_id, key), self.generale)


@pytest.fixture
def ambiente(clean_db, monkeypatch):
    repo = OutputChannelRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(router, "output_channel_repo", repo)
    monkeypatch.setattr(modulo, "log_ignora_repo", LogIgnoraRepository(pool_provider=lambda: clean_db))
    finto = _Db()
    monkeypatch.setattr(modulo, "db", finto)
    import cogs.logging.basic_logs as basic

    monkeypatch.setattr(basic, "db", finto)
    return repo, finto


def _server():
    server = fake_guild(guild_id=600)
    server.channels = []
    server.me.guild_permissions = discord.Permissions(manage_channels=True)
    n = iter(range(1000, 2000))

    def canale(*a, **k):
        c = fake_text_channel(next(n), name=a[0] if a else "x")
        return c

    server.create_category = AsyncMock(return_value=MagicMock(id=999))
    server.create_text_channel = AsyncMock(side_effect=canale)
    server.create_forum = AsyncMock(return_value=fake_forum_channel(4000))
    return server


async def test_crea_canali_un_canale_per_tipo_e_il_router_li_conosce(ambiente):
    repo, db = ambiente
    cog = modulo.LogConfigCog(bot=None)
    server = _server()
    ix = fake_interaction(guild=server)
    await cog.crea_canali.callback(cog, ix)
    assert server.create_text_channel.await_count == 4
    scelte = {r.tipo: r.channel_id for r in await repo.elenco(600)}
    assert set(scelte) == set(router.TIPI_LOG) and len(set(scelte.values())) == 4
    assert db.scritti[(600, router.SETTING_LOG_CHANNEL)] == scelte[router.TIPO_EVENTI]
    overwrites = server.create_category.await_args.kwargs["overwrites"]
    assert overwrites[server.default_role].view_channel is False


async def test_crea_canali_senza_permesso_o_senza_posto_non_crea_niente(ambiente):
    cog = modulo.LogConfigCog(bot=None)
    server = _server()
    server.me.guild_permissions = discord.Permissions.none()
    ix = fake_interaction(guild=server)
    await cog.crea_canali.callback(cog, ix)
    server.create_category.assert_not_awaited()

    pieno = _server()
    pieno.channels = [object()] * 497
    ix = fake_interaction(guild=pieno)
    await cog.crea_canali.callback(cog, ix)
    pieno.create_category.assert_not_awaited()
    assert "500" in ix.response.send_message.call_args.args[0]


async def test_crea_canali_discord_rifiuta_a_meta_dice_cosa_ha_creato(ambiente):
    cog = modulo.LogConfigCog(bot=None)
    server = _server()
    risposta = MagicMock(status=403, reason="x")
    base = server.create_text_channel.side_effect
    chiamate = {"n": 0}

    async def a_scatti(*a, **k):
        chiamate["n"] += 1
        if chiamate["n"] == 3:
            raise discord.Forbidden(risposta, "no")
        return base(*a, **k)

    server.create_text_channel = AsyncMock(side_effect=a_scatti)
    ix = fake_interaction(guild=server)
    await cog.crea_canali.callback(cog, ix)
    assert "Creati" in ix.followup.send.call_args.args[0]


async def test_crea_forum_tutti_i_tipi_puntano_al_forum(ambiente):
    repo, db = ambiente
    cog = modulo.LogConfigCog(bot=None)
    server = _server()
    ix = fake_interaction(guild=server)
    await cog.crea_forum.callback(cog, ix)
    assert {r.channel_id for r in await repo.elenco(600)} == {4000}
    assert db.scritti[(600, router.SETTING_LOG_CHANNEL)] == 4000


async def test_crea_forum_senza_community_risponde_chiaro(ambiente):
    cog = modulo.LogConfigCog(bot=None)
    server = _server()
    server.create_forum = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=400, reason="x"), "no"))
    ix = fake_interaction(guild=server)
    await cog.crea_forum.callback(cog, ix)
    assert "Community" in ix.followup.send.call_args.args[0]


async def test_ignora_aggiungi_elenco_e_togli(ambiente):
    cog = modulo.LogConfigCog(bot=None)
    ix = fake_interaction(guild=fake_guild(guild_id=600))
    canale = fake_text_channel(55)
    await cog.ignora.callback(cog, ix, "aggiungi", canale, None, None)
    await cog.ignora.callback(cog, ix, "aggiungi", None, None, "!")
    ig = await modulo.log_ignora_repo.carica(600)
    assert ig == Ignorati(canali=frozenset({55}), utenti=frozenset(), prefissi=("!",))
    await cog.ignora.callback(cog, ix, "elenco", None, None, None)
    assert "<#55>" in ix.response.send_message.call_args.args[0]
    await cog.ignora.callback(cog, ix, "rimuovi", canale, None, None)
    assert (await modulo.log_ignora_repo.carica(600)).canali == frozenset()


async def test_ignora_vuole_una_sola_scelta(ambiente):
    cog = modulo.LogConfigCog(bot=None)
    ix = fake_interaction(guild=fake_guild(guild_id=600))
    await cog.ignora.callback(cog, ix, "aggiungi", fake_text_channel(1), None, "!")
    assert "una sola" in ix.response.send_message.call_args.args[0]
    assert scegli_bersaglio(None, None, None) != ("canale", "1")


async def test_ignora_ha_un_tetto_per_server(ambiente):
    repo = modulo.log_ignora_repo
    for n in range(IGNORATI_MAX_PER_SERVER):
        assert await repo.aggiungi(600, "canale", str(n), IGNORATI_MAX_PER_SERVER)
    assert not await repo.aggiungi(600, "canale", "nuovo", IGNORATI_MAX_PER_SERVER)
    assert await repo.aggiungi(600, "canale", "3", IGNORATI_MAX_PER_SERVER)  # già presente


async def test_log_canale_con_un_forum_lo_imposta_per_il_tipo(ambiente):
    repo, db = ambiente
    cog = BasicLogsCog(bot=None)
    server = fake_guild(guild_id=600)
    ix = fake_interaction(guild=server)
    forum = fake_forum_channel(4001)
    await cog.logs_setup.callback(cog, ix, forum, "messaggi")
    assert (await repo.ottieni(600, "messaggi")).channel_id == 4001
    assert (600, router.SETTING_LOG_CHANNEL) not in db.scritti  # solo il tipo scelto


async def test_log_canale_senza_permessi_sul_canale_rifiuta(ambiente):
    cog = BasicLogsCog(bot=None)
    ix = fake_interaction(guild=fake_guild(guild_id=600))
    canale = fake_text_channel(7)
    canale.permissions_for.return_value = discord.Permissions.none()
    await cog.logs_setup.callback(cog, ix, canale, "eventi")
    assert "permessi" in ix.response.send_message.call_args.args[0]


async def test_log_stato_mostra_ogni_tipo_e_la_riserva(ambiente):
    repo, db = ambiente
    db.scritti[(600, router.SETTING_LOG_CHANNEL)] = 10
    await repo.imposta(600, "messaggi", 11)
    await repo.segna_avvisato(600, "messaggi", 11)
    server = fake_guild(guild_id=600)
    server.get_channel.side_effect = {10: fake_text_channel(10), 11: fake_text_channel(11)}.get
    cog = BasicLogsCog(bot=None)
    ix = fake_interaction(guild=server)
    await cog.logs_status.callback(cog, ix)
    testo = ix.response.send_message.call_args.args[0]
    assert testo.count("\n") == 3
    assert "riserva" in testo and "non riesco a scrivere" in testo
