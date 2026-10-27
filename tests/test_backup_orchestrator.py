"""
tests/test_backup_orchestrator.py
=================================
Test di core/backup_orchestrator.py (D8): la copia usa il server di backup
che il Creator ha già, nessuna creazione o cessione di server, e
finalize_backup_job dice solo se un server è atteso. Ogni test pulisce
il database prima e dopo: l'ordine di esecuzione non conta (#68).
"""

import pytest

from core.backup_orchestrator import finalize_backup_job, popola_server_backup, riassunto_copia
from core.backup_clone_logic import RiepilogoCopia
from core.database import Database
from core.repositories.backup_repo import BackupRepository

MAIN, BACKUP, ALTRO = 920001, 920002, 920003


class _SorgenteVuota:
    """Server sorgente con tutte le collezioni vuote: la clonazione vera è
    provata in tests/test_backup_clone_*.py, qui basta che l'orchestrazione la chiami."""

    id = MAIN
    name = "Il Mio Server"

    def __init__(self) -> None:
        import discord

        self.roles, self.categories, self.channels = [], [], []
        self.emojis, self.stickers, self.soundboard_sounds = [], [], []
        self.default_role = _Ruolo()
        self.me = object()
        self._perm = discord.Permissions.all()

    async def webhooks(self):
        return []


class _Ruolo:
    def __init__(self) -> None:
        import discord

        self.id = 1
        self.permissions = discord.Permissions.none()

    def is_default(self) -> bool:
        return True

    async def edit(self, **kwargs) -> None:
        pass


class _DestinazioneVuota:
    id = BACKUP
    name = "Backup"
    categories: list = []
    channels: list = []
    roles: list = []
    bitrate_limit = 96000.0

    def __init__(self) -> None:
        self.default_role = _Ruolo()
        self.default_role.id = 2
        self.chiamate_edit_role_positions = 0

    async def edit_role_positions(self, *a, **k) -> None:
        self.chiamate_edit_role_positions += 1


@pytest.fixture
async def repo():
    database = Database()
    await database.connect()
    await database.run_migrations()
    pulizia = (
        "DELETE FROM backup_jobs WHERE main_guild_id = ANY($1)",
        "DELETE FROM backup_pairs WHERE main_guild_id = ANY($1)",
    )
    ids = [MAIN, BACKUP, ALTRO, 100]
    for q in pulizia:
        await database.pool.execute(q, ids)
    yield BackupRepository(pool_provider=lambda: database.pool)
    for q in pulizia:
        await database.pool.execute(q, ids)
    await database.close()


class _Joined:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


@pytest.mark.asyncio
async def test_popola_server_backup_restituisce_mappa_mirror_e_riepilogo(monkeypatch):
    import core.backup_orchestrator as modulo

    monkeypatch.setattr(modulo, "conta_canali_non_visibili", lambda g: 0)
    mappa, riepilogo = await popola_server_backup(_SorgenteVuota(), _DestinazioneVuota())

    assert mappa == {}
    assert isinstance(riepilogo, RiepilogoCopia)


def test_il_riepilogo_dice_solo_cio_che_non_e_andato_come_l_originale():
    assert riassunto_copia(RiepilogoCopia()) == ""
    testo = riassunto_copia(RiepilogoCopia(canali_offuscati=2, canali_non_visibili=3, webhook_saltati=1))
    assert "offuscati saltati: 2" in testo
    assert "3 canali non visibili" in testo
    assert "14 per canale" in testo


@pytest.mark.asyncio
async def test_server_con_copia_in_corso_e_atteso_e_non_cambia_stato(repo):
    job_id = await repo.enqueue_linked_job(MAIN, BACKUP)
    await repo.mark_running(job_id)

    assert await finalize_backup_job(_Joined(BACKUP), None, repo) is True
    assert (await repo.get_job(job_id)).status == "running"


@pytest.mark.asyncio
async def test_server_di_backup_gia_collegato_e_atteso(repo):
    await repo.define_backup(MAIN, BACKUP)
    assert await finalize_backup_job(_Joined(BACKUP), None, repo) is True


@pytest.mark.asyncio
async def test_un_server_qualsiasi_non_e_atteso(repo):
    assert await finalize_backup_job(_Joined(ALTRO), None, repo) is False


@pytest.mark.asyncio
async def test_i_dati_di_un_altro_test_non_cambiano_l_esito(repo):
    """#68: prima il test dipendeva da righe lasciate da altri; con il DB
    sporco di proposito l'esito resta quello giusto."""
    await repo.define_backup(MAIN + 50, BACKUP)  # riga non nostra, stesso backup
    try:
        job_id = await repo.enqueue_linked_job(MAIN, BACKUP)
        await repo.mark_running(job_id)
        assert await finalize_backup_job(_Joined(ALTRO), None, repo) is False
    finally:
        await repo._pool.execute("DELETE FROM backup_pairs WHERE main_guild_id = $1", MAIN + 50)


@pytest.mark.asyncio
async def test_senza_messaggi_l_allineamento_non_ricopia_le_chat(monkeypatch):
    import core.backup_orchestrator as orch

    chiamate = []

    async def _vuota(*a, **k):
        return {}

    async def _conta(*a, **k):
        return 0

    async def _messaggi(*a, **k):
        chiamate.append("messaggi")

    for nome in ("clone_roles", "clone_categories_and_channels", "clone_webhooks", "create_mirror_webhooks"):
        monkeypatch.setattr(orch, nome, _vuota)
    for nome in ("clone_emoji", "clone_stickers", "clone_soundboard"):
        monkeypatch.setattr(orch, nome, _conta)
    monkeypatch.setattr(orch, "conta_canali_non_visibili", lambda g: 0)
    monkeypatch.setattr(orch, "copia_messaggi", _messaggi)

    await orch.popola_server_backup(object(), object(), con_messaggi=False)
    assert chiamate == []
    await orch.popola_server_backup(object(), object())
    assert chiamate == ["messaggi"]
