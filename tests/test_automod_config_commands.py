"""
tests/test_automod_config_commands.py
=========================================
Test dei comandi di configurazione dei filtri avanzati (SPEC.md
§6.3-§6.14) — comportamento reale dei callback, non solo smoke test
di caricamento (già in tests/test_automod_cog_smoke.py).
"""

import pytest

from cogs.automod.automod import AutomodCog, MODULE_AUTOMOD
from core.database import Database


class _FakeChoice:
    def __init__(self, name: str, value: str) -> None:
        self.name = name
        self.value = value


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    async def send_message(self, content=None, embed=None, ephemeral: bool = False) -> None:
        self.sent_messages.append(content if content is not None else "")


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeTextChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self.mention = f"<#{channel_id}>"


class _FakeRole:
    def __init__(self, role_id: int) -> None:
        self.id = role_id
        self.mention = f"<@&{role_id}>"


class _FakeInteraction:
    def __init__(self, guild_id: int, user_id: int = 1) -> None:
        self.user = _FakeUser(user_id)
        self.guild = _FakeGuild(guild_id)
        self.response = _FakeResponse()


GUILD_ID = 700000200


@pytest.fixture
async def cog(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM automod_advanced_config WHERE guild_id = $1", GUILD_ID)
    await database.set_module_active_for_guild(GUILD_ID, MODULE_AUTOMOD, True)

    import cogs.automod.automod as automod_module

    monkeypatch.setattr(automod_module, "db", database)

    # ensure_module_enabled (cogs.moderation._shared) importa "db" per
    # conto proprio, legato al singleton reale — stesso fix già usato
    # in tests/test_automod_advanced_behavior.py.
    from core.database import db as real_db_singleton

    original_pool = real_db_singleton._pool
    real_db_singleton._pool = database.pool

    from core.repositories.automod_advanced_repo import automod_advanced_repo

    original_provider = automod_advanced_repo._pool_provider
    automod_advanced_repo._pool_provider = lambda: database.pool

    yield AutomodCog(bot=None)

    automod_advanced_repo._pool_provider = original_provider
    real_db_singleton._pool = original_pool
    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", GUILD_ID)
    await database.pool.execute("DELETE FROM automod_advanced_config WHERE guild_id = $1", GUILD_ID)
    await database.close()


@pytest.mark.asyncio
async def test_anti_link_mode_imposta_la_modalita(cog):
    interaction = _FakeInteraction(GUILD_ID)

    await cog.anti_link_mode.callback(cog, interaction, mode=_FakeChoice("Blacklist", "blacklist"))

    from core.repositories.automod_advanced_repo import automod_advanced_repo

    settings = await automod_advanced_repo.get_settings(GUILD_ID)
    assert settings.config.anti_link.mode == "blacklist"


@pytest.mark.asyncio
async def test_anti_link_domain_add_e_remove(cog):
    from core.repositories.automod_advanced_repo import automod_advanced_repo

    await cog.anti_link_domain.callback(
        cog,
        _FakeInteraction(GUILD_ID),
        action=_FakeChoice("Aggiungi", "add"),
        lista=_FakeChoice("Blacklist", "blacklist"),
        domain="Cattivo.COM",
    )
    settings = await automod_advanced_repo.get_settings(GUILD_ID)
    assert settings.config.anti_link.blacklist == ("cattivo.com",)

    await cog.anti_link_domain.callback(
        cog,
        _FakeInteraction(GUILD_ID),
        action=_FakeChoice("Rimuovi", "remove"),
        lista=_FakeChoice("Blacklist", "blacklist"),
        domain="cattivo.com",
    )
    settings = await automod_advanced_repo.get_settings(GUILD_ID)
    assert settings.config.anti_link.blacklist == ()


@pytest.mark.asyncio
async def test_actions_set_salva_le_azioni_scelte(cog):
    from core.repositories.automod_advanced_repo import automod_advanced_repo

    await cog.actions_set.callback(
        cog,
        _FakeInteraction(GUILD_ID),
        violation=_FakeChoice("Anti-Caps", "anti_caps"),
        delete=True,
        warn=True,
        mute=False,
        ban=False,
    )

    settings = await automod_advanced_repo.get_settings(GUILD_ID)
    assert settings.actions["anti_caps"] == ("delete", "warn")


@pytest.mark.asyncio
async def test_mute_duration_rifiuta_valore_fuori_limite(cog):
    interaction = _FakeInteraction(GUILD_ID)

    await cog.mute_duration.callback(cog, interaction, seconds=999_999_999)

    assert "28 giorni" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_mute_duration_accetta_valore_valido(cog):
    from core.repositories.automod_advanced_repo import automod_advanced_repo

    await cog.mute_duration.callback(cog, _FakeInteraction(GUILD_ID), seconds=300)

    settings = await automod_advanced_repo.get_settings(GUILD_ID)
    assert settings.mute_duration_seconds == 300


@pytest.mark.asyncio
async def test_exempt_channel_add_e_remove(cog):
    from core.repositories.automod_advanced_repo import automod_advanced_repo

    canale = _FakeTextChannel(555)
    await cog.exempt_channel_add.callback(cog, _FakeInteraction(GUILD_ID), channel=canale)
    settings = await automod_advanced_repo.get_settings(GUILD_ID)
    assert settings.exempt_channel_ids == (555,)

    await cog.exempt_channel_remove.callback(cog, _FakeInteraction(GUILD_ID), channel=canale)
    settings = await automod_advanced_repo.get_settings(GUILD_ID)
    assert settings.exempt_channel_ids == ()


@pytest.mark.asyncio
async def test_exempt_role_add_e_remove(cog):
    from core.repositories.automod_advanced_repo import automod_advanced_repo

    ruolo = _FakeRole(777)
    await cog.exempt_role_add.callback(cog, _FakeInteraction(GUILD_ID), role=ruolo)
    settings = await automod_advanced_repo.get_settings(GUILD_ID)
    assert settings.exempt_role_ids == (777,)

    await cog.exempt_role_remove.callback(cog, _FakeInteraction(GUILD_ID), role=ruolo)
    settings = await automod_advanced_repo.get_settings(GUILD_ID)
    assert settings.exempt_role_ids == ()


@pytest.mark.asyncio
async def test_status_mostra_un_riepilogo(cog):
    interaction = _FakeInteraction(GUILD_ID)

    await cog.status.callback(cog, interaction)

    assert "Anti-Link" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_anti_caps_configura_soglia_e_lunghezza(cog):
    from core.repositories.automod_advanced_repo import automod_advanced_repo

    await cog.anti_caps.callback(cog, _FakeInteraction(GUILD_ID), enabled=True, percent=80, min_length=15)

    settings = await automod_advanced_repo.get_settings(GUILD_ID)
    assert settings.config.anti_caps.enabled is True
    assert settings.config.anti_caps.threshold_percent == 80
    assert settings.config.anti_caps.min_length == 15


@pytest.mark.asyncio
async def test_log_channel_imposta_il_canale(cog):
    from core.repositories.automod_advanced_repo import automod_advanced_repo

    canale = _FakeTextChannel(888)
    await cog.log_channel.callback(cog, _FakeInteraction(GUILD_ID), channel=canale)

    settings = await automod_advanced_repo.get_settings(GUILD_ID)
    assert settings.log_channel_id == 888
