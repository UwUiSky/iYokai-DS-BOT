"""
tests/test_backup_sincronia_canali.py
=====================================
Sincronia dei messaggi tra due canali (BKP-028): direzioni, tetto, protezione contro i cicli,
solo l'owner di entrambi i server. Elenco e disattivazione (BKP-031).
Funzioni coperte: BKP-028, BKP-031
"""

from __future__ import annotations

from types import SimpleNamespace

import discord
import pytest

import cogs.utility.backup as modulo
from core.backup_mirror_dispatch import BackupMirrorDispatcher
from core.database import Database
from core.repositories.backup_sincronia_canali_repo import MAX_DIREZIONI_PER_SERVER, BackupSincroniaCanaliRepository
from tests.test_backup_struttura_cog import _interazione

GA, GB = 940001, 940002
CA, CB = 940101, 940102


@pytest.fixture
async def ambiente(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    repo = BackupSincroniaCanaliRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(modulo, "backup_sincronia_canali_repo", repo)
    monkeypatch.setattr(modulo, "db", database)
    yield database, repo
    await database.pool.execute("DELETE FROM backup_sincronia_canali WHERE guild_da IN ($1, $2)", GA, GB)
    await database.pool.execute("DELETE FROM backup_registro WHERE guild_id IN ($1, $2)", GA, GB)
    await database.close()


class _Hook:
    def __init__(self, url):
        self.url = url


class _Testo(discord.TextChannel):
    def __init__(self, canale_id, guild_id, proprietario):
        self.id = canale_id
        self.name = f"c{canale_id}"
        self.guild = SimpleNamespace(id=guild_id, name=f"S{guild_id}", owner_id=proprietario)

    @property
    def mention(self):
        return f"<#{self.id}>"


class _Bot:
    def __init__(self, *canali):
        self.canali = {c.id: c for c in canali}

    def get_channel(self, i):
        return self.canali.get(i)


def _owner(guild_id):
    i = _interazione(owner=True)
    i.guild.id = guild_id
    return i


async def test_attiva_nei_due_sensi_e_poi_si_toglie(ambiente, monkeypatch):
    database, repo = ambiente
    qui, altro = _Testo(CA, GA, 1), _Testo(CB, GB, 1)

    async def hook(canale):
        return _Hook(f"https://hook/{canale.id}")

    monkeypatch.setattr(modulo, "webhook_chat", hook)
    cog = modulo.BackupCog(bot=_Bot(qui, altro))
    i = _owner(GA)
    scelta = SimpleNamespace(value="attiva")
    await cog.sincronia_canali.callback(cog, i, scelta, qui, str(CB), SimpleNamespace(value="due_sensi"))
    assert await repo.get_webhook_url(CA) == f"https://hook/{CB}"
    assert await repo.get_webhook_url(CB) == f"https://hook/{CA}"
    assert len(await repo.elenco(GA)) == 2
    i = _owner(GA)
    await cog.sincronia_canali.callback(cog, i, SimpleNamespace(value="elenco"), None, None, None)
    assert f"<#{CA}>" in i.response.messaggi[0][0]
    i = _owner(GA)
    await cog.sincronia_canali.callback(cog, i, SimpleNamespace(value="disattiva"), qui, str(CB), None)
    assert await repo.get_webhook_url(CA) is None and await repo.get_webhook_url(CB) is None


async def test_una_sola_direzione(ambiente, monkeypatch):
    _db, repo = ambiente
    qui, altro = _Testo(CA, GA, 1), _Testo(CB, GB, 1)

    async def hook(canale):
        return _Hook(f"https://hook/{canale.id}")

    monkeypatch.setattr(modulo, "webhook_chat", hook)
    cog = modulo.BackupCog(bot=_Bot(qui, altro))
    await cog.sincronia_canali.callback(
        cog, _owner(GA), SimpleNamespace(value="attiva"), qui, str(CB), SimpleNamespace(value="verso_qui")
    )
    assert await repo.get_webhook_url(CA) is None and await repo.get_webhook_url(CB) == f"https://hook/{CA}"


async def test_owner_diverso_o_non_owner_non_attiva(ambiente, monkeypatch):
    _db, repo = ambiente
    qui, altro = _Testo(CA, GA, 1), _Testo(CB, GB, 555)  # l'altro server è di un altro
    monkeypatch.setattr(modulo, "webhook_chat", lambda c: pytest.fail("nessun webhook"))
    cog = modulo.BackupCog(bot=_Bot(qui, altro))
    i = _owner(GA)
    await cog.sincronia_canali.callback(cog, i, SimpleNamespace(value="attiva"), qui, str(CB), None)
    assert "owner di entrambi" in i.response.messaggi[0][0].lower() or "entrambi" in i.response.messaggi[0][0]
    admin = _interazione(admin=True, owner=False)
    admin.guild.id = GA
    await cog.sincronia_canali.callback(cog, admin, SimpleNamespace(value="attiva"), qui, str(CB), None)
    assert await repo.elenco(GA) == []


async def test_tetto_di_direzioni_per_server(ambiente):
    _db, repo = ambiente
    for n in range(MAX_DIREZIONI_PER_SERVER):
        assert await repo.attiva(950000 + n, GA, 960000 + n, GB, "https://hook/x", 1)
    assert not await repo.attiva(970000, GA, 970001, 940003, "https://hook/x", 1)
    assert await repo.attiva(950000, GA, 960000, GB, "https://hook/nuovo", 1)  # aggiornare è sempre possibile
    assert await repo.get_webhook_url(950000) == "https://hook/nuovo"


class _Autore:
    def __init__(self, bot):
        self.bot, self.display_name = bot, "Mario"


async def test_i_messaggi_vanno_nel_canale_giusto_e_i_webhook_non_tornano_indietro(ambiente):
    """BKP-028: un utente si copia; un messaggio di bot o webhook (anche il nostro) no, quindi niente cicli."""
    _db, repo = ambiente
    await repo.attiva(CA, GA, CB, GB, "https://hook/b", 1)
    await repo.attiva(CB, GB, CA, GA, "https://hook/a", 1)
    inviati = []
    d = BackupMirrorDispatcher(mirror_repo=repo)

    async def finto(url, messaggio):
        inviati.append((url, messaggio.content))

    d._send = finto

    def msg(canale, bot, testo):
        return SimpleNamespace(
            channel=SimpleNamespace(id=canale), author=_Autore(bot), guild=SimpleNamespace(id=GA), content=testo,
            attachments=[], type=discord.MessageType.default,
        )

    assert await d.handle_message(msg(CA, False, "ciao"))
    assert not await d.handle_message(msg(CB, True, "ciao"))  # la copia arrivata dall'altro lato
    assert not await d.handle_message(msg(777, False, "altro canale"))
    await d.svuota()
    assert inviati == [("https://hook/b", "ciao")]
    await d.close()
