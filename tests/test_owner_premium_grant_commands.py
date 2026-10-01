"""
tests/test_owner_premium_grant_commands.py
==============================================
Test del comportamento REALE di /owner premium-grant|revoke|
subscriptions (SPEC.md §3.1, abbonamento mensile/annuale per modulo)
— stesso schema di tests/test_owner_blacklist_commands.py.
"""

import pytest

from cogs.utility.owner_premium import OwnerPremiumCog
from core.config import config
from core.database import Database
from core.premium import PremiumModule, registry

_OWNER_ID = config.OWNER_ID


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    async def send_message(self, content: str = None, ephemeral: bool = False) -> None:
        if content is not None:
            self.sent_messages.append(content)


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeInteraction:
    def __init__(self, user_id: int) -> None:
        self.user = _FakeUser(user_id)
        self.response = _FakeResponse()


class _FakeBot:
    def get_guild(self, guild_id: int):
        return None


class _FakeChoice:
    def __init__(self, name: str, value: str) -> None:
        self.name = name
        self.value = value


@pytest.fixture
async def cog_e_database(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    await database.pool.execute("DELETE FROM module_subscriptions WHERE guild_id = 700")

    from core.repositories.module_subscription_repo import module_subscription_repo
    original_provider = module_subscription_repo._pool_provider
    module_subscription_repo._pool_provider = lambda: database.pool

    registry.register(
        PremiumModule(
            category="utility",
            name="test_grant_modulo", display_name="Modulo Test Grant", description="x"
        )
    )
    registry.register(
        PremiumModule(
            category="utility",
            name="test_grant_gratuito", display_name="Sempre Gratis", description="x",
            premium_capable=False,
        )
    )

    cog = OwnerPremiumCog(_FakeBot())
    yield cog, database

    module_subscription_repo._pool_provider = original_provider
    await database.pool.execute("DELETE FROM module_subscriptions WHERE guild_id = 700")
    await database.close()


@pytest.mark.asyncio
async def test_premium_grant_rifiuta_non_owner(cog_e_database):
    cog, database = cog_e_database
    interaction = _FakeInteraction(user_id=_OWNER_ID + 1)

    await cog.premium_grant.callback(
        cog, interaction, guild_id="700", module_name="test_grant_modulo",
        duration=_FakeChoice("Mensile (30 giorni)", "monthly"),
    )

    assert "riservato al proprietario" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_premium_grant_modulo_inesistente_avvisa(cog_e_database):
    cog, database = cog_e_database
    interaction = _FakeInteraction(user_id=_OWNER_ID)

    await cog.premium_grant.callback(
        cog, interaction, guild_id="700", module_name="non_esiste",
        duration=_FakeChoice("Mensile (30 giorni)", "monthly"),
    )

    assert "non trovato" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_premium_grant_modulo_sempre_gratuito_rifiuta(cog_e_database):
    cog, database = cog_e_database
    interaction = _FakeInteraction(user_id=_OWNER_ID)

    await cog.premium_grant.callback(
        cog, interaction, guild_id="700", module_name="test_grant_gratuito",
        duration=_FakeChoice("Mensile (30 giorni)", "monthly"),
    )

    assert "sempre-gratuito" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_premium_grant_mensile_concede_30_giorni(cog_e_database):
    cog, database = cog_e_database
    interaction = _FakeInteraction(user_id=_OWNER_ID)

    await cog.premium_grant.callback(
        cog, interaction, guild_id="700", module_name="test_grant_modulo",
        duration=_FakeChoice("Mensile (30 giorni)", "monthly"),
    )

    assert "concesso" in interaction.response.sent_messages[0]

    from core.repositories.module_subscription_repo import module_subscription_repo
    assert await module_subscription_repo.is_active(700, "test_grant_modulo") is True


@pytest.mark.asyncio
async def test_premium_revoke_funziona(cog_e_database):
    cog, database = cog_e_database

    await cog.premium_grant.callback(
        cog, _FakeInteraction(user_id=_OWNER_ID), guild_id="700", module_name="test_grant_modulo",
        duration=_FakeChoice("Annuale (365 giorni)", "yearly"),
    )

    interaction_revoke = _FakeInteraction(user_id=_OWNER_ID)
    await cog.premium_revoke.callback(
        cog, interaction_revoke, guild_id="700", module_name="test_grant_modulo"
    )

    assert "revocato" in interaction_revoke.response.sent_messages[0]

    from core.repositories.module_subscription_repo import module_subscription_repo
    assert await module_subscription_repo.is_active(700, "test_grant_modulo") is False


@pytest.mark.asyncio
async def test_premium_revoke_senza_abbonamento_avvisa(cog_e_database):
    cog, database = cog_e_database
    interaction = _FakeInteraction(user_id=_OWNER_ID)

    await cog.premium_revoke.callback(
        cog, interaction, guild_id="700", module_name="test_grant_modulo"
    )

    assert "non aveva un abbonamento" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_premium_subscriptions_elenca_gli_abbonamenti(cog_e_database):
    cog, database = cog_e_database

    await cog.premium_grant.callback(
        cog, _FakeInteraction(user_id=_OWNER_ID), guild_id="700", module_name="test_grant_modulo",
        duration=_FakeChoice("Mensile (30 giorni)", "monthly"),
    )

    interaction = _FakeInteraction(user_id=_OWNER_ID)
    await cog.premium_subscriptions.callback(cog, interaction, guild_id="700")

    assert "test_grant_modulo" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_premium_subscriptions_vuoto_avvisa(cog_e_database):
    cog, database = cog_e_database
    interaction = _FakeInteraction(user_id=_OWNER_ID)

    await cog.premium_subscriptions.callback(cog, interaction, guild_id="700")

    assert "Nessun abbonamento" in interaction.response.sent_messages[0]
