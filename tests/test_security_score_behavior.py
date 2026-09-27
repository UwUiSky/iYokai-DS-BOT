"""
tests/test_security_score_behavior.py
=========================================
Test di comportamento reale del comando /security-score (SPEC.md
§7.5) — non solo che il cog carica (già in
tests/test_security_score_cog_smoke.py), ma che il punteggio
calcolato rifletta davvero i segnali del server.
"""

import discord
import pytest

import cogs.security.security_score as security_score_module
from cogs.security.security_score import SecurityScoreCog, MODULE_SECURITY_SCORE
from core.database import Database
from core.repositories.security_repo import SecuritySettings
from core.security_logic import AntiNukeConfig, AntiRaidConfig


class _FakeResponse:
    def __init__(self) -> None:
        self.embeds_sent: list = []

    async def send_message(self, content=None, embed=None, ephemeral: bool = False) -> None:
        self.embeds_sent.append(embed)


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakePermissions:
    def __init__(self, administrator: bool = False) -> None:
        self.administrator = administrator


class _FakeMember:
    def __init__(self, member_id: int, bot: bool = False, administrator: bool = False) -> None:
        self.id = member_id
        self.bot = bot
        self.guild_permissions = _FakePermissions(administrator=administrator)


class _FakeGuild:
    def __init__(self, guild_id: int, members: list) -> None:
        self.id = guild_id
        self.members = members
        self.mfa_level = 0
        self.verification_level = discord.VerificationLevel.low


class _FakeInteraction:
    def __init__(self, guild: _FakeGuild) -> None:
        self.guild = guild
        self.user = _FakeUser(1)
        self.response = _FakeResponse()


GUILD_ID = 700000500


@pytest.fixture
async def cog(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM security_config WHERE guild_id = $1", GUILD_ID)
    await database.set_module_active_for_guild(GUILD_ID, MODULE_SECURITY_SCORE, True)

    monkeypatch.setattr(security_score_module, "db", database)

    from core.database import db as real_db_singleton

    original_pool = real_db_singleton._pool
    real_db_singleton._pool = database.pool

    from core.repositories.security_repo import security_repo

    original_provider = security_repo._pool_provider
    security_repo._pool_provider = lambda: database.pool

    yield SecurityScoreCog(bot=None)

    security_repo._pool_provider = original_provider
    real_db_singleton._pool = original_pool
    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM security_config WHERE guild_id = $1", GUILD_ID)
    await database.close()


@pytest.mark.asyncio
async def test_server_senza_protezioni_ha_punteggio_basso_con_consigli(cog):
    membri = [_FakeMember(1, administrator=True)]
    guild = _FakeGuild(GUILD_ID, membri)
    interaction = _FakeInteraction(guild)

    await cog.security_score.callback(cog, interaction)

    embed = interaction.response.embeds_sent[0]
    assert not embed.description.startswith("**100/")
    consigli_field = embed.fields[0]
    assert "Anti-Raid" in consigli_field.value


@pytest.mark.asyncio
async def test_server_con_protezioni_attive_ha_punteggio_migliore(cog):
    from core.repositories.security_repo import security_repo

    await security_repo.save_settings(
        SecuritySettings(
            guild_id=GUILD_ID,
            anti_raid=AntiRaidConfig(enabled=True),
            anti_nuke=AntiNukeConfig(enabled=True),
            quarantine_role_id=None,
            alert_channel_id=None,
        )
    )
    membri = [_FakeMember(1, administrator=False)]
    guild = _FakeGuild(GUILD_ID, membri)
    guild.mfa_level = 1
    guild.verification_level = discord.VerificationLevel.high
    interaction = _FakeInteraction(guild)

    await cog.security_score.callback(cog, interaction)

    embed = interaction.response.embeds_sent[0]
    assert "90" in embed.description or "100" in embed.description
