"""
tests/test_catalogo_r2mod_registro_chat.py
==========================================
Gli ultimi messaggi del canale salvati con un caso (MOD-051): spento di base, 100 messaggi, solo scheda degli allegati,
letto con `/mod-casi caso chat`, tolto con il caso. Database vero.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation._shared import MODULE_ACTIONS, MODULE_CASE_SYSTEM
from cogs.moderation.actions import ModerationActionsCog
from cogs.moderation.case_system import ModerationCaseSystemCog
from core import moderation_registro_chat as rc
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_interaction, fake_member, fake_text_channel
from tests.test_moderation_ordine_azione import ID_BERSAGLIO, ID_SERVER, Scena


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID_SERVER, MODULE_ACTIONS, True)
    await db.set_module_active_for_guild(ID_SERVER, MODULE_CASE_SYSTEM, True)
    yield
    database_module.db._modules_cache.clear()


def _msg(testo, n=0):
    m = MagicMock()
    m.author.display_name, m.author.id = "Anna", 1
    m.content, m.created_at, m.embeds, m.stickers = testo, datetime(2026, 11, 1, 10, n, tzinfo=timezone.utc), [], []
    m.attachments = [MagicMock(filename="../foto.png", content_type="image/png", size=2048, url="https://cdn.x/y")]
    return m


def _scena(messaggi):
    s = Scena()
    canale = MagicMock(spec=discord.TextChannel)
    canale.id, canale.name = 7001, "generale"
    canale.permissions_for = lambda who: discord.Permissions(view_channel=True, read_message_history=True)
    chiamate = {}

    def storia(limit):
        chiamate["limit"] = limit

        async def gen():
            for m in messaggi:
                yield m

        return gen()

    canale.history = storia
    s.interazione.channel = canale
    return s, chiamate


# MOD-051
async def test_spento_di_base_non_salva_niente():
    s, _ = _scena([_msg("ciao")])
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, s.interazione, s.bersaglio, "Spam ripetuto")
    assert await db.pool.fetchval("SELECT count(*) FROM moderation_chat_log") == 0


# MOD-051
@pytest.mark.parametrize("azione", ["warn", "kick", "ban", "timeout"])
async def test_acceso_ogni_azione_salva_il_registro_col_caso_senza_indirizzi(azione):
    await db.set_guild_setting(ID_SERVER, rc.SETTING_REGISTRO_CHAT, True)
    s, chiamate = _scena([_msg("secondo", 2), _msg("primo", 1)][::-1][::-1])
    cog = ModerationActionsCog(bot=None)
    argomenti = {"warn": ("Spam ripetuto",), "kick": ("Spam ripetuto",), "ban": ("Spam ripetuto",), "timeout": ("Spam ripetuto", "1h")}[azione]
    await getattr(cog, azione).callback(cog, s.interazione, s.bersaglio, *argomenti)
    assert chiamate["limit"] == 100
    caso = (await moderation_repo.list_cases_for_user(ID_SERVER, ID_BERSAGLIO))[0]
    contenuto, n, canale = await rc.leggi(ID_SERVER, caso.case_number)
    testo = contenuto.decode()
    assert n == 2 and canale == 7001 and "[allegato: foto.png, image/png, 2 KB]" in testo
    assert "http" not in testo and "../" not in testo


# MOD-051
async def test_senza_permesso_di_leggere_o_fuori_da_un_canale_di_testo_non_salva_e_il_caso_resta():
    await db.set_guild_setting(ID_SERVER, rc.SETTING_REGISTRO_CHAT, True)
    s, _ = _scena([_msg("x")])
    s.interazione.channel.permissions_for = lambda who: discord.Permissions(view_channel=True)
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, s.interazione, s.bersaglio, "Spam ripetuto")
    assert len(await moderation_repo.list_cases_for_user(ID_SERVER, ID_BERSAGLIO)) == 1
    assert await db.pool.fetchval("SELECT count(*) FROM moderation_chat_log") == 0
    s2, _ = _scena([_msg("x")])
    s2.interazione.channel = MagicMock(spec=discord.VoiceChannel)
    assert await rc.salva(s2.interazione, 99) is False


# MOD-051
async def test_un_errore_del_registro_non_rompe_il_comando():
    await db.set_guild_setting(ID_SERVER, rc.SETTING_REGISTRO_CHAT, True)
    s, _ = _scena([])
    s.interazione.channel.history = MagicMock(side_effect=RuntimeError("giù"))
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, s.interazione, s.bersaglio, "Spam ripetuto")
    assert len(await moderation_repo.list_cases_for_user(ID_SERVER, ID_BERSAGLIO)) == 1


# MOD-051
async def test_il_comando_chat_manda_il_file_in_privato_e_il_caso_eliminato_porta_via_il_registro():
    await db.set_guild_setting(ID_SERVER, rc.SETTING_REGISTRO_CHAT, True)
    s, _ = _scena([_msg("ciao")])
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, s.interazione, s.bersaglio, "Spam ripetuto")
    numero = (await moderation_repo.list_cases_for_user(ID_SERVER, ID_BERSAGLIO))[0].case_number
    cs = ModerationCaseSystemCog(bot=None)
    i = fake_interaction(guild=s.server, user=s.moderatore)
    await cs.case_chat.callback(cs, i, numero)
    kw = i.response.send_message.await_args.kwargs
    assert kw["ephemeral"] is True and kw["file"].filename == f"chat_caso_{numero}.txt" and kw["allowed_mentions"].users is False
    i2 = fake_interaction(guild=s.server, user=s.moderatore)
    await cs.case_chat.callback(cs, i2, numero + 50)
    assert "file" not in i2.response.send_message.await_args.kwargs
    assert await moderation_repo.delete_case(ID_SERVER, numero) is True
    assert await rc.leggi(ID_SERVER, numero) is None
