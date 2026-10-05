"""
tests/test_basic_logs_errori_invio.py
=====================================
Log di base: se Discord rifiuta il messaggio nel canale dei log
(permesso tolto, canale cancellato, errore 5xx) il listener non
solleva. Un evento non ha nessuno a cui mostrare l'errore, e
un'eccezione qui riempie solo il log del bot a ogni evento.
"""

import datetime
import logging
from unittest.mock import MagicMock, create_autospec

import discord
import pytest

import cogs.logging.basic_logs as modulo
from core.database import Database
from core.repositories.event_log_repo import EventLogRepository
from tests.support.discord_fakes import fake_guild, fake_member, fake_role, fake_text_channel

ID_CANALE_LOG = 31337

ERRORI = {
    "forbidden": discord.Forbidden(MagicMock(status=403, reason="Forbidden"), "Missing Permissions"),
    "not_found": discord.NotFound(MagicMock(status=404, reason="Not Found"), "Unknown Channel"),
    "server_error": discord.DiscordServerError(
        MagicMock(status=503, reason="Service Unavailable"), "upstream"
    ),
}


@pytest.fixture
def repo_eventi(monkeypatch):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    db_finto.get_guild_setting.return_value = ID_CANALE_LOG
    monkeypatch.setattr(modulo, "db", db_finto)
    repo = create_autospec(EventLogRepository, instance=True)
    monkeypatch.setattr(modulo, "event_log_repo", repo)
    return repo


def _server_con_canale_rotto(errore: Exception):
    canale = fake_text_channel(channel_id=ID_CANALE_LOG)
    canale.send.side_effect = errore
    server = fake_guild()
    server.get_channel.return_value = canale
    return server, canale


def _membro(server, ruoli=None, nick=None):
    membro = fake_member(user_id=42, roles=ruoli or [])
    membro.guild = server
    membro.nick = nick
    membro.created_at = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    membro.joined_at = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    membro.display_avatar.url = "https://cdn.discordapp.com/embed/avatars/0.png"
    return membro


def _ruolo(server):
    ruolo = fake_role(role_id=7, name="Nuovo")
    ruolo.guild = server
    return ruolo


async def _ingresso(cog, server):
    await cog.on_member_join(_membro(server))


async def _uscita(cog, server):
    await cog.on_member_remove(_membro(server))


async def _ban(cog, server):
    await cog.on_member_ban(server, _membro(server))


async def _unban(cog, server):
    await cog.on_member_unban(server, _membro(server))


async def _ruoli_e_nick(cog, server):
    prima = _membro(server, ruoli=[], nick=None)
    dopo = _membro(server, ruoli=[fake_role(role_id=7)], nick="nuovo")
    await cog.on_member_update(prima, dopo)


async def _ruolo_creato(cog, server):
    await cog.on_guild_role_create(_ruolo(server))


async def _ruolo_eliminato(cog, server):
    await cog.on_guild_role_delete(_ruolo(server))


EVENTI = {
    "ingresso": (_ingresso, 1),
    "uscita": (_uscita, 1),
    "ban": (_ban, 1),
    "unban": (_unban, 1),
    # Ruoli e nickname cambiati insieme: due messaggi, e il secondo
    # parte anche se il primo è stato rifiutato.
    "ruoli_e_nick": (_ruoli_e_nick, 2),
    "ruolo_creato": (_ruolo_creato, 1),
    "ruolo_eliminato": (_ruolo_eliminato, 1),
}


@pytest.mark.parametrize("evento", EVENTI)
@pytest.mark.parametrize("errore", ERRORI)
async def test_errore_di_invio_non_esce_dal_listener(repo_eventi, caplog, evento, errore):
    server, canale = _server_con_canale_rotto(ERRORI[errore])
    esegui, invii_attesi = EVENTI[evento]
    cog = modulo.BasicLogsCog(bot=None)

    with caplog.at_level(logging.WARNING, logger="iyokai.logging.basic"):
        await esegui(cog, server)

    assert canale.send.await_count == invii_attesi
    # L'evento resta comunque scritto nel database.
    assert repo_eventi.log_event.await_count >= 1
    # E l'errore lascia una riga nel log del bot, con il canale.
    assert str(ID_CANALE_LOG) in caplog.text
