"""
tests/test_level_roles_behavior.py
======================================
Test del comportamento REALE di /level-roles add|remove|list —
contro PostgreSQL vero.
"""

import pytest

from cogs.leveling.leveling import LevelingCog
from core.database import Database
from tests.support.discord_fakes import fake_guild, fake_member, fake_role
from tests.support.moduli import attiva_livelli, togli_configurazione


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


class _FakeRole:
    def __init__(self, role_id: int) -> None:
        self.id = role_id
        self.mention = f"<@&{role_id}>"


class _FakeInteraction:
    def __init__(self, guild_id: int | None, user=None) -> None:
        self.guild = _FakeGuild(guild_id) if guild_id is not None else None
        # Un'interazione vera ha sempre un utente: le liste a pagine ne leggono l'ID.
        self.user = user if user is not None else fake_member(1)
        self.response = _FakeResponse()


def _guild_e_admin_per_check_role_assignable(guild_id: int):
    """
    Serve solo per /level-roles add, che ora chiama
    core.role_safety.check_role_assignable (SEC-4/SEC-17): a
    differenza di _FakeGuild/_FakeRole sopra (usate dagli altri test
    di questo file, che non toccano quel controllo), qui serve un
    guild/ruolo/admin fedeli — vedi tests/support/discord_fakes.py.
    """
    bot_member = fake_member(user_id=999, name="Yokai Bot", bot=True)
    ruolo_bot = fake_role(role_id=1000, name="Yokai Bot", position=50)
    bot_member.top_role = ruolo_bot

    ruolo_admin = fake_role(role_id=2000, name="Admin", position=30)
    admin = fake_member(user_id=1, name="admin", roles=[ruolo_admin])
    admin.top_role = ruolo_admin

    server = fake_guild(guild_id=guild_id, me=bot_member)
    return server, admin


@pytest.fixture
async def cog_e_database(monkeypatch):
    import cogs.leveling.leveling as leveling_module
    from core.repositories.level_reward_repo import LevelRewardRepository

    database = Database()
    await database.connect()
    await database.run_migrations()

    repo = LevelRewardRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(leveling_module, "level_reward_repo", repo)

    await attiva_livelli(monkeypatch, database.pool, 100)

    cog = LevelingCog(bot=None)
    cog.cog_unload()  # ferma subito il task periodico avviato nel costruttore

    yield cog, repo
    await togli_configurazione(database.pool, 100)
    await database.pool.execute("DELETE FROM level_reward_roles")
    await database.close()


@pytest.mark.asyncio
async def test_add_e_list(cog_e_database):
    cog, repo = cog_e_database
    server, admin = _guild_e_admin_per_check_role_assignable(100)
    interaction_add = _FakeInteraction(guild_id=100, user=admin)
    interaction_add.guild = server
    ruolo_premio = fake_role(role_id=555, name="Premio", position=1)

    await cog.level_roles_add.callback(cog, interaction_add, level=10, role=ruolo_premio)

    assert "livello **10**" in interaction_add.response.sent_messages[0]

    interaction_list = _FakeInteraction(guild_id=100)
    await cog.level_roles_list.callback(cog, interaction_list)

    assert "livello **10**" in interaction_list.response.sent_embeds[0].description


@pytest.mark.asyncio
async def test_list_vuota(cog_e_database):
    cog, repo = cog_e_database
    interaction = _FakeInteraction(guild_id=100)

    await cog.level_roles_list.callback(cog, interaction)

    assert "Nessun ruolo-premio" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_remove(cog_e_database):
    cog, repo = cog_e_database
    reward_id = await repo.add_reward(100, level_threshold=5, role_id=1)

    interaction = _FakeInteraction(guild_id=100)
    await cog.level_roles_remove.callback(cog, interaction, reward_id=reward_id)

    assert "rimosso" in interaction.response.sent_messages[0].lower()
    assert await repo.list_rewards(100) == []


@pytest.mark.asyncio
async def test_remove_inesistente_avvisa(cog_e_database):
    cog, repo = cog_e_database
    interaction = _FakeInteraction(guild_id=100)

    await cog.level_roles_remove.callback(cog, interaction, reward_id=99999)

    assert "Nessun ruolo-premio trovato" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_add_fuori_da_un_server_rifiuta(cog_e_database):
    cog, repo = cog_e_database
    interaction = _FakeInteraction(guild_id=None)

    await cog.level_roles_add.callback(cog, interaction, level=5, role=_FakeRole(1))

    assert "solo dentro un server" in interaction.response.sent_messages[0]


# ----------------------------------------------------------------------
# /monthly-winners (SPEC.md §15.11) — stesso cog, stessa fixture
# ----------------------------------------------------------------------
class _FakeTextChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self.mention = f"<#{channel_id}>"


@pytest.fixture
async def cog_e_winners_repo(monkeypatch):
    import cogs.leveling.leveling as leveling_module
    from core.repositories.monthly_winners_repo import MonthlyWinnersRepository

    database = Database()
    await database.connect()
    await database.run_migrations()

    repo = MonthlyWinnersRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(leveling_module, "monthly_winners_repo", repo)

    await attiva_livelli(monkeypatch, database.pool, 100)

    cog = LevelingCog(bot=None)
    cog.cog_unload()

    yield cog, repo
    await togli_configurazione(database.pool, 100)
    await database.pool.execute("DELETE FROM monthly_winners_config")
    await database.close()


@pytest.mark.asyncio
async def test_monthly_winners_set_segna_il_mese_precedente_come_coperto(cog_e_winners_repo):
    from core.monthly_winners_logic import previous_period_key

    cog, repo = cog_e_winners_repo
    interaction = _FakeInteraction(guild_id=100)

    await cog.monthly_winners_set.callback(cog, interaction, channel=_FakeTextChannel(500))

    config = await repo.get_config(100)
    assert config.channel_id == 500
    assert config.last_announced_period == previous_period_key()
    assert "prossimo cambio mese" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_monthly_winners_disable(cog_e_winners_repo):
    cog, repo = cog_e_winners_repo
    await repo.set_channel(100, channel_id=500, already_covered_period="2026-08")

    interaction = _FakeInteraction(guild_id=100)
    await cog.monthly_winners_disable.callback(cog, interaction)

    assert "disattivato" in interaction.response.sent_messages[0]
    assert await repo.get_config(100) is None


@pytest.mark.asyncio
async def test_monthly_winners_disable_senza_configurazione_avvisa(cog_e_winners_repo):
    cog, repo = cog_e_winners_repo
    interaction = _FakeInteraction(guild_id=100)

    await cog.monthly_winners_disable.callback(cog, interaction)

    assert "non era attivo" in interaction.response.sent_messages[0]


# ----------------------------------------------------------------------
# /clan bacheca set|disable (SPEC.md §15.10, top 3 gilde mensile) —
# stesso cog, stesso schema di /monthly-winners sopra
# ----------------------------------------------------------------------
@pytest.fixture
async def cog_e_bacheca_repo(monkeypatch):
    import cogs.leveling.leveling as leveling_module
    from core.repositories.clan_leaderboard_config_repo import (
        ClanLeaderboardConfigRepository,
    )

    database = Database()
    await database.connect()
    await database.run_migrations()

    repo = ClanLeaderboardConfigRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(leveling_module, "clan_leaderboard_config_repo", repo)

    await attiva_livelli(monkeypatch, database.pool, 100)

    cog = LevelingCog(bot=None)
    cog.cog_unload()

    yield cog, repo
    await togli_configurazione(database.pool, 100)
    await database.pool.execute("DELETE FROM clan_leaderboard_config")
    await database.close()


@pytest.mark.asyncio
async def test_clan_bacheca_set_segna_il_mese_precedente_come_coperto(cog_e_bacheca_repo):
    from core.clan_leaderboard_logic import previous_period_key

    cog, repo = cog_e_bacheca_repo
    interaction = _FakeInteraction(guild_id=100)

    await cog.clan_bacheca_set.callback(cog, interaction, channel=_FakeTextChannel(500))

    config = await repo.get_config(100)
    assert config.channel_id == 500
    assert config.last_announced_period == previous_period_key()
    assert "prossimo cambio mese" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_clan_bacheca_disable(cog_e_bacheca_repo):
    cog, repo = cog_e_bacheca_repo
    await repo.set_channel(100, channel_id=500, already_covered_period="2026-08")

    interaction = _FakeInteraction(guild_id=100)
    await cog.clan_bacheca_disable.callback(cog, interaction)

    assert "disattivato" in interaction.response.sent_messages[0]
    assert await repo.get_config(100) is None


@pytest.mark.asyncio
async def test_clan_bacheca_disable_senza_configurazione_avvisa(cog_e_bacheca_repo):
    cog, repo = cog_e_bacheca_repo
    interaction = _FakeInteraction(guild_id=100)

    await cog.clan_bacheca_disable.callback(cog, interaction)

    assert "non era attivo" in interaction.response.sent_messages[0]
