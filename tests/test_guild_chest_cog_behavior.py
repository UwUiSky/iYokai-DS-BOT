"""
tests/test_guild_chest_cog_behavior.py
==========================================
Test del comportamento REALE di /cassa saldo|sblocca-premium — contro
PostgreSQL vero (SPEC.md §15.15).
"""

from datetime import datetime, timedelta, timezone

import discord
import pytest

from cogs.leveling.leveling import LevelingCog
from core.repositories.guild_chest_repo import REASON_WEEKLY_PERSONAL_DECAY, guild_chest_repo

# Join molto nel passato rispetto a "ora" (qualunque sia "ora" quando
# la suite viene eseguita) — garantisce che il tier 1 (6 mesi) sia
# già sbloccato temporalmente, indipendentemente dalla data reale.
JOIN = datetime.now(timezone.utc) - timedelta(days=400)
JOIN_RECENTE = datetime.now(timezone.utc) - timedelta(days=10)  # tier 1 NON sbloccato


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
    def __init__(self, guild_id: int, member_count: int = 500) -> None:
        self.id = guild_id
        self.member_count = member_count


class _FakeInteraction:
    def __init__(self, guild_id: int | None, member_count: int = 500) -> None:
        self.guild = _FakeGuild(guild_id, member_count) if guild_id is not None else None
        self.user = None
        self.response = _FakeResponse()


@pytest.fixture(autouse=True)
def _collega_pool_di_test(monkeypatch, clean_db):
    import core.database as database_module
    monkeypatch.setattr(database_module.db, "_pool", clean_db)


@pytest.fixture
async def cog():
    c = LevelingCog(bot=None)
    c.cog_unload()
    return c


async def _configura_guild(clean_db, guild_id: int, joined_at: datetime = JOIN) -> None:
    await clean_db.execute(
        "INSERT INTO guild_config (guild_id, created_at) VALUES ($1, $2)",
        guild_id,
        joined_at,
    )


@pytest.mark.asyncio
async def test_saldo_di_una_cassa_vuota(cog):
    interaction = _FakeInteraction(guild_id=100)

    await cog.chest_saldo.callback(cog, interaction)

    embed = interaction.response.sent_embeds[0]
    assert "0" in embed.description


@pytest.mark.asyncio
async def test_saldo_mostra_gli_ultimi_movimenti(cog):
    await guild_chest_repo.deposit(100, 5_000, REASON_WEEKLY_PERSONAL_DECAY)
    interaction = _FakeInteraction(guild_id=100)

    await cog.chest_saldo.callback(cog, interaction)

    embed = interaction.response.sent_embeds[0]
    assert "5000" in embed.description
    assert any(REASON_WEEKLY_PERSONAL_DECAY in f.value for f in embed.fields)


@pytest.mark.asyncio
async def test_sblocca_premium_tempo_non_sbloccato(cog, clean_db):
    await _configura_guild(clean_db, 100, joined_at=JOIN_RECENTE)
    await guild_chest_repo.deposit(100, 10_000_000, REASON_WEEKLY_PERSONAL_DECAY)
    interaction = _FakeInteraction(guild_id=100)

    await cog.chest_sblocca_premium.callback(cog, interaction, tier=1)

    assert "non è ancora passato abbastanza tempo" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_sblocca_premium_saldo_insufficiente(cog, clean_db):
    await _configura_guild(clean_db, 100, joined_at=JOIN)
    await guild_chest_repo.deposit(100, 1_000, REASON_WEEKLY_PERSONAL_DECAY)  # troppo poco
    interaction = _FakeInteraction(guild_id=100)

    await cog.chest_sblocca_premium.callback(cog, interaction, tier=1)

    assert "La cassa non basta" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_sblocca_premium_riuscito(cog, clean_db):
    await _configura_guild(clean_db, 100, joined_at=JOIN)
    await guild_chest_repo.deposit(100, 1_000_000, REASON_WEEKLY_PERSONAL_DECAY)
    interaction = _FakeInteraction(guild_id=100, member_count=500)

    await cog.chest_sblocca_premium.callback(cog, interaction, tier=1)

    assert "sbloccato" in interaction.response.sent_messages[0]
    assert await guild_chest_repo.get_balance(100) == 500_000


@pytest.mark.asyncio
async def test_sblocca_premium_guild_non_configurata(cog):
    interaction = _FakeInteraction(guild_id=999)

    await cog.chest_sblocca_premium.callback(cog, interaction, tier=1)

    assert "Configurazione del server non trovata" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_saldo_fuori_da_un_server_avvisa(cog):
    interaction = _FakeInteraction(guild_id=None)

    await cog.chest_saldo.callback(cog, interaction)

    assert "solo dentro un server" in interaction.response.sent_messages[0]
