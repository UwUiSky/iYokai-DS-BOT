"""
tests/test_automod_badword_list.py
==================================
/automod badword-list con un elenco lungo (LIM-5): un messaggio tiene
2000 caratteri, l'elenco può arrivare a 1000 parole. Oltre la soglia
l'elenco viene mandato come file di testo.
"""

from unittest.mock import create_autospec

import discord
import pytest

import cogs.automod.automod as modulo_automod
import cogs.moderation._shared as modulo_shared
from core.database import Database
from core.repositories.automod_repo import AutomodConfig, AutomodRepository
from tests.support.discord_fakes import fake_interaction


@pytest.fixture
def repo_finto(monkeypatch):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo_shared, "db", db_finto)

    finto = create_autospec(AutomodRepository, instance=True)
    monkeypatch.setattr(modulo_automod, "automod_repo", finto)
    return finto


def _config_con(parole: list[str]) -> AutomodConfig:
    return AutomodConfig(guild_id=666, custom_badwords=tuple(parole), block_invites=False)


async def test_badword_list_con_mille_parole_manda_un_file(repo_finto):
    parole = [f"parolavietata{numero:04d}" for numero in range(1000)]
    repo_finto.get_config.return_value = _config_con(parole)
    interazione = fake_interaction()
    cog = modulo_automod.AutomodCog(bot=None)

    await cog.badword_list.callback(cog, interazione)

    interazione.response.send_message.assert_awaited_once()
    risposta = interazione.response.send_message.call_args
    assert len(risposta.args[0]) <= 2000
    assert "1000" in risposta.args[0]
    assert risposta.kwargs["ephemeral"] is True

    allegato = risposta.kwargs["file"]
    assert isinstance(allegato, discord.File)
    assert allegato.filename.endswith(".txt")
    assert allegato.fp.read().decode("utf-8").splitlines() == parole


async def test_badword_list_corta_resta_nel_messaggio(repo_finto):
    repo_finto.get_config.return_value = _config_con(["spam", "scam"])
    interazione = fake_interaction()
    cog = modulo_automod.AutomodCog(bot=None)

    await cog.badword_list.callback(cog, interazione)

    risposta = interazione.response.send_message.call_args
    assert "`spam`, `scam`" in risposta.args[0]
    assert "file" not in risposta.kwargs
