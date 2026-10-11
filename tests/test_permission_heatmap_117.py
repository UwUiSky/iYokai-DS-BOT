"""
tests/test_permission_heatmap_117.py
====================================
Difetti trovati leggendo la heatmap:
- @everyone con permessi critici (il rischio piu' grosso) veniva saltato;
- i ruoli piu' alti vanno in cima;
- l'avviso al proprietario: troppi insieme (un ruolo admin dato a 200
  membri) sono un diluvio di messaggi privati; il proprietario non in cache
  si cerca; i nomi dei ruoli non devono rompere il messaggio.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest
from discord.ext import commands

import cogs.security.permission_heatmap as modulo
from core.automod_rate_tracker import AutomodRateTracker
from core.database import Database
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role

ADMIN = discord.Permissions(administrator=True)


@pytest.fixture
def db_finto(monkeypatch):
    finto = create_autospec(Database, instance=True)
    finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo, "db", finto)
    monkeypatch.setattr(modulo, "premium_sbloccato", AsyncMock(return_value=True))
    monkeypatch.setattr(modulo, "heatmap_rate_tracker", AutomodRateTracker())
    return finto


async def test_everyone_con_permessi_critici_e_segnalato_per_primo(db_finto):
    server = fake_guild()
    tutti = fake_role(role_id=0, name="@everyone", permissions=ADMIN)
    tutti.members = []
    basso = fake_role(role_id=10, name="Basso", position=1, permissions=ADMIN)
    alto = fake_role(role_id=11, name="Alto", position=9, permissions=ADMIN)
    basso.members, alto.members = [], []
    server.roles = [tutti, basso, alto]
    interazione = fake_interaction(guild=server)
    cog = modulo.PermissionHeatmapCog(bot=None)

    await cog.permission_heatmap.callback(cog, interazione)

    testo = interazione.response.send_message.call_args.kwargs["embed"].description
    assert "@everyone" in testo and "tutti i membri" in testo
    assert testo.index("@everyone") < testo.index("Alto") < testo.index("Basso")


def _evento(server, ruolo):
    prima, dopo = fake_member(user_id=31, roles=[]), fake_member(user_id=31, roles=[ruolo])
    prima.guild = dopo.guild = server
    server.get_role = MagicMock(return_value=ruolo)
    return prima, dopo


async def test_diluvio_di_avvisi_si_ferma_e_lo_dice_una_volta(db_finto):
    owner = fake_member(user_id=1)
    owner.send = AsyncMock()
    server = fake_guild(owner_id=1)
    server.owner = owner
    ruolo = fake_role(role_id=10, name="Admin", permissions=ADMIN)
    cog = modulo.PermissionHeatmapCog(bot=MagicMock())
    for _ in range(modulo.MAX_AVVISI_PER_FINESTRA + 5):
        prima, dopo = _evento(server, ruolo)
        await cog.on_member_update(prima, dopo)
    # I consentiti + un solo messaggio che dice "basta per ora".
    assert owner.send.await_count == modulo.MAX_AVVISI_PER_FINESTRA + 1
    assert "troppi" in owner.send.await_args.args[0].lower()


async def test_proprietario_fuori_dalla_cache_viene_cercato(db_finto):
    server = fake_guild(owner_id=1)
    server.owner = None
    proprietario = MagicMock()
    proprietario.send = AsyncMock()
    bot = MagicMock()
    bot.fetch_user = AsyncMock(return_value=proprietario)
    ruolo = fake_role(role_id=10, name="Admin", permissions=ADMIN)
    prima, dopo = _evento(server, ruolo)
    await modulo.PermissionHeatmapCog(bot=bot).on_member_update(prima, dopo)
    bot.fetch_user.assert_awaited_once_with(1)
    proprietario.send.assert_awaited_once()


async def test_il_nome_del_ruolo_non_rompe_il_messaggio(db_finto):
    owner = fake_member(user_id=1)
    owner.send = AsyncMock()
    server = fake_guild(owner_id=1)
    server.owner = owner
    ruolo = fake_role(role_id=10, name="**@everyone** `x`", permissions=ADMIN)
    prima, dopo = _evento(server, ruolo)
    await modulo.PermissionHeatmapCog(bot=MagicMock()).on_member_update(prima, dopo)
    testo = owner.send.await_args.args[0]
    assert "@everyone" not in testo.replace("@​everyone", "")
    assert "**\\*\\*" in testo or "\\*\\*" in testo
