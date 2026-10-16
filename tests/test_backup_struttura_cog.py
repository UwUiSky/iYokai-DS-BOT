"""
tests/test_backup_struttura_cog.py
==================================
I comandi /backup delle copie: livello di permesso, file importato non valido,
menu delle parti e caricamento in sottofondo con riepilogo nel canale.
Funzioni coperte: BKP-009, BKP-010, BKP-018, BKP-019, BKP-037, M 12.17
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import cogs.utility.backup as backup_module
from cogs.utility.backup import BackupCog, ScegliPartiView
from core.database import Database
from core.repositories.backup_struttura_repo import BackupStrutturaRepository

GUILD = 920001


class _Risposte:
    def __init__(self):
        self.messaggi = []

    async def send_message(self, contenuto=None, **kw):
        self.messaggi.append((contenuto, kw))

    async def send(self, contenuto=None, **kw):
        self.messaggi.append((contenuto, kw))

    async def defer(self, **kw):
        pass

    async def edit_message(self, **kw):
        self.messaggi.append((kw.get("content"), kw))


class _Canale:
    def __init__(self):
        self.inviati = []

    async def send(self, testo):
        self.inviati.append(testo)


def _interazione(admin=True, owner=False):
    guild = SimpleNamespace(id=GUILD, owner_id=1 if owner else 2)
    return SimpleNamespace(
        guild=guild,
        user=SimpleNamespace(id=1, guild_permissions=SimpleNamespace(administrator=admin)),
        response=_Risposte(),
        followup=_Risposte(),
        channel=_Canale(),
    )


@pytest.fixture
async def ambiente(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    repo = BackupStrutturaRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(backup_module, "backup_struttura_repo", repo)
    monkeypatch.setattr(backup_module, "db", database)
    yield database, repo
    for tabella in ("backup_strutture", "backup_caricamenti", "backup_registro"):
        await database.pool.execute(f"DELETE FROM {tabella} WHERE guild_id = $1", GUILD)
    await database.pool.execute("DELETE FROM guild_config WHERE guild_id = $1", GUILD)
    await database.close()


async def test_admin_non_carica_al_livello_predefinito(ambiente):
    cog = BackupCog(bot=None)
    i = _interazione(admin=True, owner=False)
    await cog.carica.callback(cog, i, 1)
    assert "solo l'owner carica" in i.response.messaggi[0][0]


async def test_solo_l_owner_cambia_il_livello_e_finisce_nel_registro(ambiente):
    database, repo = ambiente
    cog = BackupCog(bot=None)
    scelta = SimpleNamespace(value="admin_tutto", name="Gli admin creano e caricano")
    i = _interazione(admin=True, owner=False)
    await cog.permessi.callback(cog, i, scelta)
    assert "Solo l'owner" in i.response.messaggi[0][0]
    i = _interazione(owner=True)
    await cog.permessi.callback(cog, i, scelta)
    assert await database.get_guild_setting(GUILD, "backup_livello_permessi") == "admin_tutto"
    assert (await repo.leggi_registro(GUILD))[0]["azione"] == "permessi"


async def test_file_non_valido_non_tocca_il_server(ambiente):
    cog = BackupCog(bot=None)
    i = _interazione(owner=True)

    class _File:
        size = 20
        filename = "x.json"

        async def read(self):
            return b'{"versione": 2}'

    await cog.importa.callback(cog, i, _File())
    assert "File non valido" in i.followup.messaggi[0][0]
    assert "view" not in i.followup.messaggi[0][1]


async def test_menu_delle_parti_e_caricamento_con_riepilogo_nel_canale(ambiente, monkeypatch):
    _db, repo = ambiente
    cog = BackupCog(bot=None)
    dati = {"versione": 1, "ruoli": [{"nome": "r", "permessi": 0}], "ban": [{"user_id": 7}]}
    view = ScegliPartiView(cog, 1, dati, "copia #1")
    assert [o.value for o in view.menu.options] == ["ruoli", "ban"]
    assert view.scelte == {"ruoli"}  # i ban non partono se non li scegli

    class _Caricatore:
        def __init__(self, guild, dati, parti, avanza, scarica, tetto):
            assert tetto is None  # l'owner del server non ha tetto
            self.avanza = avanza

        async def esegui(self):
            assert await self.avanza("ruoli", 1, 1) is False
            return SimpleNamespace(annullato=False, testo=lambda: "Creati: 1")

    monkeypatch.setattr(backup_module.struttura, "Caricatore", _Caricatore)
    i = _interazione(owner=True)
    await view.conferma.callback(i)
    await asyncio.gather(*cog._lavori)
    assert "avviato" in i.response.messaggi[0][0]
    assert "Creati: 1" in i.channel.inviati[0]
    stato = await repo.ultimo_caricamento(GUILD)
    assert (stato.stato, stato.fatti) == ("finito", 1)
    assert (await repo.leggi_registro(GUILD))[0]["azione"] == "carica"


async def test_esporta_un_ruolo_senza_ruolo_spiega(ambiente):
    cog = BackupCog(bot=None)
    i = _interazione(owner=True)
    await cog.esporta.callback(cog, i, SimpleNamespace(value="ruolo", name="Un ruolo"), None, None, None, None)
    assert "Scegli il ruolo" in i.followup.messaggi[0][0]


async def test_modello_si_pubblica_e_si_usa_senza_dati_personali(ambiente):
    _db, repo = ambiente
    copia = await repo.salva_struttura(
        GUILD, "base", 1, {"versione": 1, "ruoli": [{"nome": "r", "permessi": 0}], "ban": [{"user_id": 7}]}
    )
    cog = BackupCog(bot=None)
    i = _interazione(owner=True)
    await cog.modello.callback(cog, i, SimpleNamespace(value="pubblica", name="p"), copia, None)
    codice = (await repo.lista_strutture(GUILD))[0].codice_modello
    assert codice in i.response.messaggi[0][0]

    i = _interazione(owner=True)
    await cog.modello.callback(cog, i, SimpleNamespace(value="usa", name="u"), None, codice)
    view = i.response.messaggi[0][1]["view"]
    assert "ban" not in view.dati and [o.value for o in view.menu.options] == ["ruoli"]

    i = _interazione(owner=True)
    await cog.modello.callback(cog, i, SimpleNamespace(value="ritira", name="r"), copia, None)
    assert await repo.leggi_modello(codice) is None


async def test_chat_e_struttura_non_si_scambiano(ambiente):
    _db, repo = ambiente
    chat = await repo.salva_struttura(GUILD, "chat", 1, {"versione": 1, "tipo": "chat", "messaggi": []})
    copia = await repo.salva_struttura(GUILD, "copia", 1, {"versione": 1, "ruoli": []})
    assert [c.chat for c in await repo.lista_strutture(GUILD)] == [False, True]
    assert await repo.pubblica_modello(GUILD, chat) is None  # una chat non diventa un modello
    cog = BackupCog(bot=None)
    i = _interazione(owner=True)
    await cog.carica.callback(cog, i, chat)
    assert "chat-carica" in i.response.messaggi[0][0]
    i = _interazione(owner=True)
    i.channel = SimpleNamespace()
    await cog.chat_carica.callback(cog, i, copia, None)
    assert "non trovata" in i.response.messaggi[0][0]


async def test_file_importato_non_assegna_ruoli_ai_membri(ambiente):
    """L'esportazione non contiene i membri: un file che li ha non può dare ruoli a ID scelti da altri."""
    import json

    cog = BackupCog(bot=None)
    i = _interazione(owner=True)
    contenuto = json.dumps({
        "versione": 1, "ruoli": [{"nome": "Admin", "permessi": 8}],
        "membri": [{"user_id": 666, "nick": None, "ruoli": ["Admin"]}],
    }).encode()

    class _File:
        size = len(contenuto)
        filename = "modello.json"

        async def read(self):
            return contenuto

    await cog.importa.callback(cog, i, _File())
    view = i.followup.messaggi[0][1]["view"]
    assert "membri" not in view.dati
    assert "membri" not in [o.value for o in view.menu.options]


def test_tetto_e_il_ruolo_piu_alto_di_chi_carica_salvo_l_owner():
    """Al livello «admin_tutto» l'admin carica, ma non sopra il suo ruolo più alto."""
    alto = SimpleNamespace(name="Mod")
    i = _interazione(owner=False)
    i.user.top_role = alto
    i.guild.default_role = SimpleNamespace(name="@everyone")
    assert backup_module.tetto_di(i) is alto
    del i.user.top_role
    assert backup_module.tetto_di(i) is i.guild.default_role
    assert backup_module.tetto_di(_interazione(owner=True)) is None
