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
from core.repositories.leveling_repo import leveling_repo

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

    async def defer(self, ephemeral: bool = False) -> None:
        pass


class _FakeFollowup:
    """Dopo un defer() le risposte passano da qui: stessa lista dei messaggi."""

    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def send(self, content: str = None, embed=None, ephemeral: bool = False) -> None:
        await self._response.send_message(content, embed=embed, ephemeral=ephemeral)


class _FakeVoiceMember:
    def __init__(self, member_id: int, bot: bool = False) -> None:
        self.id = member_id
        self.bot = bot

    @property
    def mention(self):
        return f"<@{self.id}>"


class _FakeVoiceChannel:
    def __init__(self, members: list) -> None:
        self.members = members


class _FakeGuild:
    def __init__(self, guild_id: int, member_count: int = 500, voice_channels: list | None = None) -> None:
        self.id = guild_id
        self.member_count = member_count
        self.voice_channels = voice_channels or []


class _FakeInteraction:
    def __init__(
        self, guild_id: int | None, member_count: int = 500, voice_channels: list | None = None,
    ) -> None:
        self.guild = (
            _FakeGuild(guild_id, member_count, voice_channels) if guild_id is not None else None
        )
        self.user = None
        self.response = _FakeResponse()
        self.followup = _FakeFollowup(self.response)


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


# ======================================================================
# assegna-lobby / assegna-winner — premi evento dalla cassa di server
# (SPEC.md §15.15)
# ======================================================================

@pytest.mark.asyncio
async def test_assegna_lobby_premia_tutti_i_presenti_in_vocale(cog):
    await guild_chest_repo.deposit(100, 10_000, REASON_WEEKLY_PERSONAL_DECAY)
    canale = _FakeVoiceChannel([_FakeVoiceMember(1), _FakeVoiceMember(2)])
    interaction = _FakeInteraction(guild_id=100, voice_channels=[canale])

    await cog.assegna_lobby.callback(cog, interaction, importo=100)

    assert "Assegnate" in interaction.response.sent_messages[0]
    assert (await leveling_repo.get_totals(100, 1)).coins_total == 100
    assert (await leveling_repo.get_totals(100, 2)).coins_total == 100
    assert await guild_chest_repo.get_balance(100) == 10_000 - 200


@pytest.mark.asyncio
async def test_assegna_lobby_ignora_i_bot(cog):
    await guild_chest_repo.deposit(100, 10_000, REASON_WEEKLY_PERSONAL_DECAY)
    canale = _FakeVoiceChannel([_FakeVoiceMember(1), _FakeVoiceMember(99, bot=True)])
    interaction = _FakeInteraction(guild_id=100, voice_channels=[canale])

    await cog.assegna_lobby.callback(cog, interaction, importo=100)

    assert "1** persone" in interaction.response.sent_messages[0]
    assert (await leveling_repo.get_totals(100, 99)).coins_total == 0


@pytest.mark.asyncio
async def test_assegna_lobby_nessuno_in_vocale_avvisa(cog):
    interaction = _FakeInteraction(guild_id=100, voice_channels=[])

    await cog.assegna_lobby.callback(cog, interaction, importo=100)

    assert "Nessuno è in vocale" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_assegna_lobby_cassa_insufficiente_non_assegna_nulla(cog):
    await guild_chest_repo.deposit(100, 50, REASON_WEEKLY_PERSONAL_DECAY)
    canale = _FakeVoiceChannel([_FakeVoiceMember(1), _FakeVoiceMember(2)])
    interaction = _FakeInteraction(guild_id=100, voice_channels=[canale])

    await cog.assegna_lobby.callback(cog, interaction, importo=100)

    assert "non basta" in interaction.response.sent_messages[0]
    assert (await leveling_repo.get_totals(100, 1)).coins_total == 0
    assert await guild_chest_repo.get_balance(100) == 50


@pytest.mark.asyncio
async def test_assegna_winner_premia_il_vincitore(cog):
    await guild_chest_repo.deposit(100, 10_000, REASON_WEEKLY_PERSONAL_DECAY)
    vincitore = _FakeVoiceMember(1)
    interaction = _FakeInteraction(guild_id=100)

    await cog.assegna_winner.callback(cog, interaction, membro=vincitore, importo=5_000)

    assert "vinto" in interaction.response.sent_messages[0]
    assert (await leveling_repo.get_totals(100, 1)).coins_total == 5_000
    assert await guild_chest_repo.get_balance(100) == 5_000


@pytest.mark.asyncio
async def test_assegna_winner_cassa_insufficiente_non_assegna_nulla(cog):
    await guild_chest_repo.deposit(100, 1_000, REASON_WEEKLY_PERSONAL_DECAY)
    vincitore = _FakeVoiceMember(1)
    interaction = _FakeInteraction(guild_id=100)

    await cog.assegna_winner.callback(cog, interaction, membro=vincitore, importo=5_000)

    assert "non basta" in interaction.response.sent_messages[0]
    assert (await leveling_repo.get_totals(100, 1)).coins_total == 0


@pytest.mark.asyncio
async def test_assegna_lobby_fuori_da_un_server_avvisa(cog):
    interaction = _FakeInteraction(guild_id=None)

    await cog.assegna_lobby.callback(cog, interaction, importo=100)

    assert "solo dentro un server" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_assegna_winner_fuori_da_un_server_avvisa(cog):
    interaction = _FakeInteraction(guild_id=None)

    await cog.assegna_winner.callback(cog, interaction, membro=_FakeVoiceMember(1), importo=100)

    assert "solo dentro un server" in interaction.response.sent_messages[0]
