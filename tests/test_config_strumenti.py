"""
tests/test_config_strumenti.py
==============================
CFG-019, CFG-020, CFG-021, CFG-046 (#122): pulizia della configurazione, sincronizzazione dei permessi,
nickname del bot e `/utility info`.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

from cogs.utility import config_strumenti as modulo
from core import config_cleanup_logic as pulizia
from core.command_permissions import (
    STATO_DA_RIPROVARE,
    STATO_OK,
    STATO_SENZA_AUTORIZZAZIONE,
    STATO_TOKEN_NON_VALIDO,
    EsitoPermessi,
)
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role

pytestmark = pytest.mark.asyncio


def test_tipo_della_chiave():
    assert pulizia.tipo_della_chiave("log_channel_id") == pulizia.TIPO_CANALE
    assert pulizia.tipo_della_chiave("ticket_category_id") == pulizia.TIPO_CANALE
    assert pulizia.tipo_della_chiave("ticket_support_role_ids") == pulizia.TIPO_RUOLO
    assert pulizia.tipo_della_chiave("policy_canali_no") == pulizia.TIPO_CANALE
    assert pulizia.tipo_della_chiave("policy_ignora_utenti") is None  # utenti: non si controllano
    assert pulizia.tipo_della_chiave("music_max_volume") is None


def test_trova_orfani_toglie_solo_quelli_morti():
    settings = {
        "log_channel_id": 1,
        "mod_log_channel_id": 2,  # morto
        "ticket_support_role_ids": [10, 11, 12],  # 11 e 12 morti
        "verify_extra_role_ids": [20, 21],  # tutti morti: la chiave sparisce
        "music_max_volume": 5,
        "policy_ignora_utenti": [9999],
    }
    voci = pulizia.trova_orfani(settings, canale_esiste=lambda i: i == 1, ruolo_esiste=lambda i: i == 10)
    per_chiave = {v.chiave: v for v in voci}
    assert set(per_chiave) == {"mod_log_channel_id", "ticket_support_role_ids", "verify_extra_role_ids"}
    assert per_chiave["ticket_support_role_ids"].nuovo == [10] and per_chiave["ticket_support_role_ids"].morti == [11, 12]
    assert per_chiave["verify_extra_role_ids"].nuovo is None
    assert per_chiave["mod_log_channel_id"].nuovo is None


@pytest.fixture
async def db_pronto(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    await database_module.db.ensure_guild_exists(800)
    return database_module.db


async def test_pulisci_configurazione_anteprima_e_applica(db_pronto):
    db = db_pronto
    await db.set_guild_setting(800, "log_channel_id", 111, changed_by=1)
    await db.set_guild_setting(800, "mod_log_channel_id", 222, changed_by=1)
    await db.set_guild_setting(800, "ticket_support_role_ids", [5, 6], changed_by=1)
    guild = fake_guild(800)
    guild.roles = [fake_role(role_id=5)]
    guild.get_role = lambda i: guild.roles[0] if i == 5 else None
    guild.get_channel_or_thread = lambda i: object() if i == 111 else None
    guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "no"))

    anteprima = await pulizia.pulisci_configurazione(guild, applica=False, changed_by=9)
    assert anteprima.totale == 2 and not anteprima.applicata
    assert await db.get_guild_setting(800, "mod_log_channel_id") == 222  # niente è cambiato

    fatta = await pulizia.pulisci_configurazione(guild, applica=True, changed_by=9)
    assert fatta.applicata
    assert await db.get_guild_setting(800, "mod_log_channel_id") is None
    assert await db.get_guild_setting(800, "ticket_support_role_ids") == [5]
    assert await db.get_guild_setting(800, "log_channel_id") == 111
    storico = await db.get_config_history_filtrato(800, changed_by=9)
    assert {v.key_name for v in storico} == {"mod_log_channel_id", "ticket_support_role_ids"}  # annullabile


async def test_thread_archiviato_o_errore_di_discord_non_si_toglie(db_pronto):
    """Un thread archiviato non è in memoria: si chiede a Discord. Solo «non trovato» lo toglie."""
    db = db_pronto
    await db.set_guild_setting(800, "log_channel_id", 111, changed_by=1)  # thread archiviato, esiste
    await db.set_guild_setting(800, "mod_log_channel_id", 222, changed_by=1)  # cancellato
    await db.set_guild_setting(800, "welcome_channel_id", 333, changed_by=1)  # Discord non risponde
    guild = fake_guild(800)
    guild.roles = [fake_role(role_id=5)]
    guild.get_channel_or_thread = lambda i: None

    async def fetch(i):
        if i == 111:
            return object()
        if i == 222:
            raise discord.NotFound(MagicMock(status=404), "no")
        raise discord.HTTPException(MagicMock(status=500), "giù")

    guild.fetch_channel = fetch
    await pulizia.pulisci_configurazione(guild, applica=True, changed_by=9)
    assert await db.get_guild_setting(800, "log_channel_id") == 111
    assert await db.get_guild_setting(800, "mod_log_channel_id") is None
    assert await db.get_guild_setting(800, "welcome_channel_id") == 333


async def test_server_non_caricato_non_si_tocca(db_pronto):
    db = db_pronto
    await db.set_guild_setting(800, "log_channel_id", 111, changed_by=1)
    guild = fake_guild(800)
    guild.roles = []  # non ancora caricato
    esito = await pulizia.pulisci_configurazione(guild, applica=True, changed_by=9)
    assert esito.voci == [] and await db.get_guild_setting(800, "log_channel_id") == 111
    assert (await pulizia.pulisci_configurazione(None, applica=True, changed_by=9)).voci == []


def test_riassumi_esiti():
    ok = EsitoPermessi(STATO_OK)
    assert modulo.riassumi_esiti({})[0] == "cfg_sync_nessun_ruolo"
    assert modulo.riassumi_esiti({"admin_role_id": None})[0] == "cfg_sync_non_autorizzato"
    assert modulo.riassumi_esiti({"admin_role_id": EsitoPermessi(STATO_SENZA_AUTORIZZAZIONE)})[0] == "cfg_sync_non_autorizzato"
    assert modulo.riassumi_esiti({"admin_role_id": EsitoPermessi(STATO_TOKEN_NON_VALIDO)})[0] == "cfg_sync_token_non_valido"
    chiave, valori = modulo.riassumi_esiti({"admin_role_id": EsitoPermessi(STATO_DA_RIPROVARE, errori={"log": 500})})
    assert chiave == "cfg_sync_parziale" and "log" in valori["gruppi"]
    assert modulo.riassumi_esiti({"admin_role_id": ok}) == ("cfg_sync_ok", {"tipi": "admin_role_id"})


def _cog():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    return modulo.ConfigStrumentiCog(bot)


async def test_sincronizza_ha_un_tempo_di_attesa(db_pronto, monkeypatch):
    cog = _cog()
    chiamate = AsyncMock(return_value={"admin_role_id": EsitoPermessi(STATO_OK)})
    monkeypatch.setattr(modulo, "risincronizza_server", chiamate)
    i = fake_interaction(guild=fake_guild(800))
    await cog.sincronizza.callback(cog, i)
    assert chiamate.await_count == 1
    i2 = fake_interaction(guild=fake_guild(800))
    await cog.sincronizza.callback(cog, i2)
    assert chiamate.await_count == 1  # la seconda è respinta
    assert "riprova" in i2.response.send_message.call_args.args[0].lower()


async def test_sincronizza_fallita_non_fa_scattare_l_attesa(db_pronto, monkeypatch):
    cog = _cog()
    chiamate = AsyncMock(return_value={"admin_role_id": EsitoPermessi(STATO_DA_RIPROVARE, errori={"log": 500})})
    monkeypatch.setattr(modulo, "risincronizza_server", chiamate)
    for _ in range(2):
        await cog.sincronizza.callback(cog, fake_interaction(guild=fake_guild(800)))
    assert chiamate.await_count == 2  # chi ha sbagliato riprova subito


async def test_sincronizza_due_insieme_ne_parte_una(db_pronto, monkeypatch):
    import asyncio

    cog = _cog()
    via = asyncio.Event()

    async def lenta(bot, guild):
        await via.wait()
        return {"admin_role_id": EsitoPermessi(STATO_OK)}

    chiamate = AsyncMock(side_effect=lenta)
    monkeypatch.setattr(modulo, "risincronizza_server", chiamate)
    prima = asyncio.create_task(cog.sincronizza.callback(cog, fake_interaction(guild=fake_guild(800))))
    await asyncio.sleep(0)
    seconda = fake_interaction(guild=fake_guild(800))
    await cog.sincronizza.callback(cog, seconda)
    assert "in corso" in seconda.response.send_message.call_args.args[0]
    via.set()
    await prima
    assert chiamate.await_count == 1


async def test_nickname_bot_errore_di_discord_e_detto(db_pronto):
    cog = _cog()
    guild = fake_guild(800)
    guild.me = MagicMock()
    guild.me.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500), "giù"))
    i = fake_interaction(guild=guild)
    await cog.nickname_bot.callback(cog, i, "X")
    assert "rifiutato" in i.response.send_message.call_args.args[0]


async def test_nickname_bot_cambia_azzera_e_dice_se_manca_il_permesso(db_pronto):
    cog = _cog()
    guild = fake_guild(800)
    guild.me = MagicMock()
    guild.me.edit = AsyncMock()
    i = fake_interaction(guild=guild)
    await cog.nickname_bot.callback(cog, i, " Yokai ")
    guild.me.edit.assert_awaited_once()
    assert guild.me.edit.await_args.kwargs["nick"] == "Yokai"
    i = fake_interaction(guild=guild)
    await cog.nickname_bot.callback(cog, i, None)
    assert guild.me.edit.await_args.kwargs["nick"] is None
    guild.me.edit = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "no"))
    i = fake_interaction(guild=guild)
    await cog.nickname_bot.callback(cog, i, "X")
    assert "permesso" in i.response.send_message.call_args.args[0]


async def test_info_mostra_versione_e_invito(db_pronto, monkeypatch):
    cog = _cog()
    monkeypatch.setattr(type(cog.bot), "application_id", property(lambda self: 4242), raising=False)
    import dataclasses

    monkeypatch.setattr(modulo, "config", dataclasses.replace(modulo.config, SUPPORT_SERVER_URL="https://discord.gg/xyz"))
    i = fake_interaction(guild=fake_guild(800))
    i.locale = discord.Locale.italian
    await cog.info.callback(cog, i)
    embed = i.response.send_message.call_args.kwargs["embed"]
    testo = " ".join(f.value for f in embed.fields)
    assert "client_id=4242" in testo and "discord.gg/xyz" in testo
    assert any("Versione" in f.name for f in embed.fields)
