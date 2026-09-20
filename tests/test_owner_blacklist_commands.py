"""
tests/test_owner_blacklist_commands.py
===========================================
Test del comportamento REALE dei comandi blacklist/leave-guild in
OwnerPremiumCog — non solo che il cog carica (già in test_owner_
premium_cog_smoke.py), ma che il controllo owner-only funziona
davvero e che le azioni hanno l'effetto atteso, contro PostgreSQL
reale. app_commands.Command.callback invocato direttamente (verificato
prima di scrivere questi test che è il modo corretto di chiamare il
codice sotto un @group.command senza passare per il dispatch completo
di discord.py).
"""

import pytest

from cogs.utility.owner_premium import OwnerPremiumCog
from core.config import config
from core.database import Database

_OWNER_ID = config.OWNER_ID  # valore reale già impostato dall'ambiente di test (conftest.py)


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    async def send_message(self, content: str, ephemeral: bool = False) -> None:
        self.sent_messages.append(content)


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeInteraction:
    def __init__(self, user_id: int) -> None:
        self.user = _FakeUser(user_id)
        self.response = _FakeResponse()


class _FakeGuildToLeave:
    def __init__(self, guild_id: int, name: str = "Server di prova") -> None:
        self.id = guild_id
        self.name = name
        self.left = False

    async def leave(self) -> None:
        self.left = True


class _FakeBot:
    def __init__(self, guilds: dict[int, _FakeGuildToLeave] | None = None) -> None:
        self._guilds = guilds or {}

    def get_guild(self, guild_id: int):
        return self._guilds.get(guild_id)


@pytest.mark.asyncio
async def test_blacklist_user_add_rifiuta_non_owner(monkeypatch):
    cog = OwnerPremiumCog(_FakeBot())
    interaction = _FakeInteraction(user_id=_OWNER_ID + 1)  # non l'owner

    await cog.blacklist_user_add.callback(cog, interaction, user_id="1", reason=None)

    assert "riservato al proprietario" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_blacklist_user_add_e_remove_funzionano_davvero(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute("DELETE FROM user_blacklist WHERE user_id = 555")
    
        from core.repositories.blacklist_repo import blacklist_repo
        original_provider = blacklist_repo._pool_provider
        blacklist_repo._pool_provider = lambda: database.pool

        try:
            cog = OwnerPremiumCog(_FakeBot())
            interaction = _FakeInteraction(user_id=_OWNER_ID)  # l'owner

            await cog.blacklist_user_add.callback(cog, interaction, user_id="555", reason="test")
            assert await blacklist_repo.is_user_blacklisted(555) is True

            interaction2 = _FakeInteraction(user_id=_OWNER_ID)
            await cog.blacklist_user_remove.callback(cog, interaction2, user_id="555")
            assert await blacklist_repo.is_user_blacklisted(555) is False
        finally:
            blacklist_repo._pool_provider = original_provider
    finally:
        await database.pool.execute("DELETE FROM user_blacklist WHERE user_id = 555")
        await database.close()


@pytest.mark.asyncio
async def test_blacklist_guild_add_fa_uscire_il_bot_se_gia_presente(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        await database.pool.execute("DELETE FROM guild_blacklist WHERE guild_id = 777")
    
        from core.repositories.blacklist_repo import blacklist_repo
        original_provider = blacklist_repo._pool_provider
        blacklist_repo._pool_provider = lambda: database.pool

        try:
            guild = _FakeGuildToLeave(777)
            cog = OwnerPremiumCog(_FakeBot(guilds={777: guild}))
            interaction = _FakeInteraction(user_id=_OWNER_ID)

            await cog.blacklist_guild_add.callback(
                cog, interaction, guild_id="777", reason="raid"
            )

            assert guild.left is True
            assert await blacklist_repo.is_guild_blacklisted(777) is True
        finally:
            blacklist_repo._pool_provider = original_provider
    finally:
        await database.pool.execute("DELETE FROM guild_blacklist WHERE guild_id = 777")
        await database.close()


@pytest.mark.asyncio
async def test_leave_guild_esce_dal_server_indicato(monkeypatch):
    guild = _FakeGuildToLeave(888, name="Server da abbandonare")
    cog = OwnerPremiumCog(_FakeBot(guilds={888: guild}))
    interaction = _FakeInteraction(user_id=_OWNER_ID)

    await cog.leave_guild.callback(cog, interaction, guild_id="888")

    assert guild.left is True
    assert "Server da abbandonare" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_leave_guild_server_non_presente_non_solleva(monkeypatch):
    cog = OwnerPremiumCog(_FakeBot(guilds={}))
    interaction = _FakeInteraction(user_id=_OWNER_ID)

    await cog.leave_guild.callback(cog, interaction, guild_id="999999")

    assert "non risulta presente" in interaction.response.sent_messages[0]
