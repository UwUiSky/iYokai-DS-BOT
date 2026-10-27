"""
tests/test_backup_cog_behavior.py
=====================================
Test del comportamento REALE di /define-main e /define-backup —
contro PostgreSQL vero.
"""

import pytest

from cogs.utility.backup import BackupCog
from core.database import Database


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.deferred = False

    async def send_message(self, content: str, ephemeral: bool = False) -> None:
        self.sent_messages.append(content)

    async def defer(self, ephemeral: bool = False) -> None:
        self.deferred = True


class _FakeFollowup:
    def __init__(self, response) -> None:
        self._response = response

    async def send(self, content: str | None = None, embed=None, ephemeral: bool = False) -> None:
        self._response.sent_messages.append(content if content is not None else embed.description)


class _FakeGuild:
    owner_id = 42  # l'utente finto è il proprietario

    def __init__(self, guild_id: int) -> None:
        self.id = guild_id
        self.name = "Server"

    async def templates(self):
        return []


class _FakeUser:
    id = 42

    def __init__(self, admin: bool = True) -> None:
        self.guild_permissions = type("P", (), {"administrator": admin})()


class _FakeInteraction:
    def __init__(self, guild_id: int | None, admin: bool = True) -> None:
        self.guild = _FakeGuild(guild_id) if guild_id is not None else None
        self.user = _FakeUser(admin)
        self.response = _FakeResponse()
        self.followup = _FakeFollowup(self.response)


class _FakeBotUser:
    id = 999


class _FakeCreator:
    user = type("U", (), {"id": 888})()

    def __init__(self, guild_ids=()) -> None:
        self._ids = set(guild_ids)

    def get_guild(self, guild_id):
        return object() if guild_id in self._ids else None


class _FakeMembro:
    def __init__(self, uid):
        self.id = uid
        self.guild_permissions = type("P", (), {"administrator": True})()


class _FakeGuildPrincipale:
    owner_id = 0

    def get_member(self, uid):
        return _FakeMembro(uid)


class _FakeBot:
    user = _FakeBotUser()

    def get_guild(self, guild_id):
        return _FakeGuildPrincipale()

    def __init__(self, creator=None) -> None:
        self.backup_creator_client = creator


@pytest.mark.asyncio
async def test_define_main_registra_il_server(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        import cogs.utility.backup as backup_module
        from core.repositories.backup_repo import BackupRepository

        repo = BackupRepository(pool_provider=lambda: database.pool)
        monkeypatch.setattr(backup_module, "backup_repo", repo)

        cog = BackupCog(bot=None)
        interaction = _FakeInteraction(guild_id=100)

        await cog.define_main.callback(cog, interaction)

        assert "registrato come 'main'" in interaction.response.sent_messages[0]
        coppia = await repo.get_pair(100)
        assert coppia is not None
    finally:
        await database.pool.execute("DELETE FROM backup_pairs")
        await database.close()


@pytest.mark.asyncio
async def test_define_backup_senza_define_main_prima_avvisa(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        import cogs.utility.backup as backup_module
        from core.repositories.backup_repo import BackupRepository

        repo = BackupRepository(pool_provider=lambda: database.pool)
        monkeypatch.setattr(backup_module, "backup_repo", repo)

        cog = BackupCog(bot=None)
        interaction = _FakeInteraction(guild_id=999)

        await cog.define_backup.callback(cog, interaction)

        assert "prima registrare" in interaction.response.sent_messages[0]
    finally:
        await database.close()


async def _repo_con_cog(monkeypatch, database, creator=None):
    import cogs.utility.backup as backup_module
    from core.repositories.backup_repo import BackupRepository

    repo = BackupRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(backup_module, "backup_repo", repo)
    return repo, BackupCog(bot=_FakeBot(creator))


@pytest.mark.asyncio
async def test_crea_dopo_main_da_il_codice_e_i_link_degli_inviti(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        repo, cog = await _repo_con_cog(monkeypatch, database, _FakeCreator())
        await cog.define_main.callback(cog, _FakeInteraction(guild_id=100))

        interaction = _FakeInteraction(guild_id=100)
        await cog.define_backup.callback(cog, interaction)

        testo = interaction.response.sent_messages[0]
        assert "/backup collega" in testo
        assert "client_id=999" in testo and "client_id=888" in testo
        assert await database.pool.fetchval(
            "SELECT count(*) FROM backup_link_codes WHERE main_guild_id = 100"
        ) == 1
        assert await repo.get_next_pending_job() is None  # la copia parte al collegamento
    finally:
        await database.pool.execute("DELETE FROM backup_link_codes WHERE main_guild_id = 100")
        await database.pool.execute("DELETE FROM backup_pairs")
        await database.close()


@pytest.mark.asyncio
async def test_crea_solo_per_amministratori(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        _repo, cog = await _repo_con_cog(monkeypatch, database)
        interaction = _FakeInteraction(guild_id=100, admin=False)

        await cog.define_backup.callback(cog, interaction)

        assert "Amministratore" in interaction.response.sent_messages[0]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_crea_rifiuta_se_c_e_gia_una_copia_attiva(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        repo, cog = await _repo_con_cog(monkeypatch, database, _FakeCreator())
        await cog.define_main.callback(cog, _FakeInteraction(guild_id=100))
        await repo.enqueue_linked_job(100, 200)

        seconda = _FakeInteraction(guild_id=100)
        await cog.define_backup.callback(cog, seconda)

        assert "già" in seconda.response.sent_messages[0]
        assert await database.pool.fetchval(
            "SELECT count(*) FROM backup_link_codes WHERE main_guild_id = 100"
        ) == 0
    finally:
        await database.pool.execute("DELETE FROM backup_pairs")
        await database.pool.execute("DELETE FROM backup_jobs")
        await database.close()


@pytest.mark.asyncio
async def test_collega_con_il_codice_giusto_mette_in_coda_la_copia(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        repo, cog = await _repo_con_cog(monkeypatch, database, _FakeCreator([200]))
        await cog.define_main.callback(cog, _FakeInteraction(guild_id=100))
        from core.backup_link_logic import crea_codice_collegamento

        codice, _ = await crea_codice_collegamento(repo, 100, creato_da=42)
        interaction = _FakeInteraction(guild_id=200)

        await cog.collega.callback(cog, interaction, codice)

        assert "collegato" in interaction.response.sent_messages[0]
        from core.backup_messages_logic import MESSAGGI_PER_CANALE

        assert f"ultimi {MESSAGGI_PER_CANALE} messaggi" in interaction.response.sent_messages[0]
        job = await repo.get_next_pending_job()
        assert (job.main_guild_id, job.backup_guild_id) == (100, 200)
    finally:
        await database.pool.execute("DELETE FROM backup_link_codes WHERE main_guild_id = 100")
        await database.pool.execute("DELETE FROM backup_pairs")
        await database.pool.execute("DELETE FROM backup_jobs")
        await database.close()


@pytest.mark.asyncio
async def test_collega_con_il_codice_sbagliato_non_fa_nulla(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        repo, cog = await _repo_con_cog(monkeypatch, database, _FakeCreator([200]))
        interaction = _FakeInteraction(guild_id=200)

        await cog.collega.callback(cog, interaction, "ZZZZ-ZZZZ-ZZZZ")

        assert "non valido" in interaction.response.sent_messages[0]
        assert await repo.get_next_pending_job() is None
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_collega_senza_il_creator_nel_server_spiega_cosa_fare(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        _repo, cog = await _repo_con_cog(monkeypatch, database, _FakeCreator([]))
        interaction = _FakeInteraction(guild_id=200)

        await cog.collega.callback(cog, interaction, "ZZZZ-ZZZZ-ZZZZ")

        assert "Creator" in interaction.response.sent_messages[0]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_define_main_fuori_da_un_server_rifiuta():
    cog = BackupCog(bot=None)
    interaction = _FakeInteraction(guild_id=None)

    await cog.define_main.callback(cog, interaction)

    assert "solo dentro un server" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_promuovi_backup_su_server_non_backup_avvisa(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        import cogs.utility.backup as backup_module
        from core.repositories.backup_repo import BackupRepository

        repo = BackupRepository(pool_provider=lambda: database.pool)
        monkeypatch.setattr(backup_module, "backup_repo", repo)
        monkeypatch.setattr(backup_module, "db", database)

        cog = BackupCog(bot=None)
        interaction = _FakeInteraction(guild_id=999)

        await cog.promuovi_backup.callback(cog, interaction)

        assert "non risulta registrato come backup" in interaction.response.sent_messages[0]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_promuovi_backup_promuove_senza_accodare_copie_orfane(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        repo, cog = await _repo_con_cog(monkeypatch, database)
        import cogs.utility.backup as backup_module

        from core.repositories.backup_mirror_repo import BackupMirrorRepository

        monkeypatch.setattr(backup_module, "db", database)
        monkeypatch.setattr(
            backup_module, "backup_mirror_repo", BackupMirrorRepository(pool_provider=lambda: database.pool)
        )
        await repo.define_main(100)
        await repo.define_backup(100, 200)
        interaction = _FakeInteraction(guild_id=200)

        await cog.promuovi_backup.callback(cog, interaction)

        messaggio = interaction.response.sent_messages[0]
        assert "promosso a" in messaggio and "100" in messaggio
        assert "/backup crea" in messaggio
        assert await repo.get_next_pending_job() is None  # un job senza server non servirebbe
        assert await repo.is_backup_of(100, 200)  # coppia storica (BUG-34)
    finally:
        await database.pool.execute("DELETE FROM backup_pairs")
        await database.pool.execute("DELETE FROM backup_jobs")
        await database.pool.execute("DELETE FROM backup_pair_history WHERE old_main_guild_id = 100")
        await database.close()


@pytest.mark.asyncio
async def test_promuovi_vuole_lo_stesso_livello_di_carica_e_toglie_il_mirror(monkeypatch):
    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        repo, cog = await _repo_con_cog(monkeypatch, database)
        import cogs.utility.backup as backup_module
        from core.repositories.backup_mirror_repo import BackupMirrorRepository

        mirror = BackupMirrorRepository(pool_provider=lambda: database.pool)
        monkeypatch.setattr(backup_module, "db", database)
        monkeypatch.setattr(backup_module, "backup_mirror_repo", mirror)
        await repo.define_main(100)
        await repo.define_backup(100, 200)
        await mirror.save_mapping(100, 200, {5: "https://discord.com/api/webhooks/1/x"})

        # un admin che non è l'owner: al livello predefinito non può
        admin = _FakeInteraction(guild_id=200)
        admin.guild.owner_id = 7
        await cog.promuovi_backup.callback(cog, admin)
        assert "⛔" in admin.response.sent_messages[0]
        assert await mirror.get_webhook_url(5) is not None
        assert (await repo.get_pair(100)).backup_guild_id == 200

        proprietario = _FakeInteraction(guild_id=200)
        await cog.promuovi_backup.callback(cog, proprietario)
        assert "promosso" in proprietario.response.sent_messages[0]
        assert await mirror.get_webhook_url(5) is None
    finally:
        await database.pool.execute("DELETE FROM backup_pairs")
        await database.pool.execute("DELETE FROM backup_mirror_webhooks")
        await database.pool.execute("DELETE FROM backup_pair_history WHERE old_main_guild_id = 100")
        await database.close()


# ---- 13/10: il cog passa davvero utente_id e puo_collegare a collega_backup ----

class _MembroMain:
    def __init__(self, uid, admin):
        self.id = uid
        self.guild_permissions = type("P", (), {"administrator": admin})()


class _MainFinto:
    def __init__(self, owner_id=0, membri=None):
        self.owner_id = owner_id
        self._membri = membri or {}

    def get_member(self, uid):
        return self._membri.get(uid)


class _BotMain(_FakeBot):
    def __init__(self, creator, main):
        super().__init__(creator)
        self._main = main

    def get_guild(self, guild_id):
        return self._main


async def _collega_con(monkeypatch, creato_da, main_finto):
    """Esegue /backup collega dal server 200 (utente 42, admin lì). Restituisce (messaggio, coppia)."""
    from core.backup_link_logic import crea_codice_collegamento

    database = Database()
    await database.connect()
    try:
        await database.run_migrations()
        import cogs.utility.backup as backup_module
        from core.repositories.backup_repo import BackupRepository

        repo = BackupRepository(pool_provider=lambda: database.pool)
        monkeypatch.setattr(backup_module, "backup_repo", repo)
        cog = BackupCog(bot=_BotMain(_FakeCreator([200]), main_finto))
        codice, _ = await crea_codice_collegamento(repo, 100, creato_da=creato_da)
        interaction = _FakeInteraction(guild_id=200)

        await cog.collega.callback(cog, interaction, codice)

        return interaction.response.sent_messages[0], await repo.get_pair(100)
    finally:
        await database.pool.execute("DELETE FROM backup_link_codes WHERE main_guild_id = 100")
        await database.pool.execute("DELETE FROM backup_pairs")
        await database.pool.execute("DELETE FROM backup_jobs")
        await database.close()


@pytest.mark.asyncio
async def test_collega_con_il_codice_di_un_altro_utente_e_rifiutato(monkeypatch):
    messaggio, coppia = await _collega_con(monkeypatch, 7, _MainFinto(membri={42: _MembroMain(42, True)}))
    assert "solo chi lo ha creato" in messaggio
    assert coppia is None


@pytest.mark.asyncio
async def test_collega_da_chi_non_e_admin_del_main_e_rifiutato(monkeypatch):
    messaggio, coppia = await _collega_con(monkeypatch, 42, _MainFinto(membri={42: _MembroMain(42, False)}))
    assert "amministratore" in messaggio
    assert coppia is None


@pytest.mark.asyncio
async def test_collega_da_chi_non_e_nel_main_e_rifiutato(monkeypatch):
    messaggio, coppia = await _collega_con(monkeypatch, 42, _MainFinto())
    assert "amministratore" in messaggio
    assert coppia is None


@pytest.mark.asyncio
async def test_collega_dall_owner_del_main_senza_admin_e_ammesso(monkeypatch):
    messaggio, coppia = await _collega_con(
        monkeypatch, 42, _MainFinto(owner_id=42, membri={42: _MembroMain(42, False)})
    )
    assert "collegato" in messaggio
    assert coppia is not None and coppia.backup_guild_id == 200
