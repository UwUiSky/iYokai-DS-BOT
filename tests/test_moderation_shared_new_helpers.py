"""
tests/test_moderation_shared_new_helpers.py
===============================================
Test di validate_reason() e post_to_mod_log() (cogs/moderation/
_shared.py). post_to_mod_log passa dal singleton core.database.db,
quindi il pool di test viene collegato con monkeypatch sull'attributo
privato _pool del singleton REALE (stesso pattern già in uso in
tests/test_scheduler.py) — non un mock, il db.get_guild_setting()/
set_guild_setting() reali restano gli stessi, solo il pool a cui si
appoggiano cambia.

Nota: gli altri helper di questo file (ensure_module_enabled,
check_can_moderate, try_dm, format_duration) non hanno test diretti
— coperti solo indirettamente dai test dei comandi che li usano. Non
un problema introdotto qui, un vuoto preesistente non colmato in
questo passaggio (fuori scope per questa sessione).
"""

import discord
import pytest

from cogs.moderation._shared import (
    SETTING_MOD_LOG_CHANNEL,
    post_to_mod_log,
    validate_reason,
)


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.ephemeral_flags: list[bool] = []

    async def send_message(self, content: str, ephemeral: bool = False) -> None:
        self.sent_messages.append(content)
        self.ephemeral_flags.append(ephemeral)


class _FakeInteraction:
    def __init__(self) -> None:
        self.response = _FakeResponse()


class TestValidateReason:
    @pytest.mark.asyncio
    async def test_motivo_valido_restituisce_true_senza_rispondere(self):
        interaction = _FakeInteraction()
        risultato = await validate_reason(interaction, "Spam ripetuto")
        assert risultato is True
        assert interaction.response.sent_messages == []

    @pytest.mark.asyncio
    async def test_motivo_non_valido_risponde_e_restituisce_false(self):
        interaction = _FakeInteraction()
        risultato = await validate_reason(interaction, "ok")
        assert risultato is False
        assert len(interaction.response.sent_messages) == 1
        assert interaction.response.ephemeral_flags == [True]


class _FakeMessageChannel(discord.TextChannel):
    """
    Eredita da discord.TextChannel SENZA chiamare il costruttore
    reale (che richiederebbe stato interno di discord.py non
    disponibile in un test) — serve solo perché post_to_mod_log fa
    un isinstance(channel, discord.TextChannel) reale, che un
    duck-type qualsiasi non supererebbe.
    """

    def __init__(self) -> None:
        self.sent_embeds: list = []

    async def send(self, embed=None) -> None:
        self.sent_embeds.append(embed)


class _FakeGuildForModLog:
    def __init__(self, guild_id: int, channel=None) -> None:
        self.id = guild_id
        self._channel = channel

    def get_channel(self, channel_id: int):
        return self._channel


def _collega_pool_di_test(monkeypatch, clean_db) -> None:
    import core.database as database_module
    monkeypatch.setattr(database_module.db, "_pool", clean_db)


@pytest.mark.asyncio
async def test_post_to_mod_log_nessun_canale_configurato_non_fa_nulla(clean_db, monkeypatch):
    _collega_pool_di_test(monkeypatch, clean_db)
    guild = _FakeGuildForModLog(100)
    embed = discord.Embed(title="Test")
    await post_to_mod_log(guild, embed)  # non deve sollevare eccezioni


@pytest.mark.asyncio
async def test_post_to_mod_log_canale_configurato_invia_embed(clean_db, monkeypatch):
    _collega_pool_di_test(monkeypatch, clean_db)
    from core.database import db

    await db.set_guild_setting(100, SETTING_MOD_LOG_CHANNEL, 555)
    canale_finto = _FakeMessageChannel()
    guild = _FakeGuildForModLog(100, channel=canale_finto)

    embed = discord.Embed(title="Caso di prova")
    await post_to_mod_log(guild, embed)

    assert len(canale_finto.sent_embeds) == 1
    assert canale_finto.sent_embeds[0] is embed


@pytest.mark.asyncio
async def test_post_to_mod_log_canale_non_testuale_non_fa_nulla(clean_db, monkeypatch):
    _collega_pool_di_test(monkeypatch, clean_db)
    from core.database import db

    await db.set_guild_setting(100, SETTING_MOD_LOG_CHANNEL, 555)
    # get_channel restituisce None (es. canale eliminato).
    guild = _FakeGuildForModLog(100, channel=None)

    embed = discord.Embed(title="Test")
    await post_to_mod_log(guild, embed)  # non deve sollevare eccezioni
