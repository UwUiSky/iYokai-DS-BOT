"""
tests/test_backup_orchestrator.py
=====================================
Test di core/backup_orchestrator.py. Le funzioni di clonazione sono
già testate a fondo altrove (tests/test_backup_clone_*.py) — qui si
verifica solo l'ORCHESTRAZIONE: che create_guild venga chiamato con
il nome giusto, che l'URL di invito abbia la forma corretta, che la
finalizzazione trasferisca la proprietà e faccia uscire Creator solo
quando il guild è davvero atteso da un job.
"""

import discord
import pytest

from core.backup_orchestrator import finalize_backup_job, start_backup_job
from core.repositories.backup_repo import BackupRepository
from core.database import Database


class _FakeSourceGuildCompleta:
    """Un server sorgente con TUTTE le collezioni vuote — sufficiente
    per far scorrere le funzioni di clonazione senza sollevare, dato
    che quelle funzioni sono già testate a fondo altrove con dati
    veri; qui serve solo che l'orchestrazione le chiami tutte."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.roles = []
        self.categories = []
        self.channels = []
        self.emojis = []
        self.stickers = []
        self.soundboard_sounds = []
        self.default_role = _FakeRoleMinimo()

    async def webhooks(self):
        return []


class _FakeCreatedGuild:
    def __init__(self, guild_id: int, name: str) -> None:
        self.id = guild_id
        self.name = name
        self.default_role = _FakeRoleMinimo()

    def get_role(self, role_id: int):
        return None


class _FakeRoleMinimo:
    def __init__(self, role_id: int = 0) -> None:
        self.id = role_id
        self.permissions = discord.Permissions.none()

    async def edit(self, **kwargs) -> None:
        pass


class _FakeCreatorClient:
    def __init__(self, guild_creato: _FakeCreatedGuild) -> None:
        self._guild_creato = guild_creato
        self.chiamate_create_guild: list[dict] = []
        self._guilds_disponibili: dict[int, "_FakeCreatorSideGuild"] = {}

    async def create_guild(self, **kwargs) -> _FakeCreatedGuild:
        self.chiamate_create_guild.append(kwargs)
        return self._guild_creato

    def get_guild(self, guild_id: int):
        return self._guilds_disponibili.get(guild_id)


class _FakeCreatorSideGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id
        self.chiamate_edit: list[dict] = []
        self.leave_chiamato = False

    async def edit(self, **kwargs) -> None:
        self.chiamate_edit.append(kwargs)

    async def leave(self) -> None:
        self.leave_chiamato = True


class _FakeJoinedGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id
        self.me = object()  # rappresenta il bot Main stesso in questo server


@pytest.mark.asyncio
async def test_start_backup_job_crea_il_server_con_il_nome_giusto():
    source = _FakeSourceGuildCompleta(name="Il Mio Server")
    creato = _FakeCreatedGuild(guild_id=555, name="Backup di Il Mio Server")
    creator = _FakeCreatorClient(creato)

    nuovo_server, _url = await start_backup_job(
        creator, source, main_client_id=999, main_permissions=discord.Permissions.none()
    )

    assert creator.chiamate_create_guild[0]["name"] == "Backup di Il Mio Server"
    assert nuovo_server is creato


@pytest.mark.asyncio
async def test_start_backup_job_restituisce_un_url_di_invito_valido():
    source = _FakeSourceGuildCompleta(name="Test")
    creato = _FakeCreatedGuild(guild_id=555, name="Backup di Test")
    creator = _FakeCreatorClient(creato)

    _server, url = await start_backup_job(
        creator, source, main_client_id=123456, main_permissions=discord.Permissions(administrator=True)
    )

    assert "client_id=123456" in url
    assert "guild_id=555" in url
    assert "disable_guild_select=true" in url
    assert url.startswith("https://discord.com/oauth2/authorize")


@pytest.mark.asyncio
async def test_finalize_backup_job_trasferisce_proprieta_e_fa_uscire_creator(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        repo = BackupRepository(pool_provider=lambda: database.pool)

        job_id = await repo.enqueue_job(main_guild_id=100)
        await repo.mark_running(job_id)
        await repo.set_backup_guild_id(job_id, backup_guild_id=555)

        joined_guild = _FakeJoinedGuild(guild_id=555)
        creato_lato_creator = _FakeCreatorSideGuild(guild_id=555)
        creator = _FakeCreatorClient(_FakeCreatedGuild(0, ""))
        creator._guilds_disponibili[555] = creato_lato_creator

        risultato = await finalize_backup_job(joined_guild, creator, repo)

        assert risultato is True
        assert creato_lato_creator.chiamate_edit[0]["owner"] is joined_guild.me
        assert creato_lato_creator.leave_chiamato is True

        job = await repo.get_job(job_id)
        assert job.status == "completed"
    finally:
        await database.pool.execute("DELETE FROM backup_jobs")
        await database.close()


@pytest.mark.asyncio
async def test_finalize_backup_job_ignora_un_guild_non_atteso():
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        repo = BackupRepository(pool_provider=lambda: database.pool)

        joined_guild = _FakeJoinedGuild(guild_id=999999)  # nessun job lo aspetta
        creator = _FakeCreatorClient(_FakeCreatedGuild(0, ""))

        risultato = await finalize_backup_job(joined_guild, creator, repo)

        assert risultato is False
    finally:
        await database.close()
