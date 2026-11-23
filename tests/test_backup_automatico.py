"""
tests/test_backup_automatico.py
===============================
Copie automatiche della struttura (BKP-008) e lista delle copie, i più nuovi per primi (BKP-005).
Funzioni coperte: BKP-005, BKP-008
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core import backup_automatico_logic as logica
from core.database import Database
from core.repositories.backup_automatico_repo import BackupAutomaticoRepository
from core.repositories.backup_struttura_repo import MAX_COPIE_PER_SERVER, BackupStrutturaRepository

G = 930001


@pytest.fixture
async def ambiente(monkeypatch):
    database = Database()
    await database.connect()
    await database.run_migrations()
    auto = BackupAutomaticoRepository(pool_provider=lambda: database.pool)
    copie = BackupStrutturaRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(logica, "backup_automatico_repo", auto)
    monkeypatch.setattr(logica, "backup_struttura_repo", copie)
    monkeypatch.setattr(logica.struttura, "leggi_struttura", lambda g: {"versione": 1, "ruoli": [], "canali": []})
    yield database, auto, copie
    await database.pool.execute("DELETE FROM backup_automatici WHERE guild_id = $1", G)
    await database.pool.execute("DELETE FROM backup_strutture WHERE guild_id = $1", G)
    await database.close()


def _bot(presente=True):
    return SimpleNamespace(get_guild=lambda i: SimpleNamespace(id=i) if presente else None)


async def test_la_copia_automatica_parte_all_intervallo_e_tiene_solo_n_copie(ambiente):
    """BKP-008: ogni N ore una copia; oltre le copie volute la più vecchia automatica si sovrascrive."""
    database, auto, copie = ambiente
    await auto.imposta(G, 4, 2, 1)
    assert await logica.fai_copia_automatica(_bot())
    assert not await logica.fai_copia_automatica(_bot())  # non ancora dovuta
    for _ in range(3):
        await database.pool.execute("UPDATE backup_automatici SET ultimo = now() - interval '5 hours' WHERE guild_id = $1", G)
        assert await logica.fai_copia_automatica(_bot())
    lista = await copie.lista_strutture(G)
    assert len(lista) == 2 and all(c.automatica for c in lista)


async def test_le_copie_a_mano_non_si_toccano_e_se_e_pieno_non_si_salva(ambiente):
    database, auto, copie = ambiente
    for n in range(MAX_COPIE_PER_SERVER):
        assert await copie.salva_struttura(G, f"m{n}", 1, {"versione": 1})
    await auto.imposta(G, 4, 3, 1)
    assert not await logica.fai_copia_automatica(_bot())
    assert len(await copie.lista_strutture(G)) == MAX_COPIE_PER_SERVER
    assert not any(c.automatica for c in await copie.lista_strutture(G))


async def test_server_assente_si_segna_e_non_blocca_gli_altri(ambiente):
    _db, auto, _c = ambiente
    await auto.imposta(G, 4, 1, 1)
    assert not await logica.fai_copia_automatica(_bot(presente=False))
    assert await auto.prossimo_dovuto() is None


async def test_limiti_e_spegnimento(ambiente):
    _db, auto, _c = ambiente
    with pytest.raises(ValueError):
        await auto.imposta(G, 2, 1, 1)
    with pytest.raises(ValueError):
        await auto.imposta(G, 4, 9, 1)
    await auto.imposta(G, 24, 3, 1)
    assert (await auto.leggi(G)).ore == 24
    assert await auto.togli(G) and not await auto.togli(G)


async def test_la_lista_ha_i_piu_nuovi_per_primi(ambiente):
    """BKP-005: elenco per data decrescente, con le automatiche segnate."""
    database, _a, copie = ambiente
    for nome in ("vecchia", "nuova"):
        await copie.salva_struttura(G, nome, 1, {"versione": 1})
        await database.pool.execute("UPDATE backup_strutture SET creato_il = creato_il - interval '1 day' WHERE guild_id = $1 AND nome = 'vecchia'", G)
    assert [c.nome for c in await copie.lista_strutture(G)] == ["nuova", "vecchia"]


async def test_il_comando_accende_legge_e_spegne(ambiente, monkeypatch):
    import cogs.utility.backup as modulo
    from tests.test_backup_struttura_cog import _interazione

    database, auto, copie = ambiente
    monkeypatch.setattr(modulo, "db", database)
    monkeypatch.setattr(modulo, "backup_automatico_repo", auto)
    monkeypatch.setattr(modulo, "backup_struttura_repo", copie)
    cog = modulo.BackupCog(bot=None)
    i = _interazione(owner=True)
    i.guild.id = G
    await cog.automatico.callback(cog, i, 12, 4, False)
    assert "ogni 12 ore" in i.response.messaggi[0][0]
    assert (await auto.leggi(G)).copie == 4
    i = _interazione(owner=True)
    i.guild.id = G
    await cog.automatico.callback(cog, i, None, 3, True)
    assert "spente" in i.response.messaggi[0][0] and await auto.leggi(G) is None
    await database.pool.execute("DELETE FROM backup_registro WHERE guild_id = $1", G)
