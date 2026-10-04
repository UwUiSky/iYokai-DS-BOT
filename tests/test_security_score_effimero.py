"""
tests/test_security_score_effimero.py
=====================================
LC-8: /security-score mostra i punti deboli del server. La risposta
deve vederla solo chi ha lanciato il comando, non tutto il canale.
"""

from unittest.mock import create_autospec

import discord

import cogs.moderation._shared as modulo_shared
import cogs.security.security_score as modulo
from core.database import Database
from core.repositories.security_repo import SecurityRepository, SecuritySettings
from core.security_logic import AntiNukeConfig, AntiRaidConfig
from tests.support.discord_fakes import fake_guild, fake_interaction


async def test_security_score_risponde_in_modo_effimero(monkeypatch):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo_shared, "db", db_finto)
    monkeypatch.setattr(modulo, "db", db_finto)

    repo_finto = create_autospec(SecurityRepository, instance=True)
    repo_finto.get_settings.return_value = SecuritySettings(
        guild_id=666,
        anti_raid=AntiRaidConfig(),
        anti_nuke=AntiNukeConfig(),
        quarantine_role_id=None,
        alert_channel_id=None,
    )
    monkeypatch.setattr(modulo, "security_repo", repo_finto)

    server = fake_guild()
    server.mfa_level = discord.MFALevel.disabled
    server.verification_level = discord.VerificationLevel.low
    interazione = fake_interaction(guild=server)
    cog = modulo.SecurityScoreCog(bot=None)

    await cog.security_score.callback(cog, interazione)

    risposta = interazione.response.send_message.call_args
    assert isinstance(risposta.kwargs["embed"], discord.Embed)
    assert risposta.kwargs.get("ephemeral") is True
