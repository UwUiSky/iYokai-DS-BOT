"""
tests/test_backup_sic016.py
===========================
SIC-016 (D121): ripristino dopo un attacco dall'ultima copia automatica. La copia automatica può farsi ogni 3 ore
(BKP-008, per chi lo chiede); `/admin-backup carica ultima_automatica:sì` la riprende, solo il proprietario del server,
solo la struttura (ruoli e canali), con il menu di conferma di sempre.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import cogs.utility.backup as modulo
from core import backup_struttura_logic as struttura
from core.database import Database
from core.repositories.backup_automatico_repo import ORE_MINIME, BackupAutomaticoRepository
from core.repositories.backup_struttura_repo import BackupStrutturaRepository

G = 880077


@pytest.fixture
async def ambiente(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    auto = BackupAutomaticoRepository(pool_provider=lambda: database.pool)
    copie = BackupStrutturaRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(modulo, "db", database)
    monkeypatch.setattr(modulo, "backup_automatico_repo", auto)
    monkeypatch.setattr(modulo, "backup_struttura_repo", copie)
    yield database, auto, copie
    await database.pool.execute("DELETE FROM backup_automatici WHERE guild_id = $1", G)
    await database.pool.execute("DELETE FROM backup_strutture WHERE guild_id = $1", G)
    await database.close()


def test_la_copia_automatica_puo_farsi_ogni_3_ore():
    assert ORE_MINIME == 3


async def test_ogni_3_ore_si_accetta_e_2_no(ambiente):
    _, auto, _ = ambiente
    await auto.imposta(G, 3, 2, 1)
    assert (await auto.leggi(G)).ore == 3
    with pytest.raises(ValueError):
        await auto.imposta(G, 2, 2, 1)


def test_solo_struttura_tiene_ruoli_e_canali_e_toglie_il_resto():
    dati = {"versione": 1, "ruoli": [{"nome": "a"}], "categorie": [{"nome": "c"}], "canali": [{"nome": "g"}], "everyone": {"p": 1},
            "ban": [{"id": 1}], "membri": [{"id": 2}], "messaggi": {"1": [1]}, "emoji": [{"n": "x"}], "impostazioni": {"a": 1}, "automatica": True}
    s = struttura.solo_struttura(dati)
    assert struttura.parti_presenti(s) == ["ruoli", "canali"]
    assert "ban" not in s and "membri" not in s and "messaggi" not in s and "emoji" not in s


async def test_ultima_automatica_prende_la_piu_recente_e_non_le_copie_a_mano(ambiente):
    _, _, copie = ambiente
    await copie.salva_struttura(G, "a mano", 1, {"versione": 1, "ruoli": [{"nome": "manuale"}]})
    await copie.salva_automatica(G, "auto 1", {"versione": 1, "ruoli": [{"nome": "vecchia"}]}, 3)
    await copie.salva_automatica(G, "auto 2", {"versione": 1, "ruoli": [{"nome": "nuova"}]}, 3)
    trovata = await copie.ultima_automatica(G)
    assert trovata is not None and trovata[2]["ruoli"][0]["nome"] == "nuova"
    assert await copie.ultima_automatica(G + 1) is None


def _interazione(user_id, owner_id):
    inter = MagicMock()
    inter.guild = SimpleNamespace(id=G, owner_id=owner_id)
    inter.user = SimpleNamespace(id=user_id, guild_permissions=SimpleNamespace(administrator=True))
    inter.response.send_message = AsyncMock()
    return inter


async def test_il_comando_serve_il_proprietario_e_mostra_solo_la_struttura(ambiente, monkeypatch):
    _, _, copie = ambiente
    await copie.salva_automatica(G, "auto", {"versione": 1, "ruoli": [{"nome": "r"}], "canali": [{"nome": "c"}], "ban": [{"id": 1}]}, 3)
    cog = modulo.BackupCog(bot=None)
    monkeypatch.setattr(cog, "_puo", AsyncMock(return_value=True))
    altro = _interazione(user_id=2, owner_id=1)
    await cog.carica.callback(cog, altro, None, True)
    assert "proprietario" in altro.response.send_message.await_args.args[0].lower() or altro.response.send_message.await_args.kwargs.get("view") is None
    proprietario = _interazione(user_id=1, owner_id=1)
    await cog.carica.callback(cog, proprietario, None, True)
    vista = proprietario.response.send_message.await_args.kwargs["view"]
    assert {o.value for o in vista.menu.options} == {"ruoli", "canali"}  # i ban non ci sono


async def test_senza_copia_o_senza_scelta_risponde_con_un_errore(ambiente, monkeypatch):
    cog = modulo.BackupCog(bot=None)
    monkeypatch.setattr(cog, "_puo", AsyncMock(return_value=True))
    i = _interazione(user_id=1, owner_id=1)
    await cog.carica.callback(cog, i, None, True)  # nessuna copia automatica
    assert i.response.send_message.await_args.kwargs.get("view") is None
    i2 = _interazione(user_id=1, owner_id=1)
    await cog.carica.callback(cog, i2, None, False)  # né numero né ultima_automatica
    assert i2.response.send_message.await_args.kwargs.get("view") is None
