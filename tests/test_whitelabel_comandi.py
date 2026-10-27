"""
tests/test_whitelabel_comandi.py
================================
Il bot con marchio risponde ai comandi (NF-38, #109): le interazioni del suo client le esegue il principale,
e i comandi si registrano sull'applicazione del marchio solo se l'albero è cambiato.
Client e bot sono oggetti veri (non collegati); Discord è finto solo per la richiesta HTTP.
"""

import asyncio
from unittest.mock import AsyncMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

import core.whitelabel_bot as wl
from core.command_sync import SALTATA, SINCRONIZZATA


class _StatoInMemoria:
    def __init__(self):
        self.valori = {}

    async def leggi(self, scope):
        return self.valori.get(scope)

    async def salva(self, scope, impronta):
        self.valori[scope] = impronta


def _bot_con_comando(eseguiti):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())

    @bot.tree.command(name="prova", description="Un comando di prova")
    async def prova(interaction: discord.Interaction):
        eseguiti.append(interaction)

    return bot


def _interazione_grezza(nome="prova"):
    return {
        "id": "9001", "application_id": "777", "type": 2, "token": "tok", "version": 1,
        "user": {"id": "5", "username": "u", "discriminator": "0", "avatar": None},
        "data": {"id": "42", "name": nome, "type": 1},
        "channel_id": "10", "locale": "it", "app_permissions": "0", "attachment_size_limit": 10485760,
    }


async def test_l_interazione_del_marchio_la_esegue_il_principale():
    eseguiti = []
    bot = _bot_con_comando(eseguiti)
    await bot._async_setup_hook()  # come al login: da qui il bot ha il suo ciclo di eventi
    client = wl._ClientMarchio(500, None, bot, 777)

    client._connection.parsers["INTERACTION_CREATE"](_interazione_grezza())
    for _ in range(20):
        await asyncio.sleep(0)

    assert len(eseguiti) == 1
    assert eseguiti[0].client is bot  # eseguita con i cog e i controlli del principale
    assert eseguiti[0].application_id == 777  # ma risponde con l'identità del marchio
    await client.close()
    await bot.close()


async def test_senza_principale_il_client_non_inoltra_niente():
    client = wl._ClientMarchio(500, None)
    assert client._connection.parsers["INTERACTION_CREATE"].__qualname__.startswith("ConnectionState.")
    await client.close()


async def test_i_comandi_si_registrano_nel_server_del_marchio_una_volta():
    bot = _bot_con_comando([])
    client = wl._ClientMarchio(500, None, bot, 777)
    client.http.bulk_upsert_guild_commands = AsyncMock(return_value=[])
    stato = _StatoInMemoria()

    primo = await wl.sincronizza_comandi_marchio(client, bot, 500, 777, stato)
    secondo = await wl.sincronizza_comandi_marchio(client, bot, 500, 777, stato)

    assert (primo, secondo) == (SINCRONIZZATA, SALTATA)
    client.http.bulk_upsert_guild_commands.assert_awaited_once()
    app_id, guild_id, payload = client.http.bulk_upsert_guild_commands.await_args.args
    assert (app_id, guild_id) == (777, 500) and [c["name"] for c in payload] == ["prova"]
    assert list(stato.valori) == ["marchio:500"]
    await client.close()
    await bot.close()


async def test_un_errore_nella_registrazione_non_ferma_il_marchio(monkeypatch):
    bot = _bot_con_comando([])
    client = wl._ClientMarchio(500, None, bot, 777)
    client.http.bulk_upsert_guild_commands = AsyncMock(side_effect=discord.Forbidden(AsyncMock(status=403, reason="x"), "Missing Access"))
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", object(), raising=False)
    monkeypatch.setattr("core.command_sync.StatoSyncDatabase", lambda pool: _StatoInMemoria())

    await client._registra_comandi()  # non solleva

    client.http.bulk_upsert_guild_commands.assert_awaited_once()
    await client.close()
    await bot.close()


async def test_i_comandi_veri_del_principale_stanno_nel_tetto_del_marchio():
    """Il marchio riceve gli stessi comandi (senza /owner): il tetto di Discord è 100 per applicazione e server."""
    from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed

    creato_qui = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti
        bot.tree.remove_command("owner")  # come fa main.py: non è globale
        comandi = bot.tree.get_commands()
        assert 0 < len(comandi) <= 100
        assert all(isinstance(c.to_dict(bot.tree), dict) for c in comandi)
    finally:
        await close_full_bot(bot)
        if creato_qui:
            from core.database import db

            await db.close()
