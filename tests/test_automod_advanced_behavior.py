"""
tests/test_automod_advanced_behavior.py
===========================================
Test di integrazione reale dei filtri AutoMod avanzati (SPEC.md
§6.3-§6.14): AutomodCog.on_message() con oggetti discord.py fittizi
(stesso schema di tests/test_sticky_messages_listener.py) contro un
database Postgres reale.
"""

import discord
import pytest

import cogs.automod.automod as automod_module
from cogs.automod.automod import AutomodCog, MODULE_AUTOMOD
from core.automod_advanced_logic import (
    AntiLinkConfig,
    AutomodAdvancedConfig,
    CapsFilterConfig,
    ThresholdFilterConfig,
)
from core.database import Database
from core.repositories.automod_advanced_repo import AutomodAdvancedSettings


class _FakePermissions:
    def __init__(self, administrator: bool = False, manage_guild: bool = False) -> None:
        self.administrator = administrator
        self.manage_guild = manage_guild


class _FakeRole:
    def __init__(self, role_id: int) -> None:
        self.id = role_id


class _FakeGuild:
    def __init__(self, guild_id: int, owner_id: int = 999999) -> None:
        self.id = guild_id
        self.owner_id = owner_id
        self.me = None

    def get_channel(self, channel_id: int):
        return None


class _FakeMember(discord.Member):
    def __init__(
        self,
        user_id: int,
        guild: _FakeGuild,
        roles: tuple = (),
        is_admin: bool = False,
        is_owner: bool = False,
    ) -> None:
        self._id_finto = user_id
        self._guild_finta = guild if not is_owner else _FakeGuild(guild.id, owner_id=user_id)
        self._ruoli_finti = list(roles)
        self._permessi_finti = _FakePermissions(administrator=is_admin)
        self.timeout_calls: list = []
        self.ban_calls: list = []
        self.dm_sent: list = []

    @property
    def id(self):
        return self._id_finto

    @property
    def bot(self):
        return False

    @property
    def guild(self):
        return self._guild_finta

    @property
    def roles(self):
        return self._ruoli_finti

    @property
    def mention(self):
        return f"<@{self._id_finto}>"

    @property
    def guild_permissions(self):
        return self._permessi_finti

    def __hash__(self) -> int:
        return hash(self._id_finto)

    async def timeout(self, duration, reason=None) -> None:
        self.timeout_calls.append((duration, reason))

    async def ban(self, reason=None, delete_message_seconds=0) -> None:
        self.ban_calls.append(reason)

    async def send(self, embed=None) -> None:
        self.dm_sent.append(embed)


class _FakeTextChannel(discord.TextChannel):
    def __init__(self, channel_id: int) -> None:
        self._id_finto = channel_id
        self.sent: list = []

    @property
    def id(self):
        return self._id_finto

    @property
    def mention(self):
        return f"<#{self._id_finto}>"

    async def send(self, embed=None) -> None:
        self.sent.append(embed)


class _FakeMessage:
    def __init__(
        self,
        guild: _FakeGuild,
        author: _FakeMember,
        channel: _FakeTextChannel,
        content: str = "",
        mentions: tuple = (),
        role_mentions: tuple = (),
        mention_everyone: bool = False,
        attachments: tuple = (),
        stickers: tuple = (),
    ) -> None:
        self.guild = guild
        self.author = author
        self.channel = channel
        self.content = content
        self.mentions = list(mentions)
        self.role_mentions = list(role_mentions)
        self.mention_everyone = mention_everyone
        self.attachments = list(attachments)
        self.stickers = list(stickers)
        self.deleted = False

    async def delete(self) -> None:
        self.deleted = True


GUILD_ID = 700000100


@pytest.fixture
async def contesto(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()

    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM automod_advanced_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM automod_action_log WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM moderation_cases WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM moderation_case_counters WHERE guild_id = $1", GUILD_ID)

    await database.set_module_active_for_guild(GUILD_ID, MODULE_AUTOMOD, True)

    monkeypatch.setattr(automod_module, "db", database)

    # cogs.moderation._shared importa "db" per conto proprio (stesso
    # nome, ma legato al singleton REALE al momento del suo import):
    # patchare automod_module.db sopra non lo tocca. post_to_mod_log
    # (chiamata dall'azione "warn") passa quindi dal singleton vero —
    # gli si presta temporaneamente il pool di test, invece di
    # ri-mockare anche _shared.py.
    from core.database import db as real_db_singleton

    original_pool = real_db_singleton._pool
    real_db_singleton._pool = database.pool

    from core.repositories.automod_advanced_repo import automod_advanced_repo
    from core.repositories.moderation_repo import moderation_repo

    original_advanced_provider = automod_advanced_repo._pool_provider
    original_moderation_provider = moderation_repo._pool_provider
    automod_advanced_repo._pool_provider = lambda: database.pool
    moderation_repo._pool_provider = lambda: database.pool

    yield database

    automod_advanced_repo._pool_provider = original_advanced_provider
    moderation_repo._pool_provider = original_moderation_provider
    real_db_singleton._pool = original_pool
    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM automod_advanced_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM automod_action_log WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM moderation_cases WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM moderation_case_counters WHERE guild_id = $1", GUILD_ID)
    await database.close()


async def _salva_config(database, **overrides) -> None:
    from core.repositories.automod_advanced_repo import automod_advanced_repo

    base = AutomodAdvancedSettings(
        guild_id=GUILD_ID,
        config=AutomodAdvancedConfig(),
        exempt_channel_ids=(),
        exempt_role_ids=(),
        actions={},
        mute_duration_seconds=600,
        log_channel_id=None,
    )
    dati = base.__dict__.copy()
    dati.update(overrides)
    await automod_advanced_repo.save_settings(AutomodAdvancedSettings(**dati))


@pytest.mark.asyncio
async def test_modulo_disattivato_non_valuta_nulla(contesto):
    await contesto.set_module_active_for_guild(GUILD_ID, MODULE_AUTOMOD, False)
    await _salva_config(contesto, config=AutomodAdvancedConfig(anti_zalgo_enabled=True))

    guild = _FakeGuild(GUILD_ID)
    autore = _FakeMember(1, guild)
    canale = _FakeTextChannel(1)
    messaggio = _FakeMessage(guild, autore, canale, content="A" + "́" * 10)

    cog = AutomodCog(bot=None)
    await cog.on_message(messaggio)

    assert messaggio.deleted is False


@pytest.mark.asyncio
async def test_canale_esente_bypassa_tutti_i_filtri(contesto):
    canale_id = 5555
    await _salva_config(
        contesto,
        config=AutomodAdvancedConfig(anti_zalgo_enabled=True),
        exempt_channel_ids=(canale_id,),
    )
    guild = _FakeGuild(GUILD_ID)
    autore = _FakeMember(1, guild)
    canale = _FakeTextChannel(canale_id)
    messaggio = _FakeMessage(guild, autore, canale, content="A" + "́" * 10)

    cog = AutomodCog(bot=None)
    await cog.on_message(messaggio)

    assert messaggio.deleted is False


@pytest.mark.asyncio
async def test_ruolo_esente_bypassa_tutti_i_filtri(contesto):
    ruolo_id = 8888
    await _salva_config(
        contesto,
        config=AutomodAdvancedConfig(anti_zalgo_enabled=True),
        exempt_role_ids=(ruolo_id,),
    )
    guild = _FakeGuild(GUILD_ID)
    autore = _FakeMember(1, guild, roles=(_FakeRole(ruolo_id),))
    canale = _FakeTextChannel(1)
    messaggio = _FakeMessage(guild, autore, canale, content="A" + "́" * 10)

    cog = AutomodCog(bot=None)
    await cog.on_message(messaggio)

    assert messaggio.deleted is False


@pytest.mark.asyncio
async def test_zalgo_cancella_il_messaggio_per_default(contesto):
    await _salva_config(contesto, config=AutomodAdvancedConfig(anti_zalgo_enabled=True))
    guild = _FakeGuild(GUILD_ID)
    autore = _FakeMember(1, guild)
    canale = _FakeTextChannel(1)
    messaggio = _FakeMessage(guild, autore, canale, content="A" + "́" * 10)

    cog = AutomodCog(bot=None)
    await cog.on_message(messaggio)

    assert messaggio.deleted is True

    from core.repositories.automod_advanced_repo import automod_advanced_repo

    recenti = await automod_advanced_repo.get_recent_actions(GUILD_ID)
    assert len(recenti) == 1
    assert recenti[0]["violation"] == "anti_zalgo"
    assert recenti[0]["actions_taken"] == ("delete",)


@pytest.mark.asyncio
async def test_azioni_multiple_delete_e_warn_vengono_eseguite_insieme(contesto):
    await _salva_config(
        contesto,
        config=AutomodAdvancedConfig(anti_zalgo_enabled=True),
        actions={"anti_zalgo": ("delete", "warn")},
    )
    guild = _FakeGuild(GUILD_ID)
    autore = _FakeMember(1, guild)
    canale = _FakeTextChannel(1)
    messaggio = _FakeMessage(guild, autore, canale, content="A" + "́" * 10)

    cog = AutomodCog(bot=None)
    await cog.on_message(messaggio)

    assert messaggio.deleted is True
    assert len(autore.dm_sent) == 1  # il warn manda un DM

    from core.repositories.moderation_repo import moderation_repo

    caso = await moderation_repo.get_case(GUILD_ID, 1)
    assert caso is not None
    assert caso.action_type == "warn"


@pytest.mark.asyncio
async def test_mute_e_ban_non_si_applicano_a_un_admin_protetto(contesto):
    await _salva_config(
        contesto,
        config=AutomodAdvancedConfig(anti_zalgo_enabled=True),
        actions={"anti_zalgo": ("delete", "mute", "ban")},
    )
    guild = _FakeGuild(GUILD_ID)
    autore = _FakeMember(1, guild, is_admin=True)
    canale = _FakeTextChannel(1)
    messaggio = _FakeMessage(guild, autore, canale, content="A" + "́" * 10)

    cog = AutomodCog(bot=None)
    await cog.on_message(messaggio)

    assert messaggio.deleted is True  # delete resta sempre applicato
    assert autore.timeout_calls == []
    assert autore.ban_calls == []


@pytest.mark.asyncio
async def test_mute_si_applica_a_un_membro_normale(contesto):
    await _salva_config(
        contesto,
        config=AutomodAdvancedConfig(anti_zalgo_enabled=True),
        actions={"anti_zalgo": ("mute",)},
        mute_duration_seconds=120,
    )
    guild = _FakeGuild(GUILD_ID)
    autore = _FakeMember(1, guild)
    canale = _FakeTextChannel(1)
    messaggio = _FakeMessage(guild, autore, canale, content="A" + "́" * 10)

    cog = AutomodCog(bot=None)
    await cog.on_message(messaggio)

    assert len(autore.timeout_calls) == 1
    durata, _ = autore.timeout_calls[0]
    assert durata.total_seconds() == 120


@pytest.mark.asyncio
async def test_link_non_in_whitelist_viola(contesto):
    await _salva_config(
        contesto,
        config=AutomodAdvancedConfig(
            anti_link=AntiLinkConfig(mode="whitelist", whitelist=("buono.com",))
        ),
    )
    guild = _FakeGuild(GUILD_ID)
    autore = _FakeMember(1, guild)
    canale = _FakeTextChannel(1)
    messaggio = _FakeMessage(guild, autore, canale, content="vai su https://cattivo.com ora")

    cog = AutomodCog(bot=None)
    await cog.on_message(messaggio)

    assert messaggio.deleted is True


@pytest.mark.asyncio
async def test_mass_mention_oltre_soglia_viola(contesto):
    await _salva_config(
        contesto,
        config=AutomodAdvancedConfig(anti_mass_mention=ThresholdFilterConfig(enabled=True, max_count=2)),
    )
    guild = _FakeGuild(GUILD_ID)
    autore = _FakeMember(1, guild)
    canale = _FakeTextChannel(1)
    messaggio = _FakeMessage(
        guild, autore, canale, content="ping", mentions=(1, 2, 3)
    )

    cog = AutomodCog(bot=None)
    await cog.on_message(messaggio)

    assert messaggio.deleted is True


@pytest.mark.asyncio
async def test_messaggio_pulito_non_scatena_nulla(contesto):
    await _salva_config(
        contesto,
        config=AutomodAdvancedConfig(
            anti_caps=CapsFilterConfig(enabled=True, threshold_percent=70, min_length=5)
        ),
    )
    guild = _FakeGuild(GUILD_ID)
    autore = _FakeMember(1, guild)
    canale = _FakeTextChannel(1)
    messaggio = _FakeMessage(guild, autore, canale, content="Un messaggio normale e pulito")

    cog = AutomodCog(bot=None)
    await cog.on_message(messaggio)

    assert messaggio.deleted is False
    assert autore.timeout_calls == []
    assert autore.ban_calls == []


@pytest.mark.asyncio
async def test_log_channel_riceve_lembed(contesto):
    canale_log = _FakeTextChannel(9999)
    guild = _FakeGuild(GUILD_ID)
    guild.get_channel = lambda cid: canale_log if cid == canale_log.id else None

    await _salva_config(
        contesto,
        config=AutomodAdvancedConfig(anti_zalgo_enabled=True),
        log_channel_id=canale_log.id,
    )
    autore = _FakeMember(1, guild)
    canale = _FakeTextChannel(1)
    messaggio = _FakeMessage(guild, autore, canale, content="A" + "́" * 10)

    cog = AutomodCog(bot=None)
    await cog.on_message(messaggio)

    assert len(canale_log.sent) == 1
