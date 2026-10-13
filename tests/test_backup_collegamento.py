"""
tests/test_backup_collegamento.py
=================================
M 12.1, 12.2, 12.9, 12.13 (#68): collegamento tra server principale e
server di backup con un codice; nessuna creazione di server; permessi
dell'invito; coppia storica dopo la promozione.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
import pytest

from core.backup_link_logic import (
    ESITO_GIA_USATO,
    ESITO_OK,
    ESITO_SCADUTO,
    ESITO_SCONOSCIUTO,
    ESITO_STESSO_SERVER,
    VALIDITA_CODICE,
    collega_backup,
    crea_codice_collegamento,
    genera_codice,
    hash_codice,
    permessi_invito_creator,
    permessi_invito_main,
)
from core.database import Database
from core.repositories.backup_repo import STATUS_PENDING, BackupRepository

MAIN, BACKUP = 910001, 910002
RADICE = Path(__file__).resolve().parent.parent


@pytest.fixture
async def repo():
    database = Database()
    await database.connect()
    await database.run_migrations()
    pulizia = (
        "DELETE FROM backup_link_codes WHERE main_guild_id = ANY($1)",
        "DELETE FROM backup_jobs WHERE main_guild_id = ANY($1)",
        "DELETE FROM backup_pairs WHERE main_guild_id = ANY($1)",
        "DELETE FROM backup_pair_history WHERE old_main_guild_id = ANY($1)",
    )
    ids = [MAIN, BACKUP]
    for q in pulizia:
        await database.pool.execute(q, ids)
    yield BackupRepository(pool_provider=lambda: database.pool)
    for q in pulizia:
        await database.pool.execute(q, ids)
    await database.close()


def test_il_codice_ha_la_forma_attesa_e_non_si_ripete():
    codici = {genera_codice() for _ in range(50)}
    assert len(codici) == 50
    assert all(re.fullmatch(r"[A-Z2-9]{4}(-[A-Z2-9]{4}){2}", c) for c in codici)


def test_l_impronta_ignora_trattini_spazi_e_maiuscole():
    assert hash_codice("abcd-efgh-jkmn") == hash_codice(" ABCD EFGH JKMN ")


@pytest.mark.asyncio
async def test_codice_giusto_collega_e_mette_in_coda_la_copia(repo):
    codice, _scade = await crea_codice_collegamento(repo, MAIN, creato_da=1)
    esito = await collega_backup(repo, codice, BACKUP)

    assert esito.esito == ESITO_OK
    assert esito.main_guild_id == MAIN
    coppia = await repo.get_pair(MAIN)
    assert coppia is not None and coppia.backup_guild_id == BACKUP
    job = await repo.get_job(esito.job_id)
    assert job.status == STATUS_PENDING
    assert job.backup_guild_id == BACKUP


@pytest.mark.asyncio
async def test_codice_sbagliato_non_collega_nulla(repo):
    await crea_codice_collegamento(repo, MAIN, creato_da=1)
    esito = await collega_backup(repo, "AAAA-BBBB-CCCC", BACKUP)

    assert esito.esito == ESITO_SCONOSCIUTO
    assert await repo.get_pair(MAIN) is None
    assert not await repo.has_active_job(MAIN)


@pytest.mark.asyncio
async def test_codice_scaduto_non_collega_nulla(repo):
    adesso = datetime.now(timezone.utc)
    codice, _ = await crea_codice_collegamento(
        repo, MAIN, creato_da=1, adesso=adesso - VALIDITA_CODICE - timedelta(minutes=1)
    )
    esito = await collega_backup(repo, codice, BACKUP, adesso=adesso)

    assert esito.esito == ESITO_SCADUTO
    assert await repo.get_pair(MAIN) is None


@pytest.mark.asyncio
async def test_codice_si_usa_una_volta_sola(repo):
    codice, _ = await crea_codice_collegamento(repo, MAIN, creato_da=1)
    assert (await collega_backup(repo, codice, BACKUP)).esito == ESITO_OK
    assert (await collega_backup(repo, codice, BACKUP + 1)).esito == ESITO_GIA_USATO


@pytest.mark.asyncio
async def test_il_server_principale_non_puo_essere_il_proprio_backup(repo):
    codice, _ = await crea_codice_collegamento(repo, MAIN, creato_da=1)
    assert (await collega_backup(repo, codice, MAIN)).esito == ESITO_STESSO_SERVER
    # il codice non è stato bruciato: si può ancora usare nel server giusto
    assert (await collega_backup(repo, codice, BACKUP)).esito == ESITO_OK


def test_il_link_d_invito_chiede_anche_creare_espressioni():
    """M 12.9: CREATE_GUILD_EXPRESSIONS per Main e per il Creator."""
    assert permessi_invito_main().create_expressions
    creator = permessi_invito_creator()
    assert creator.create_expressions and creator.manage_webhooks
    assert creator.manage_roles and creator.manage_channels
    assert not creator.administrator


def test_nessuna_chiamata_per_creare_cedere_o_cancellare_server():
    """M 12.2 (cricchetto): D8, un bot non può creare server."""
    vietato = re.compile(
        r"\bcreate_guild\(|\bpulisci_server_orfani\b|\belimina_server_creato\b"
        r"|\b(guild|server|nuovo_server)\.delete\(\)|owner=\w+\.me|MAX_CREATOR_GUILDS"
    )
    file = [
        *RADICE.glob("core/backup_*.py"),
        *RADICE.glob("cogs/utility/backup*.py"),
    ]
    trovati = [
        f"{f.name}:{i}"
        for f in file
        for i, riga in enumerate(f.read_text(encoding="utf-8").splitlines(), 1)
        if vietato.search(riga) and not riga.lstrip().startswith("#")
    ]
    assert trovati == []


@pytest.mark.asyncio
async def test_restore_dopo_la_promozione_riconosce_la_coppia_storica(repo):
    """M 12.13 (BUG-34): il backup promosso può ancora ripristinare gli utenti del vecchio main."""
    await repo.define_backup(MAIN, BACKUP)
    assert await repo.is_backup_of(MAIN, BACKUP)

    await repo.promote_backup_to_main(old_main_guild_id=MAIN, new_main_guild_id=BACKUP)

    assert (await repo.get_pair(MAIN)).backup_guild_id is None
    assert await repo.is_backup_of(MAIN, BACKUP)
    assert not await repo.is_backup_of(MAIN, BACKUP + 5)
    assert not await repo.is_backup_of(BACKUP, MAIN)


@pytest.mark.asyncio
async def test_il_codice_vale_24_ore_esatte(repo):
    adesso = datetime.now(timezone.utc)
    assert VALIDITA_CODICE == timedelta(hours=24)
    _codice, scadenza = await crea_codice_collegamento(repo, MAIN, creato_da=1, adesso=adesso)
    assert scadenza == adesso + timedelta(hours=24)

    dentro, _ = await crea_codice_collegamento(
        repo, MAIN, creato_da=1, adesso=adesso - timedelta(hours=23, minutes=59)
    )
    assert (await collega_backup(repo, dentro, BACKUP, adesso=adesso)).esito == ESITO_OK
