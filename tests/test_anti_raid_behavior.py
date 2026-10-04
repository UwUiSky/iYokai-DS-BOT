"""
tests/test_anti_raid_behavior.py
====================================
Test di integrazione reale di AntiRaidCog.on_member_join() (SPEC.md
§7.1) — stesso schema di tests/test_automod_advanced_behavior.py:
oggetti discord.py fittizi contro un database Postgres reale.
"""

from datetime import datetime, timedelta, timezone

import discord
import pytest

import cogs.security.anti_raid as anti_raid_module
from cogs.security.anti_raid import AntiRaidCog, MODULE_ANTI_RAID
from core.database import Database
from core.repositories.security_repo import SecuritySettings
from core.security_logic import AntiNukeConfig, AntiRaidConfig


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.dm_sent: list = []

    async def send(self, embed=None) -> None:
        self.dm_sent.append(embed)


class _FakeGuild:
    def __init__(self, guild_id: int, owner: _FakeUser) -> None:
        self.id = guild_id
        self.owner = owner
        self.owner_id = owner.id
        self.channels: list = []
        self._ruoli: dict = {}
        self._prossimo_ruolo_id = 5000
        self.edit_calls: list = []

    def get_role(self, role_id: int):
        return self._ruoli.get(role_id)

    def get_channel(self, channel_id: int):
        return None

    async def create_role(self, name: str, reason: str | None = None):
        self._prossimo_ruolo_id += 1
        ruolo = _FakeRole(self._prossimo_ruolo_id, name)
        self._ruoli[ruolo.id] = ruolo
        return ruolo

    async def edit(self, verification_level=None, reason=None) -> None:
        self.edit_calls.append(verification_level)


class _FakeRole:
    def __init__(self, role_id: int, name: str) -> None:
        self.id = role_id
        self.name = name


class _FakeMember(discord.Member):
    def __init__(
        self,
        user_id: int,
        guild: _FakeGuild,
        created_at: datetime,
        has_avatar: bool = True,
        username: str = "MembroNormale",
        bot: bool = False,
    ) -> None:
        self._bot_finto = bot
        self._id_finto = user_id
        self._guild_finta = guild
        self._created_at_finto = created_at
        self._has_avatar = has_avatar
        self._username_finto = username
        self.added_roles: list = []

    @property
    def id(self):
        return self._id_finto

    @property
    def guild(self):
        return self._guild_finta

    @property
    def bot(self):
        return self._bot_finto

    @property
    def created_at(self):
        return self._created_at_finto

    @property
    def avatar(self):
        return object() if self._has_avatar else None

    @property
    def name(self):
        return self._username_finto

    def __str__(self) -> str:
        return self._username_finto

    async def add_roles(self, role, reason=None) -> None:
        self.added_roles.append(role)


GUILD_ID = 700000300


@pytest.fixture
async def contesto(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM security_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM security_action_log WHERE guild_id = $1", GUILD_ID)

    await database.set_module_active_for_guild(GUILD_ID, MODULE_ANTI_RAID, True)

    monkeypatch.setattr(anti_raid_module, "db", database)

    # security_rate_tracker è un singleton di modulo: senza sostituirlo
    # con un'istanza vuota, il conteggio join di un test precedente
    # sullo stesso GUILD_ID si accumulerebbe qui (stesso fix di
    # tests/test_anti_nuke_behavior.py).
    from core.automod_rate_tracker import AutomodRateTracker

    monkeypatch.setattr(anti_raid_module, "security_rate_tracker", AutomodRateTracker())

    from core.repositories.security_repo import security_repo

    original_provider = security_repo._pool_provider
    security_repo._pool_provider = lambda: database.pool

    yield database

    security_repo._pool_provider = original_provider
    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM security_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM security_action_log WHERE guild_id = $1", GUILD_ID)
    await database.close()


async def _salva_config(anti_raid: AntiRaidConfig) -> None:
    from core.repositories.security_repo import security_repo

    await security_repo.save_settings(
        SecuritySettings(
            guild_id=GUILD_ID,
            anti_raid=anti_raid,
            anti_nuke=AntiNukeConfig(),
            quarantine_role_id=None,
            alert_channel_id=None,
        )
    )


@pytest.mark.asyncio
async def test_modulo_disattivato_non_valuta_nulla(contesto):
    await contesto.set_module_active_for_guild(GUILD_ID, MODULE_ANTI_RAID, False)
    await _salva_config(AntiRaidConfig(enabled=True, min_account_age_seconds=999999))

    owner = _FakeUser(1)
    guild = _FakeGuild(GUILD_ID, owner)
    membro = _FakeMember(2, guild, created_at=datetime.now(timezone.utc))

    cog = AntiRaidCog(bot=None)
    await cog.on_member_join(membro)

    assert membro.added_roles == []


@pytest.mark.asyncio
async def test_account_troppo_nuovo_scatena_quarantena_e_alert(contesto):
    await _salva_config(AntiRaidConfig(enabled=True, min_account_age_seconds=86400, lockdown_action="quarantine"))

    owner = _FakeUser(1)
    guild = _FakeGuild(GUILD_ID, owner)
    membro = _FakeMember(2, guild, created_at=datetime.now(timezone.utc) - timedelta(minutes=1))

    cog = AntiRaidCog(bot=None)
    await cog.on_member_join(membro)

    assert len(membro.added_roles) == 1
    assert len(owner.dm_sent) == 1

    from core.repositories.security_repo import security_repo

    recenti = await security_repo.get_recent_actions(GUILD_ID)
    assert len(recenti) == 1
    assert recenti[0]["category"] == "raid_join"


@pytest.mark.asyncio
async def test_lockdown_action_verification_innalza_il_livello(contesto):
    await _salva_config(AntiRaidConfig(enabled=True, min_account_age_seconds=86400, lockdown_action="verification"))

    owner = _FakeUser(1)
    guild = _FakeGuild(GUILD_ID, owner)
    membro = _FakeMember(2, guild, created_at=datetime.now(timezone.utc) - timedelta(minutes=1))

    cog = AntiRaidCog(bot=None)
    await cog.on_member_join(membro)

    assert membro.added_roles == []  # nessuna quarantena, solo verification
    assert guild.edit_calls == [discord.VerificationLevel.highest]


@pytest.mark.asyncio
async def test_join_normale_nessuna_azione(contesto):
    await _salva_config(AntiRaidConfig(enabled=True, min_account_age_seconds=86400))

    owner = _FakeUser(1)
    guild = _FakeGuild(GUILD_ID, owner)
    membro = _FakeMember(2, guild, created_at=datetime.now(timezone.utc) - timedelta(days=365))

    cog = AntiRaidCog(bot=None)
    await cog.on_member_join(membro)

    assert membro.added_roles == []
    assert owner.dm_sent == []


@pytest.mark.asyncio
async def test_username_sospetto_scatena_azione(contesto):
    await _salva_config(AntiRaidConfig(enabled=True, min_account_age_seconds=1, check_username_pattern=True))

    owner = _FakeUser(1)
    guild = _FakeGuild(GUILD_ID, owner)
    membro = _FakeMember(
        2, guild, created_at=datetime.now(timezone.utc) - timedelta(days=365), username="asjdk48213"
    )

    cog = AntiRaidCog(bot=None)
    await cog.on_member_join(membro)

    assert len(membro.added_roles) == 1


@pytest.mark.asyncio
async def test_un_bot_aggiunto_da_un_admin_non_viene_valutato(contesto):
    """
    LC-6: un bot entra solo se un amministratore lo invita. Anche se
    l'applicazione è appena nata, non va messo in quarantena.
    """
    await _salva_config(AntiRaidConfig(enabled=True, min_account_age_seconds=86400))

    owner = _FakeUser(1)
    guild = _FakeGuild(GUILD_ID, owner)
    bot_nuovo = _FakeMember(2, guild, created_at=datetime.now(timezone.utc), bot=True)

    cog = AntiRaidCog(bot=None)
    await cog.on_member_join(bot_nuovo)

    assert bot_nuovo.added_roles == []
    assert owner.dm_sent == []

    from core.repositories.security_repo import security_repo

    assert await security_repo.get_recent_actions(GUILD_ID) == []


@pytest.mark.asyncio
async def test_gli_ingressi_dei_bot_non_entrano_nel_conteggio_del_raid(contesto):
    """Due bot aggiunti di fila non fanno sembrare un raid l'ingresso di una persona."""
    await _salva_config(
        AntiRaidConfig(enabled=True, join_rate_max=2, min_account_age_seconds=0)
    )

    owner = _FakeUser(1)
    guild = _FakeGuild(GUILD_ID, owner)
    vecchio = datetime.now(timezone.utc) - timedelta(days=365)
    cog = AntiRaidCog(bot=None)

    for numero in (10, 11, 12):
        await cog.on_member_join(_FakeMember(numero, guild, created_at=vecchio, bot=True))
    persona = _FakeMember(20, guild, created_at=vecchio)
    await cog.on_member_join(persona)

    assert persona.added_roles == []
    assert owner.dm_sent == []
