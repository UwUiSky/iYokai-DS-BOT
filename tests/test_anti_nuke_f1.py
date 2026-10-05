"""
tests/test_anti_nuke_f1.py
==========================
Anti-nuke, correzioni della fase F1:
- BUG-11: un bot che fa danni viene espulso (i suoi ruoli gestiti non
  si possono togliere);
- LIM-31 / PERF-5: il registro di controllo viene riletto se la voce
  non c'è ancora, e non viene letto affatto dove l'anti-nuke è spento;
- #30 / LIM-38: il recupero ricrea ogni tipo di canale.

L'anti-nuke viene configurato con i suoi comandi (database vero).
Server, canali, membri e voci del registro sono finti fedeli.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest
from discord import app_commands
from discord.ext import commands

import cogs.moderation._shared as modulo_shared
import cogs.security.anti_nuke as modulo
from core.automod_rate_tracker import AutomodRateTracker
from core.database import Database
from core.repositories.security_repo import security_repo
from core.security_logic import NUKE_CATEGORY_CHANNEL
from tests.support.discord_fakes import (
    fake_forum_channel,
    fake_guild,
    fake_interaction,
    fake_member,
    fake_role,
    fake_text_channel,
    fake_voice_channel,
)

GUILD_ID = 666
AUTORE_ID = 4242
BOT_ID = 999


@pytest.fixture
def db_finto(clean_db, monkeypatch):
    finto = create_autospec(Database, instance=True)
    finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo_shared, "db", finto)
    monkeypatch.setattr(modulo, "db", finto)
    monkeypatch.setattr(security_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(modulo, "security_rate_tracker", AutomodRateTracker())
    return finto


@pytest.fixture
def attese(monkeypatch):
    """Le attese tra una lettura e l'altra del registro: registrate, non dormite."""
    finta = AsyncMock()
    monkeypatch.setattr(modulo, "_aspetta", finta)
    return finta


@pytest.fixture
async def cog(db_finto, attese):
    bot = create_autospec(commands.Bot, instance=True)
    bot.user = fake_member(user_id=BOT_ID, bot=True)
    cog = modulo.AntiNukeCog(bot)
    # Anti-nuke acceso e soglia canali a zero: la prima azione è già "di massa".
    await cog.enable.callback(cog, _interazione(), True)
    await cog.limits.callback(
        cog, _interazione(), app_commands.Choice(name="Canali", value=NUKE_CATEGORY_CHANNEL), 0, 60
    )
    return cog


def _interazione() -> MagicMock:
    return fake_interaction(guild=fake_guild(guild_id=GUILD_ID))


def _voce(azione, autore_id: int, bersaglio_id: int | None = None) -> MagicMock:
    voce = create_autospec(discord.AuditLogEntry, instance=True)
    voce.action = azione
    voce.user_id = autore_id
    voce.target = discord.Object(id=bersaglio_id) if bersaglio_id is not None else None
    voce.created_at = datetime.now(timezone.utc)
    return voce


def _server(autore: MagicMock, letture_registro: list[list]) -> MagicMock:
    """
    Server finto. `letture_registro` dice cosa restituisce il registro
    di controllo a ogni lettura (l'ultima vale anche per le successive).
    """
    server = fake_guild(guild_id=GUILD_ID, owner_id=1)
    server.owner = fake_member(user_id=1)
    server.bitrate_limit = 96000
    server.get_member.side_effect = lambda user_id: autore if user_id == autore.id else None
    letture = list(letture_registro)

    def _audit_logs(**_kwargs):
        voci = letture.pop(0) if len(letture) > 1 else letture[0]

        async def _genera():
            for voce in voci:
                yield voce

        return _genera()

    server.audit_logs.side_effect = _audit_logs
    return server


def _canale_cancellato(canale: MagicMock, server: MagicMock, nome: str = "generale") -> MagicMock:
    canale.id = 7001
    canale.name = nome
    canale.guild = server
    canale.position = 4
    canale.overwrites = {}
    canale.category = None
    canale.category_id = None
    return canale


async def _azioni_registrate() -> list[str]:
    return [riga["category"] for riga in await security_repo.get_recent_actions(GUILD_ID)]


# ====================================================================
# M 3.2 — un bot non si punisce togliendo i ruoli
# ====================================================================
async def test_bot_che_cancella_canali_viene_espulso(cog):
    ruolo_gestito = fake_role(role_id=50, name="BotCattivo", managed=True)
    bot_cattivo = fake_member(user_id=AUTORE_ID, bot=True, roles=[ruolo_gestito])
    server = _server(bot_cattivo, [[_voce(discord.AuditLogAction.channel_delete, AUTORE_ID, 7001)]])
    canale = _canale_cancellato(fake_text_channel(), server)

    await cog.on_guild_channel_delete(canale)

    bot_cattivo.kick.assert_awaited_once()
    assert len(bot_cattivo.kick.call_args.kwargs["reason"]) <= 512
    bot_cattivo.edit.assert_not_awaited()
    assert await _azioni_registrate() == ["nuke_channel"]


async def test_persona_con_ruolo_gestito_perde_solo_gli_altri_ruoli(cog):
    # Il ruolo "Server Booster" è gestito da Discord: chiedere di
    # toglierlo fa fallire tutta la modifica.
    booster = fake_role(role_id=51, name="Server Booster", managed=True)
    admin = fake_role(role_id=52, name="Admin", position=5)
    persona = fake_member(user_id=AUTORE_ID, roles=[booster, admin])
    server = _server(persona, [[_voce(discord.AuditLogAction.channel_delete, AUTORE_ID, 7001)]])
    canale = _canale_cancellato(fake_text_channel(), server)

    await cog.on_guild_channel_delete(canale)

    persona.edit.assert_awaited_once()
    assert persona.edit.call_args.kwargs["roles"] == [booster]
    persona.kick.assert_not_awaited()


# ====================================================================
# M 3.3 — il registro di controllo arriva in ritardo
# ====================================================================
async def test_voce_del_registro_arrivata_dopo_due_secondi_viene_contata(cog, attese):
    autore = fake_member(user_id=AUTORE_ID)
    voce = _voce(discord.AuditLogAction.channel_delete, AUTORE_ID, 7001)
    # Prima e seconda lettura: la voce non c'è ancora. Alla terza sì.
    server = _server(autore, [[], [], [voce]])
    canale = _canale_cancellato(fake_text_channel(), server)

    await cog.on_guild_channel_delete(canale)

    assert server.audit_logs.call_count == 3
    assert sum(chiamata.args[0] for chiamata in attese.await_args_list) == 2
    assert await _azioni_registrate() == ["nuke_channel"]
    autore.edit.assert_awaited_once()


async def test_voce_mai_arrivata_si_smette_di_cercare(cog, attese):
    autore = fake_member(user_id=AUTORE_ID)
    server = _server(autore, [[]])
    canale = _canale_cancellato(fake_text_channel(), server)

    await cog.on_guild_channel_delete(canale)

    assert server.audit_logs.call_count == len(modulo.ATTESE_REGISTRO)
    assert await _azioni_registrate() == []


async def test_voce_di_un_altro_canale_non_viene_presa_per_buona(cog):
    # Nel registro c'è la cancellazione di un ALTRO canale fatta da un
    # admin: non va attribuita a questa.
    autore = fake_member(user_id=AUTORE_ID)
    altra = _voce(discord.AuditLogAction.channel_delete, autore_id=31337, bersaglio_id=1234)
    giusta = _voce(discord.AuditLogAction.channel_delete, AUTORE_ID, 7001)
    server = _server(autore, [[altra], [giusta, altra]])
    canale = _canale_cancellato(fake_text_channel(), server)

    await cog.on_guild_channel_delete(canale)

    autore.edit.assert_awaited_once()


async def test_modulo_spento_il_registro_non_viene_letto(cog, db_finto):
    db_finto.is_module_active_for_guild.return_value = False
    autore = fake_member(user_id=AUTORE_ID)
    server = _server(autore, [[_voce(discord.AuditLogAction.kick, AUTORE_ID, 500)]])
    uscito = fake_member(user_id=500)
    uscito.guild = server

    await cog.on_member_remove(uscito)
    await cog.on_guild_channel_delete(_canale_cancellato(fake_text_channel(), server))

    server.audit_logs.assert_not_called()


async def test_anti_nuke_disattivato_il_registro_non_viene_letto(cog):
    await cog.enable.callback(cog, _interazione(), False)
    autore = fake_member(user_id=AUTORE_ID)
    server = _server(autore, [[_voce(discord.AuditLogAction.kick, AUTORE_ID, 500)]])
    uscito = fake_member(user_id=500)
    uscito.guild = server

    await cog.on_member_remove(uscito)

    server.audit_logs.assert_not_called()


async def test_errore_di_discord_sul_registro_non_rompe_l_evento(cog):
    autore = fake_member(user_id=AUTORE_ID)
    server = _server(autore, [[]])
    risposta = MagicMock()
    risposta.status = 500
    risposta.reason = "Internal Server Error"
    server.audit_logs.side_effect = discord.HTTPException(risposta, "errore finto")

    await cog.on_guild_channel_delete(_canale_cancellato(fake_text_channel(), server))

    assert await _azioni_registrate() == []
