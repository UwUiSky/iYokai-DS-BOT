"""
tests/test_sticky_messages_blocco.py
=======================================
M 10.4 (sticky persi o doppi): un blocco per canale intorno a
cancella-e-rimanda. M 10.6 (D12): ping di ruolo solo con "Menziona tutti".
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.sticky_messages as sticky_module
from cogs.utility.sticky_messages import StickyMessagesCog
from core.repositories.sticky_message_repo import StickyMessageRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel


class _Canale(discord.TextChannel):
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self.invii: list[tuple[str, discord.AllowedMentions]] = []
        self._n = 9000

    async def fetch_message(self, message_id: int):
        raise discord.NotFound(MagicMock(status=404, reason="x"), "non trovato")

    async def send(self, content: str, **kwargs):
        await asyncio.sleep(0)  # cede il turno: è qui che nascono i doppioni
        self._n += 1
        self.invii.append((content, kwargs.get("allowed_mentions")))
        m = MagicMock()
        m.id = self._n
        return m


def _messaggio(canale, guild_id=100):
    m = MagicMock()
    m.author.bot = False
    m.guild.id = guild_id
    m.channel = canale
    return m


@pytest.fixture
def repo(clean_db, monkeypatch):
    r = StickyMessageRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(sticky_module, "sticky_message_repo", r)
    monkeypatch.setattr(
        sticky_module.db, "is_module_active_for_guild", AsyncMock(return_value=True)
    )
    return r


@pytest.mark.asyncio
async def test_dieci_messaggi_veloci_un_solo_sticky(repo):
    await repo.set_sticky(800, 100, "Regole")
    canale = _Canale(800)
    cog = StickyMessagesCog(bot=None)

    await asyncio.gather(*(cog.on_message(_messaggio(canale)) for _ in range(10)))

    assert len(canale.invii) == 1


@pytest.mark.asyncio
async def test_il_ping_di_ruolo_segue_il_permesso_di_chi_ha_configurato(repo):
    await repo.set_sticky(801, 100, "Ciao <@&5>", ping_ruoli=True)
    canale = _Canale(801)
    await StickyMessagesCog(bot=None).on_message(_messaggio(canale))
    menzioni = canale.invii[0][1]
    assert menzioni.roles is True and menzioni.everyone is False

    await repo.set_sticky(802, 100, "Ciao <@&5>")
    canale2 = _Canale(802)
    await StickyMessagesCog(bot=None).on_message(_messaggio(canale2))
    assert canale2.invii[0][1].roles is False


@pytest.mark.asyncio
async def test_sticky_set_ricorda_il_permesso_e_chiede_il_modulo(repo):
    guild = fake_guild(guild_id=100)
    cog = StickyMessagesCog(bot=None)
    canale = fake_text_channel(channel_id=803)
    utente = fake_member(guild_permissions=discord.Permissions(mention_everyone=True))

    await cog.set_sticky.callback(cog, fake_interaction(guild=guild, user=utente), canale, "Ciao")
    assert (await repo.get_sticky(803)).ping_ruoli is True

    sticky_module.db.is_module_active_for_guild.return_value = False
    interazione = fake_interaction(guild=guild, user=utente)
    await cog.set_sticky.callback(cog, interazione, fake_text_channel(channel_id=804), "Ciao")
    assert await repo.get_sticky(804) is None
    assert "modulo" in interazione.response.send_message.await_args.args[0].lower()
