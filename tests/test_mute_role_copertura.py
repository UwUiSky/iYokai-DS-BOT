"""
tests/test_mute_role_copertura.py
=================================
Il ruolo Muted (M 1.7, LIM-30) blocca anche thread, forum, chat dei
vocali e palchi, e viene applicato ai canali creati dopo. Se Discord
rifiuta la creazione del ruolo (es. 250 ruoli già presenti) il comando
risponde invece di rompersi.

Database vero (clean_db): l'impostazione del ruolo la scrive il codice
di produzione al primo mute.
"""

from unittest.mock import MagicMock, create_autospec

import discord
import pytest

from cogs.moderation._shared import MODULE_ACTIONS
from cogs.moderation.softban_mute import (
    SETTING_MUTE_ROLE_ID,
    ModerationSoftbanMuteCog,
    _get_or_create_mute_role,
)
from core.database import db
from tests.support.discord_fakes import (
    fake_forum_channel,
    fake_guild,
    fake_role,
    fake_text_channel,
    fake_voice_channel,
)

ID_SERVER = 100
ID_RUOLO = 88

PERMESSI_NEGATI = (
    "send_messages",
    "send_messages_in_threads",
    "create_public_threads",
    "create_private_threads",
    "add_reactions",
    "speak",
    "connect",
)


@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID_SERVER, MODULE_ACTIONS, True)
    yield
    database_module.db._modules_cache.clear()


def _senza_blocco(canale):
    """Un canale dove il ruolo Muted non ha ancora nessun permesso negato."""
    canale.overwrites_for.return_value = discord.PermissionOverwrite()
    return canale


def _canale(classe, channel_id: int):
    canale = create_autospec(classe, instance=True)
    canale.id = channel_id
    return _senza_blocco(canale)


def _server_con_ogni_tipo_di_canale():
    server = fake_guild(ID_SERVER)
    ruolo = fake_role(ID_RUOLO, "Muted")
    server.create_role.return_value = ruolo
    server.channels = [
        _canale(discord.CategoryChannel, 1),
        _senza_blocco(fake_text_channel(2)),
        _senza_blocco(fake_voice_channel(3)),
        _senza_blocco(fake_forum_channel(4)),
        _canale(discord.StageChannel, 5),
    ]
    return server, ruolo


def _negati(canale, ruolo) -> None:
    canale.set_permissions.assert_awaited_once()
    chiamata = canale.set_permissions.call_args
    assert chiamata.args[0] is ruolo
    for permesso in PERMESSI_NEGATI:
        assert getattr(chiamata.kwargs["overwrite"], permesso) is False, permesso


async def test_il_ruolo_muted_copre_ogni_tipo_di_canale():
    server, ruolo = _server_con_ogni_tipo_di_canale()

    assert await _get_or_create_mute_role(server) is ruolo

    for canale in server.channels:
        _negati(canale, ruolo)


async def test_un_canale_creato_dopo_riceve_il_blocco():
    server, ruolo = _server_con_ogni_tipo_di_canale()
    await _get_or_create_mute_role(server)
    server.get_role.side_effect = lambda role_id: ruolo if role_id == ID_RUOLO else None

    nuovo = _senza_blocco(fake_text_channel(99, "nuovo"))
    nuovo.guild = server
    cog = ModerationSoftbanMuteCog(bot=None)
    await cog.on_guild_channel_create(nuovo)

    _negati(nuovo, ruolo)


async def test_ruolo_gia_esistente_si_coprono_solo_i_canali_scoperti():
    """
    Un ruolo creato prima di questa correzione (o un canale nato a bot
    spento) viene sistemato al mute successivo. I permessi che un
    admin ha aggiunto a mano restano.
    """
    server, ruolo = _server_con_ogni_tipo_di_canale()
    await _get_or_create_mute_role(server)
    server.get_role.side_effect = lambda role_id: ruolo if role_id == ID_RUOLO else None
    coperto, vecchio = fake_text_channel(10), fake_text_channel(11)
    coperto.overwrites_for.return_value = discord.PermissionOverwrite(
        **{permesso: False for permesso in PERMESSI_NEGATI}
    )
    vecchio.overwrites_for.return_value = discord.PermissionOverwrite(
        send_messages=False, add_reactions=False, view_channel=False
    )
    server.channels = [coperto, vecchio]

    assert await _get_or_create_mute_role(server) is ruolo

    server.create_role.assert_awaited_once()
    coperto.set_permissions.assert_not_awaited()
    _negati(vecchio, ruolo)
    assert vecchio.set_permissions.call_args.kwargs["overwrite"].view_channel is False


async def test_un_eccezione_voluta_dall_admin_non_viene_cancellata():
    """
    Un canale "appelli" dove l'admin ha permesso apposta ai silenziati
    di scrivere: il blocco completa solo i permessi non impostati.
    """
    server, ruolo = _server_con_ogni_tipo_di_canale()
    await _get_or_create_mute_role(server)
    server.get_role.side_effect = lambda role_id: ruolo if role_id == ID_RUOLO else None
    appelli = fake_text_channel(12, "appelli")
    appelli.overwrites_for.return_value = discord.PermissionOverwrite(
        send_messages=True, add_reactions=False
    )
    server.channels = [appelli]

    await _get_or_create_mute_role(server)

    permessi = appelli.set_permissions.call_args.kwargs["overwrite"]
    assert permessi.send_messages is True
    assert permessi.send_messages_in_threads is False
    assert permessi.connect is False

    # Completato una volta, al mute successivo non viene più toccato.
    appelli.overwrites_for.return_value = permessi
    appelli.set_permissions.reset_mock()
    await _get_or_create_mute_role(server)
    appelli.set_permissions.assert_not_awaited()


async def test_canale_nuovo_senza_ruolo_muted_nessuna_chiamata():
    server = fake_guild(ID_SERVER)
    nuovo = fake_text_channel(99, "nuovo")
    nuovo.guild = server

    cog = ModerationSoftbanMuteCog(bot=None)
    await cog.on_guild_channel_create(nuovo)

    nuovo.set_permissions.assert_not_awaited()


async def test_canale_nuovo_errore_di_discord_non_esce_dal_listener():
    server, ruolo = _server_con_ogni_tipo_di_canale()
    await _get_or_create_mute_role(server)
    server.get_role.side_effect = lambda role_id: ruolo if role_id == ID_RUOLO else None
    nuovo = _senza_blocco(fake_voice_channel(99, "nuovo"))
    nuovo.guild = server
    nuovo.set_permissions.side_effect = discord.Forbidden(
        MagicMock(status=403, reason="Forbidden"), "Missing Permissions"
    )

    cog = ModerationSoftbanMuteCog(bot=None)
    await cog.on_guild_channel_create(nuovo)

    nuovo.set_permissions.assert_awaited_once()


async def test_creazione_del_ruolo_rifiutata_da_discord_restituisce_none():
    """Con 250 ruoli Discord risponde 400, non 403."""
    server, _ = _server_con_ogni_tipo_di_canale()
    server.create_role.side_effect = discord.HTTPException(
        MagicMock(status=400, reason="Bad Request"), "Maximum number of guild roles reached (250)"
    )

    assert await _get_or_create_mute_role(server) is None
    assert await db.get_guild_setting(ID_SERVER, SETTING_MUTE_ROLE_ID) is None
