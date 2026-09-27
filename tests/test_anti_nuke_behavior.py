"""
tests/test_anti_nuke_behavior.py
====================================
Test di integrazione reale del motore Anti-Nuke (SPEC.md §7.2) —
stesso schema di tests/test_anti_raid_behavior.py.
"""

from datetime import datetime, timezone

import discord
import pytest

import cogs.security.anti_nuke as anti_nuke_module
from cogs.security.anti_nuke import AntiNukeCog, MODULE_ANTI_NUKE
from core.database import Database
from core.repositories.security_repo import SecuritySettings
from core.security_logic import AntiNukeConfig, AntiRaidConfig, NUKE_CATEGORY_CHANNEL


class _FakeAuditEntry:
    def __init__(self, user_id: int, target_id: int | None = None, created_at=None) -> None:
        self.user_id = user_id
        self.target = _FakeTarget(target_id) if target_id is not None else None
        self.created_at = created_at or datetime.now(timezone.utc)


class _FakeTarget:
    def __init__(self, target_id: int) -> None:
        self.id = target_id


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.dm_sent: list = []

    async def send(self, embed=None) -> None:
        self.dm_sent.append(embed)


class _FakeMember(discord.Member):
    def __init__(self, member_id: int, guild) -> None:
        self._id_finto = member_id
        self._guild_finta = guild
        self.roles_removed = False
        self.banned = False

    @property
    def id(self):
        return self._id_finto

    @property
    def guild(self):
        return self._guild_finta

    def __str__(self) -> str:
        return f"Membro{self._id_finto}"

    async def edit(self, roles=None, reason=None) -> None:
        self.roles_removed = True

    async def ban(self, reason=None, delete_message_seconds=0) -> None:
        self.banned = True


class _FakeGuild:
    def __init__(self, guild_id: int, owner: _FakeUser, owner_id: int) -> None:
        self.id = guild_id
        self.owner = owner
        self.owner_id = owner_id
        self._members: dict = {}
        self._audit_entries: dict = {}

    def get_member(self, user_id: int):
        return self._members.get(user_id)

    def get_channel(self, channel_id: int):
        return None

    def set_audit_entries(self, action, entries) -> None:
        self._audit_entries[action] = entries

    async def audit_logs(self, action=None, limit=10):
        for entry in self._audit_entries.get(action, []):
            yield entry

    async def create_text_channel(self, name, category=None, overwrites=None, reason=None):
        self.recreated_channel_name = name


GUILD_ID = 700000400
ACTOR_ID = 900001


@pytest.fixture
async def contesto(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM security_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM security_action_log WHERE guild_id = $1", GUILD_ID)

    await database.set_module_active_for_guild(GUILD_ID, MODULE_ANTI_NUKE, True)

    monkeypatch.setattr(anti_nuke_module, "db", database)

    # security_rate_tracker è un singleton di modulo: senza
    # sostituirlo con un'istanza vuota, il conteggio di un test
    # precedente sulla stessa (guild, attore, categoria) farebbe
    # scattare la violazione un turno prima del previsto qui.
    from core.automod_rate_tracker import AutomodRateTracker

    monkeypatch.setattr(anti_nuke_module, "security_rate_tracker", AutomodRateTracker())

    from core.repositories.security_repo import security_repo

    original_provider = security_repo._pool_provider
    security_repo._pool_provider = lambda: database.pool

    yield database

    security_repo._pool_provider = original_provider
    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM security_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM security_action_log WHERE guild_id = $1", GUILD_ID)
    await database.close()


async def _salva_config(anti_nuke: AntiNukeConfig) -> None:
    from core.repositories.security_repo import security_repo

    await security_repo.save_settings(
        SecuritySettings(
            guild_id=GUILD_ID,
            anti_raid=AntiRaidConfig(),
            anti_nuke=anti_nuke,
            quarantine_role_id=None,
            alert_channel_id=None,
        )
    )


@pytest.mark.asyncio
async def test_sotto_soglia_nessuna_azione(contesto):
    await _salva_config(AntiNukeConfig(enabled=True, channel_max=5))
    owner = _FakeUser(1)
    guild = _FakeGuild(GUILD_ID, owner, owner_id=1)
    membro = _FakeMember(ACTOR_ID, guild)
    guild._members[ACTOR_ID] = membro

    cog = AntiNukeCog(bot=None)
    risultato = await cog._handle_event(guild, NUKE_CATEGORY_CHANNEL, ACTOR_ID, "test")

    assert risultato is None
    assert membro.roles_removed is False


@pytest.mark.asyncio
async def test_sopra_soglia_rimuove_i_ruoli_di_default(contesto):
    await _salva_config(AntiNukeConfig(enabled=True, channel_max=1))
    owner = _FakeUser(1)
    guild = _FakeGuild(GUILD_ID, owner, owner_id=1)
    membro = _FakeMember(ACTOR_ID, guild)
    guild._members[ACTOR_ID] = membro

    cog = AntiNukeCog(bot=None)
    await cog._handle_event(guild, NUKE_CATEGORY_CHANNEL, ACTOR_ID, "azione 1")
    await cog._handle_event(guild, NUKE_CATEGORY_CHANNEL, ACTOR_ID, "azione 2")

    assert membro.roles_removed is True
    assert len(owner.dm_sent) == 1

    from core.repositories.security_repo import security_repo

    recenti = await security_repo.get_recent_actions(GUILD_ID)
    assert len(recenti) == 1
    assert recenti[0]["category"] == f"nuke_{NUKE_CATEGORY_CHANNEL}"


@pytest.mark.asyncio
async def test_punish_action_ban(contesto):
    await _salva_config(AntiNukeConfig(enabled=True, channel_max=1, punish_action="ban"))
    owner = _FakeUser(1)
    guild = _FakeGuild(GUILD_ID, owner, owner_id=1)
    membro = _FakeMember(ACTOR_ID, guild)
    guild._members[ACTOR_ID] = membro

    cog = AntiNukeCog(bot=None)
    await cog._handle_event(guild, NUKE_CATEGORY_CHANNEL, ACTOR_ID, "1")
    await cog._handle_event(guild, NUKE_CATEGORY_CHANNEL, ACTOR_ID, "2")

    assert membro.banned is True


@pytest.mark.asyncio
async def test_actor_fidato_non_subisce_nulla(contesto):
    await _salva_config(AntiNukeConfig(enabled=True, channel_max=1, trusted_ids=(ACTOR_ID,)))
    owner = _FakeUser(1)
    guild = _FakeGuild(GUILD_ID, owner, owner_id=1)
    membro = _FakeMember(ACTOR_ID, guild)
    guild._members[ACTOR_ID] = membro

    cog = AntiNukeCog(bot=None)
    await cog._handle_event(guild, NUKE_CATEGORY_CHANNEL, ACTOR_ID, "1")
    await cog._handle_event(guild, NUKE_CATEGORY_CHANNEL, ACTOR_ID, "2")

    assert membro.roles_removed is False
    assert membro.banned is False


@pytest.mark.asyncio
async def test_owner_come_autore_non_subisce_nulla(contesto):
    await _salva_config(AntiNukeConfig(enabled=True, channel_max=1))
    owner = _FakeUser(1)
    guild = _FakeGuild(GUILD_ID, owner, owner_id=1)
    membro_owner = _FakeMember(1, guild)
    guild._members[1] = membro_owner

    cog = AntiNukeCog(bot=None)
    await cog._handle_event(guild, NUKE_CATEGORY_CHANNEL, 1, "1")
    await cog._handle_event(guild, NUKE_CATEGORY_CHANNEL, 1, "2")

    assert membro_owner.roles_removed is False


@pytest.mark.asyncio
async def test_modulo_disattivato_ignora_tutto(contesto):
    await contesto.set_module_active_for_guild(GUILD_ID, MODULE_ANTI_NUKE, False)
    await _salva_config(AntiNukeConfig(enabled=True, channel_max=1))
    owner = _FakeUser(1)
    guild = _FakeGuild(GUILD_ID, owner, owner_id=1)
    membro = _FakeMember(ACTOR_ID, guild)
    guild._members[ACTOR_ID] = membro

    cog = AntiNukeCog(bot=None)
    await cog._handle_event(guild, NUKE_CATEGORY_CHANNEL, ACTOR_ID, "1")
    await cog._handle_event(guild, NUKE_CATEGORY_CHANNEL, ACTOR_ID, "2")

    assert membro.roles_removed is False


@pytest.mark.asyncio
async def test_on_member_remove_ignora_un_leave_volontario(contesto):
    await _salva_config(AntiNukeConfig(enabled=True, ban_kick_max=0))
    owner = _FakeUser(1)
    guild = _FakeGuild(GUILD_ID, owner, owner_id=1)
    guild.set_audit_entries(discord.AuditLogAction.kick, [])  # nessuna voce kick recente
    membro = _FakeMember(500, guild)

    cog = AntiNukeCog(bot=None)
    await cog.on_member_remove(membro)

    from core.repositories.security_repo import security_repo

    recenti = await security_repo.get_recent_actions(GUILD_ID)
    assert recenti == []


@pytest.mark.asyncio
async def test_on_member_remove_rileva_un_kick_reale(contesto):
    await _salva_config(AntiNukeConfig(enabled=True, ban_kick_max=0))
    owner = _FakeUser(1)
    guild = _FakeGuild(GUILD_ID, owner, owner_id=1)
    membro_espulso = _FakeMember(500, guild)
    guild.set_audit_entries(
        discord.AuditLogAction.kick, [_FakeAuditEntry(user_id=ACTOR_ID, target_id=500)]
    )
    guild._members[ACTOR_ID] = _FakeMember(ACTOR_ID, guild)

    cog = AntiNukeCog(bot=None)
    await cog.on_member_remove(membro_espulso)

    from core.repositories.security_repo import security_repo

    recenti = await security_repo.get_recent_actions(GUILD_ID)
    assert len(recenti) == 1
    assert recenti[0]["category"] == "nuke_ban_kick"


@pytest.mark.asyncio
async def test_on_guild_channel_delete_ricrea_il_canale_in_recovery(contesto):
    await _salva_config(AntiNukeConfig(enabled=True, channel_max=0, recovery_enabled=True))
    owner = _FakeUser(1)
    guild = _FakeGuild(GUILD_ID, owner, owner_id=1)
    guild.set_audit_entries(
        discord.AuditLogAction.channel_delete, [_FakeAuditEntry(user_id=ACTOR_ID)]
    )
    guild._members[ACTOR_ID] = _FakeMember(ACTOR_ID, guild)

    class _FakeTextChannel(discord.TextChannel):
        def __init__(self, name, guild):
            self._nome_finto = name
            self._guild_finta = guild

        @property
        def name(self):
            return self._nome_finto

        @property
        def guild(self):
            return self._guild_finta

        @property
        def category(self):
            return None

        @property
        def overwrites(self):
            return {}

    canale = _FakeTextChannel("canale-importante", guild)

    cog = AntiNukeCog(bot=None)
    await cog.on_guild_channel_delete(canale)

    assert getattr(guild, "recreated_channel_name", None) == "canale-importante"
