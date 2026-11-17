"""
tests/test_ruoli_vocali.py
==========================
Ruoli vocali (RUO-044; #123): ruolo a chi è in un canale vocale, tolto quando esce.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.ruoli_vocali as modulo
from cogs.utility.ruoli_vocali import RuoliVocaliCog
from core.repositories.voice_role_repo import VoiceRoleRepository
from core.ruoli_vocali_logic import MAX_RUOLI_VOCALI, cambio_ruoli, correzioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role


def test_RUO_044_cambio_di_canale_da_e_toglie_il_ruolo():


    # RUO-044
    regole = {10: 100, 20: 200, 30: 100}
    assert cambio_ruoli(regole, None, 10) == ({100}, set())
    assert cambio_ruoli(regole, 10, None) == (set(), {100})
    assert cambio_ruoli(regole, 10, 20) == ({200}, {100})
    assert cambio_ruoli(regole, 10, 30) == (set(), set())  # lo stesso ruolo da due canali: nessun cambio
    assert cambio_ruoli(regole, 99, 98) == (set(), set())


def test_RUO_044_correzioni_dopo_il_riavvio():


    # RUO-044
    regole = {10: 100, 30: 100}
    dare, togliere = correzioni(regole, {10: {1, 2}, 30: {3}}, {100: {2, 3, 9}})
    assert dare == [(1, 100)] and togliere == [(9, 100)]


@pytest.fixture
def repo(clean_db):
    return VoiceRoleRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_RUO_044_archivio_cambia_toglie_e_ha_un_tetto(repo):
    # RUO-044
    assert await repo.set(1, 10, 100, 7) and await repo.set(1, 10, 101, 7)  # stesso canale: cambia ruolo
    assert await repo.rules(1) == {10: 101}
    for n in range(MAX_RUOLI_VOCALI - 1):
        assert await repo.set(1, 20 + n, 100, 7)
    assert await repo.set(1, 99, 100, 7) is False  # oltre il tetto
    assert await repo.set(1, 10, 102, 7) is True  # ma cambiare uno che c'è si può
    assert await repo.remove(1, 10) == 102 and await repo.remove(1, 10) is None
    assert await repo.guild_ids() == [1]


class _Scena:
    def __init__(self, monkeypatch, regole):
        self.guild = fake_guild(guild_id=1)
        self.ruolo = fake_role(role_id=100, name="In vocale", position=1)
        self.guild.me.top_role = fake_role(role_id=900, name="Bot", position=50)
        self.guild.get_role = lambda rid: self.ruolo if rid == 100 else None
        self.repo = MagicMock(
            rules=AsyncMock(return_value=regole), set=AsyncMock(return_value=True), remove=AsyncMock(return_value=100)
        )
        monkeypatch.setattr(modulo, "voice_role_repo", self.repo)
        self.cog = RuoliVocaliCog(MagicMock())
        self.membro = fake_member(5, "mario")
        self.membro.guild = self.guild
        self.membro.add_roles = AsyncMock()
        self.membro.remove_roles = AsyncMock()


def _stato(canale_id):
    return MagicMock(channel=MagicMock(id=canale_id) if canale_id else None)


@pytest.mark.asyncio
async def test_RUO_044_entrare_da_il_ruolo_e_uscire_lo_toglie(monkeypatch):
    # RUO-044
    s = _Scena(monkeypatch, {10: 100})
    await s.cog.on_voice_state_update(s.membro, _stato(None), _stato(10))
    s.membro.add_roles.assert_awaited_once()
    await s.cog.on_voice_state_update(s.membro, _stato(10), _stato(None))
    s.membro.remove_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_RUO_044_stesso_canale_bot_e_server_senza_regole_non_fanno_nulla(monkeypatch):
    # RUO-044
    s = _Scena(monkeypatch, {10: 100})
    await s.cog.on_voice_state_update(s.membro, _stato(10), _stato(10))  # muto/sordo, non un cambio
    bot = fake_member(6, "bot", bot=True)
    bot.add_roles = AsyncMock()
    await s.cog.on_voice_state_update(bot, _stato(None), _stato(10))
    s.membro.add_roles.assert_not_awaited()
    bot.add_roles.assert_not_awaited()
    s2 = _Scena(monkeypatch, {})
    await s2.cog.on_voice_state_update(s2.membro, _stato(None), _stato(10))
    s2.membro.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_RUO_044_ruolo_non_assegnabile_non_si_da(monkeypatch):
    # RUO-044
    s = _Scena(monkeypatch, {10: 100})
    s.ruolo.permissions = discord.Permissions(administrator=True)  # diventato pericoloso
    await s.cog.on_voice_state_update(s.membro, _stato(None), _stato(10))
    s.membro.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_RUO_044_il_comando_aggiunge_toglie_ed_elenca(monkeypatch):
    # RUO-044
    s = _Scena(monkeypatch, {10: 100})
    i = fake_interaction(guild=s.guild, user=fake_member(7, "staff"))
    i.user.top_role = fake_role(role_id=800, name="Staff", position=40)
    canale = MagicMock(id=10, mention="<#10>")
    await s.cog.vocale.callback(s.cog, i, "aggiungi", canale, s.ruolo)
    s.repo.set.assert_awaited_once_with(1, 10, 100, 7)
    await s.cog.vocale.callback(s.cog, i, "togli", canale, None)
    s.repo.remove.assert_awaited_once_with(1, 10)
    await s.cog.vocale.callback(s.cog, i, "elenco", None, None)
    assert "<#10>" in i.response.send_message.await_args.args[0]
    assert i.response.send_message.await_args.kwargs["allowed_mentions"].roles is False
