"""
tests/test_leveling_messaggi_di_sistema.py
==========================================
LC-6: i messaggi di sistema di Discord (boost, messaggio fissato,
benvenuto automatico) hanno come autore un utente vero ma non sono
messaggi scritti da lui: non devono dare XP. Contano solo i messaggi
normali e le risposte.
"""

from unittest.mock import create_autospec

import discord
import pytest

import cogs.leveling.leveling as modulo
from core.database import Database
from core.repositories.guild_clan_repo import GuildClanRepository
from core.repositories.leveling_repo import LevelingRepository, TextXpResult
from tests.support.discord_fakes import fake_message


@pytest.fixture
def repo_xp(monkeypatch):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo, "db", db_finto)

    async def mai_in_blacklist(user_id):
        return False

    monkeypatch.setattr(modulo.blacklist_repo, "is_user_blacklisted", mai_in_blacklist)

    clan_finto = create_autospec(GuildClanRepository, instance=True)
    clan_finto.get_member_clan_in_guild.return_value = None
    monkeypatch.setattr(modulo, "guild_clan_repo", clan_finto)

    # Nessun drop casuale: qui si guarda solo l'XP.
    monkeypatch.setattr(modulo, "should_trigger_drop", lambda valore: False)

    finto = create_autospec(LevelingRepository, instance=True)
    finto.add_text_xp.return_value = TextXpResult(
        granted=True, new_xp_total=10, leveled_up=False, new_level=0
    )
    monkeypatch.setattr(modulo, "leveling_repo", finto)
    return finto


async def _ricevi(tipo: discord.MessageType) -> None:
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()  # ferma il task periodico dell'XP vocale
    messaggio = fake_message()
    messaggio.type = tipo
    await cog.on_message(messaggio)


@pytest.mark.parametrize(
    "tipo",
    [
        discord.MessageType.premium_guild_subscription,
        discord.MessageType.premium_guild_tier_1,
        discord.MessageType.pins_add,
        discord.MessageType.new_member,
        discord.MessageType.thread_created,
    ],
)
async def test_un_messaggio_di_sistema_non_da_xp(repo_xp, tipo):
    await _ricevi(tipo)

    repo_xp.add_text_xp.assert_not_awaited()


@pytest.mark.parametrize("tipo", [discord.MessageType.default, discord.MessageType.reply])
async def test_un_messaggio_normale_o_una_risposta_danno_xp(repo_xp, tipo):
    await _ricevi(tipo)

    repo_xp.add_text_xp.assert_awaited_once()
