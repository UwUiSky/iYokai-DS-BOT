"""
tests/test_feed_alerts_behavior.py
======================================
Test del comportamento REALE dei comandi /alerts — non solo che il
cog carica, contro PostgreSQL reale.
"""

import pytest

from cogs.utility.feed_alerts import MODULE_FEED_ALERTS, FeedAlertsCog
from core.database import Database


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.sent_embeds: list = []

    async def send_message(self, content: str = None, embed=None, ephemeral: bool = False) -> None:
        if content is not None:
            self.sent_messages.append(content)
        if embed is not None:
            self.sent_embeds.append(embed)


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self.mention = f"<#{channel_id}>"


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeInteraction:
    def __init__(self, guild_id: int | None, user_id: int = 1) -> None:
        self.guild = _FakeGuild(guild_id) if guild_id is not None else None
        self.user = _FakeUser(user_id)
        self.response = _FakeResponse()


@pytest.mark.asyncio
async def test_add_modulo_disattivato_rifiuta(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 900000001
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)

        import cogs.utility.feed_alerts as feed_alerts_module
        monkeypatch.setattr(feed_alerts_module, "db", database)

        cog = FeedAlertsCog(bot=None)
        interaction = _FakeInteraction(guild_id)
        canale = _FakeChannel(500)

        await cog.add.callback(
            cog, interaction, feed_url="https://esempio.com/feed", channel=canale,
            label="Test", message_template=None,
        )

        assert "non è attivo" in interaction.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 900000001")
        await database.close()


@pytest.mark.asyncio
async def test_add_list_remove_ciclo_completo(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 900000002
        await database.set_module_active_for_guild(guild_id, MODULE_FEED_ALERTS, True)

        import cogs.utility.feed_alerts as feed_alerts_module
        from core.repositories.feed_subscription_repo import FeedSubscriptionRepository
        from core.repositories.twitch_subscription_repo import TwitchSubscriptionRepository

        monkeypatch.setattr(feed_alerts_module, "db", database)
        repo_di_test = FeedSubscriptionRepository(pool_provider=lambda: database.pool)
        monkeypatch.setattr(feed_alerts_module, "feed_subscription_repo", repo_di_test)
        monkeypatch.setattr(
            feed_alerts_module,
            "twitch_subscription_repo",
            TwitchSubscriptionRepository(pool_provider=lambda: database.pool),
        )

        cog = FeedAlertsCog(bot=None)
        canale = _FakeChannel(500)

        # add
        interaction_add = _FakeInteraction(guild_id)
        await cog.add.callback(
            cog, interaction_add, feed_url="https://esempio.com/feed.rss", channel=canale,
            label="Canale di prova", message_template=None,
        )
        assert "Sottoscrizione creata" in interaction_add.response.sent_messages[0]

        # list
        interaction_list = _FakeInteraction(guild_id)
        await cog.list_alerts.callback(cog, interaction_list)
        assert len(interaction_list.response.sent_embeds) == 1
        assert "Canale di prova" in interaction_list.response.sent_embeds[0].description

        sottoscrizioni = await repo_di_test.list_subscriptions(guild_id)
        subscription_id = sottoscrizioni[0].id

        # remove
        interaction_remove = _FakeInteraction(guild_id)
        await cog.remove.callback(cog, interaction_remove, subscription_id=f"RSS-{subscription_id}")
        assert "rimossa" in interaction_remove.response.sent_messages[0].lower()

        interaction_list2 = _FakeInteraction(guild_id)
        await cog.list_alerts.callback(cog, interaction_list2)
        assert "Nessuna sottoscrizione" in interaction_list2.response.sent_messages[0]
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 900000002")
        await database.pool.execute("DELETE FROM feed_subscriptions WHERE guild_id = 900000002")
        await database.close()


@pytest.mark.asyncio
async def test_remove_non_permette_di_toccare_altro_server(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()

        import cogs.utility.feed_alerts as feed_alerts_module
        from core.repositories.feed_subscription_repo import FeedSubscriptionRepository

        monkeypatch.setattr(feed_alerts_module, "db", database)
        repo_di_test = FeedSubscriptionRepository(pool_provider=lambda: database.pool)
        monkeypatch.setattr(feed_alerts_module, "feed_subscription_repo", repo_di_test)

        subscription_id = await repo_di_test.add_subscription(
            900000003, 500, "https://esempio.com/feed", "Test", 1
        )

        cog = FeedAlertsCog(bot=None)
        interaction = _FakeInteraction(guild_id=900000004)  # server diverso

        await cog.remove.callback(cog, interaction, subscription_id=f"RSS-{subscription_id}")

        assert "Nessuna sottoscrizione trovata" in interaction.response.sent_messages[0]
        assert len(await repo_di_test.list_subscriptions(900000003)) == 1
    finally:
        await database.pool.execute("DELETE FROM feed_subscriptions WHERE guild_id = 900000003")
        await database.close()


@pytest.mark.asyncio
async def test_add_fuori_da_un_server_rifiuta():
    cog = FeedAlertsCog(bot=None)
    interaction = _FakeInteraction(guild_id=None)
    canale = _FakeChannel(500)

    await cog.add.callback(
        cog, interaction, feed_url="https://esempio.com/feed", channel=canale,
        label="Test", message_template=None,
    )

    assert "solo dentro un server" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_add_twitch_e_list_mostra_entrambi_i_tipi_con_prefissi(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        guild_id = 900000005
        await database.set_module_active_for_guild(guild_id, MODULE_FEED_ALERTS, True)

        import cogs.utility.feed_alerts as feed_alerts_module
        from core.repositories.feed_subscription_repo import FeedSubscriptionRepository
        from core.repositories.twitch_subscription_repo import TwitchSubscriptionRepository

        monkeypatch.setattr(feed_alerts_module, "db", database)
        feed_repo = FeedSubscriptionRepository(pool_provider=lambda: database.pool)
        twitch_repo = TwitchSubscriptionRepository(pool_provider=lambda: database.pool)
        monkeypatch.setattr(feed_alerts_module, "feed_subscription_repo", feed_repo)
        monkeypatch.setattr(feed_alerts_module, "twitch_subscription_repo", twitch_repo)

        cog = FeedAlertsCog(bot=None)
        canale = _FakeChannel(500)

        interaction_add = _FakeInteraction(guild_id)
        await cog.add_twitch.callback(
            cog, interaction_add, twitch_login="streamerx", channel=canale, label="Streamer X"
        )
        assert "Sottoscrizione Twitch creata" in interaction_add.response.sent_messages[0]

        interaction_add_rss = _FakeInteraction(guild_id)
        await cog.add.callback(
            cog, interaction_add_rss, feed_url="https://esempio.com/feed.rss", channel=canale,
            label="Un feed", message_template=None,
        )

        interaction_list = _FakeInteraction(guild_id)
        await cog.list_alerts.callback(cog, interaction_list)

        descrizione = interaction_list.response.sent_embeds[0].description
        assert "TW-" in descrizione
        assert "RSS-" in descrizione
        assert "Streamer X" in descrizione
        assert "Un feed" in descrizione

        # remove con prefisso TW rimuove solo la sottoscrizione Twitch
        sottoscrizioni_twitch = await twitch_repo.list_subscriptions(guild_id)
        twitch_id = sottoscrizioni_twitch[0].id

        interaction_remove = _FakeInteraction(guild_id)
        await cog.remove.callback(cog, interaction_remove, subscription_id=f"TW-{twitch_id}")

        assert "rimossa" in interaction_remove.response.sent_messages[0].lower()
        assert await twitch_repo.list_subscriptions(guild_id) == []
        assert len(await feed_repo.list_subscriptions(guild_id)) == 1  # il feed resta
    finally:
        await database.pool.execute("DELETE FROM guild_config WHERE guild_id = 900000005")
        await database.pool.execute("DELETE FROM feed_subscriptions WHERE guild_id = 900000005")
        await database.pool.execute("DELETE FROM twitch_subscriptions WHERE guild_id = 900000005")
        await database.close()


@pytest.mark.asyncio
async def test_remove_con_formato_id_non_valido_avvisa():
    cog = FeedAlertsCog(bot=None)
    interaction = _FakeInteraction(guild_id=900000006)

    await cog.remove.callback(cog, interaction, subscription_id="qualcosa_senza_trattino")

    assert "Formato ID non valido" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_remove_con_prefisso_sconosciuto_avvisa():
    cog = FeedAlertsCog(bot=None)
    interaction = _FakeInteraction(guild_id=900000007)

    await cog.remove.callback(cog, interaction, subscription_id="XYZ-5")

    assert "Prefisso non riconosciuto" in interaction.response.sent_messages[0]
