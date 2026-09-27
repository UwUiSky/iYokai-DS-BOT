"""
tests/test_snipe_cog_behavior.py
====================================
Test comportamentali di SnipeCog (SPEC.md §14.11/§14.12) contro
PostgreSQL reale — stesso pattern di tests/test_moderation_shared_
new_helpers.py per il pool, con oggetti Discord finti minimali per
payload/messaggi (nessun isinstance reale su questi nel cog, solo
accesso attributi — duck typing sufficiente).
"""

import discord
import pytest

from cogs.logging.basic_logs import SETTING_LOG_CHANNEL
from cogs.utility.snipe import MODULE_GHOST_PING, MODULE_REACTIONSNIPE, SnipeCog


def _collega_pool_di_test(monkeypatch, clean_db) -> None:
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()


class _FakeEmoji:
    def __init__(self, s: str) -> None:
        self._s = s

    def __str__(self) -> str:
        return self._s


class _FakeReactionRemovePayload:
    def __init__(self, guild_id: int, channel_id: int, message_id: int, user_id: int, emoji: str) -> None:
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.message_id = message_id
        self.user_id = user_id
        self.emoji = _FakeEmoji(emoji)


class _FakeGuild:
    def __init__(self, guild_id: int, channel=None) -> None:
        self.id = guild_id
        self._channel = channel

    def get_channel(self, channel_id: int):
        return self._channel


class _FakeBot:
    def __init__(self, guild: _FakeGuild) -> None:
        self._guild = guild

    def get_guild(self, guild_id: int):
        return self._guild if self._guild.id == guild_id else None


class _FakeLogChannel(discord.TextChannel):
    def __init__(self) -> None:
        self.sent_embeds: list = []

    async def send(self, embed=None) -> None:
        self.sent_embeds.append(embed)


class _FakeMentionedUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeAuthor:
    def __init__(self, author_id: int, bot: bool = False) -> None:
        self.id = author_id
        self.bot = bot


class _FakeChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id


class _FakeMessage:
    def __init__(
        self,
        message_id: int,
        guild: _FakeGuild,
        author: _FakeAuthor,
        channel_id: int,
        mentions: list | None = None,
        mention_everyone: bool = False,
    ) -> None:
        self.id = message_id
        self.guild = guild
        self.author = author
        self.channel = _FakeChannel(channel_id)
        self.mentions = mentions or []
        self.mention_everyone = mention_everyone


class _FakeDeletePayload:
    def __init__(self, guild_id: int, message_id: int) -> None:
        self.guild_id = guild_id
        self.message_id = message_id


@pytest.fixture(autouse=True)
def _pool(monkeypatch, clean_db):
    _collega_pool_di_test(monkeypatch, clean_db)
    return clean_db


class TestReactionsnipe:
    @pytest.mark.asyncio
    async def test_modulo_disattivato_non_registra_nulla(self):
        cog = SnipeCog(bot=_FakeBot(_FakeGuild(100)))
        await cog.on_raw_reaction_remove(_FakeReactionRemovePayload(100, 200, 300, 1, "😀"))
        assert cog._last_removed_reaction.get(200) is None

    @pytest.mark.asyncio
    async def test_modulo_attivo_registra_la_rimozione(self):
        from core.database import db

        await db.set_module_active_for_guild(100, MODULE_REACTIONSNIPE, True)
        cog = SnipeCog(bot=_FakeBot(_FakeGuild(100)))

        await cog.on_raw_reaction_remove(_FakeReactionRemovePayload(100, 200, 300, 1, "😀"))

        registrata = cog._last_removed_reaction.get(200)
        assert registrata is not None
        assert registrata.emoji == "😀"
        assert registrata.user_id == 1
        assert registrata.message_id == 300


class TestGhostPingDetection:
    @pytest.mark.asyncio
    async def test_messaggio_senza_menzioni_non_viene_tracciato(self):
        from core.database import db

        await db.set_module_active_for_guild(100, MODULE_GHOST_PING, True)
        cog = SnipeCog(bot=_FakeBot(_FakeGuild(100)))
        guild = _FakeGuild(100)

        await cog.on_message(_FakeMessage(1, guild, _FakeAuthor(1), channel_id=200))

        assert cog._tracked_mentions.get(1) is None

    @pytest.mark.asyncio
    async def test_messaggio_con_menzione_cancellato_invia_avviso_nel_log(self):
        from core.database import db

        log_channel = _FakeLogChannel()
        guild = _FakeGuild(100, channel=log_channel)
        await db.set_module_active_for_guild(100, MODULE_GHOST_PING, True)
        await db.set_guild_setting(100, SETTING_LOG_CHANNEL, 999)

        cog = SnipeCog(bot=_FakeBot(guild))
        messaggio = _FakeMessage(
            1, guild, _FakeAuthor(1), channel_id=200, mentions=[_FakeMentionedUser(2)]
        )
        await cog.on_message(messaggio)
        assert cog._tracked_mentions.get(1) is not None

        await cog.on_raw_message_delete(_FakeDeletePayload(100, 1))

        assert len(log_channel.sent_embeds) == 1
        assert cog._tracked_mentions.get(1) is None  # consumato dopo l'avviso

    @pytest.mark.asyncio
    async def test_messaggio_non_cancellato_non_invia_nulla(self):
        from core.database import db

        log_channel = _FakeLogChannel()
        guild = _FakeGuild(100, channel=log_channel)
        await db.set_module_active_for_guild(100, MODULE_GHOST_PING, True)
        await db.set_guild_setting(100, SETTING_LOG_CHANNEL, 999)

        cog = SnipeCog(bot=_FakeBot(guild))
        await cog.on_message(
            _FakeMessage(1, guild, _FakeAuthor(1), channel_id=200, mentions=[_FakeMentionedUser(2)])
        )

        # Un'altra cancellazione, non collegata a nessun messaggio tracciato.
        await cog.on_raw_message_delete(_FakeDeletePayload(100, 999999))

        assert log_channel.sent_embeds == []

    @pytest.mark.asyncio
    async def test_messaggio_di_un_bot_non_viene_tracciato(self):
        from core.database import db

        await db.set_module_active_for_guild(100, MODULE_GHOST_PING, True)
        cog = SnipeCog(bot=_FakeBot(_FakeGuild(100)))
        guild = _FakeGuild(100)

        await cog.on_message(
            _FakeMessage(1, guild, _FakeAuthor(1, bot=True), channel_id=200, mentions=[_FakeMentionedUser(2)])
        )

        assert cog._tracked_mentions.get(1) is None
