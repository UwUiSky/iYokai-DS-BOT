"""
tests/test_catalogo_r2mod_esporta_chat.py
=========================================
`/mod-canali esporta-chat` (UTL-204, D74): file di testo, allegati solo come scheda, permessi riletti. Database vero.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation._shared import MODULE_CLEAR
from cogs.moderation.clear import ModerationClearCog
from core import moderation_esporta_chat as esporta
from core.database import db
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

QUANDO = datetime(2026, 11, 1, 10, 30, tzinfo=timezone.utc)


def _msg(testo="ciao", nome="Anna", uid=1, allegati=(), embeds=0):
    m = MagicMock()
    m.author.display_name, m.author.id = nome, uid
    m.content, m.created_at, m.embeds, m.stickers = testo, QUANDO, [object()] * embeds, []
    m.attachments = [MagicMock(filename=f, content_type=t, size=s, url="https://cdn.discordapp.com/x") for f, t, s in allegati]
    return m


# UTL-204
def test_l_allegato_e_solo_una_scheda_senza_indirizzo():
    riga = esporta.riga_messaggio(_msg("guarda", allegati=[("../../etc/pass‮wd.png", "image/png; x=1", 5000)]))
    assert "[allegato: pass" in riga and "image/png" in riga and "4 KB" in riga
    assert "http" not in riga and "cdn" not in riga and "‮" not in riga and "etc/" not in riga


# UTL-204
def test_le_righe_a_capo_restano_nel_messaggio_e_il_file_ha_il_tetto():
    assert "\n    seconda" in esporta.riga_messaggio(_msg("prima\nseconda"))
    grandi = [_msg("x" * 100_000) for _ in range(200)]
    contenuto, scritti, tagliato = esporta.costruisci_file(grandi, "gen")
    assert tagliato and len(contenuto) <= esporta.MAX_BYTE and scritti < 200


# UTL-204
def test_il_file_ha_al_massimo_mille_messaggi():
    _, scritti, tagliato = esporta.costruisci_file([_msg() for _ in range(1200)], "gen")
    assert scritti == 1000 and not tagliato


@pytest.fixture
async def amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(100, MODULE_CLEAR, True)
    server = fake_guild(100, owner_id=1)
    canale = fake_text_channel(7, "generale")
    canale.permissions_for = lambda who: discord.Permissions(view_channel=True, read_message_history=True, manage_messages=True) if who is not server.me else discord.Permissions(view_channel=True, read_message_history=True)

    async def storia(limit):
        for m in [_msg("due"), _msg("uno")][:limit]:
            yield m

    canale.history = lambda limit: storia(limit)
    canale.mention = "<#7>"
    yield server, canale
    database_module.db._modules_cache.clear()


# UTL-204
async def test_il_comando_manda_il_file_solo_a_chi_comanda_senza_menzioni(amb, monkeypatch):
    server, canale = amb
    monkeypatch.setattr("cogs.moderation.clear.post_to_mod_log", AsyncMock())
    i = fake_interaction(guild=server, user=fake_member(10), channel=canale)
    cog = ModerationClearCog(bot=MagicMock())
    await cog.esporta_chat.callback(cog, i, 5, canale)
    inviato = i.followup.send.await_args
    assert inviato.kwargs["ephemeral"] is True and inviato.kwargs["file"].filename == "chat-7.txt"
    assert isinstance(inviato.kwargs["allowed_mentions"], discord.AllowedMentions)
    righe = inviato.kwargs["file"].fp.read().decode().splitlines()
    assert righe[1].endswith("uno") and righe[2].endswith("due")  # dal più vecchio


# UTL-204
async def test_senza_il_permesso_adesso_non_esporta(amb):
    server, canale = amb
    canale.permissions_for = lambda who: discord.Permissions(view_channel=True)
    i = fake_interaction(guild=server, user=fake_member(10), channel=canale)
    cog = ModerationClearCog(bot=MagicMock())
    await cog.esporta_chat.callback(cog, i, 5, canale)
    i.response.send_message.assert_awaited_once()
    i.followup.send.assert_not_awaited()
