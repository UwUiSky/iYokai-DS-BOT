"""
tests/test_migrations.py
============================
Test del sistema di migrazioni versionate (DB-1, #25): il runner
applica una migrazione numerata una volta sola, due runner concorrenti
non la applicano due volte (pg_advisory_lock), e una migrazione che
fallisce non lascia metà schema (transazione per migrazione). Usa un
pool reale (db_pool) puntato a una cartella di migrazioni TEMPORANEA
(tmp_path), non a core/migrations/ vera — così questi test non
toccano le migrazioni reali del progetto.
"""

import asyncio
import os
import uuid

import asyncpg
import pytest

from core.migrations import (
    ADVISORY_LOCK_ID,
    MigrationError,
    apply_numbered_migrations,
    discover_migrations,
    ensure_schema_migrations_table,
    run_all_migrations,
)


def _scrivi_migrazione(tmp_path, nome_file, sql):
    (tmp_path / nome_file).write_text(sql, encoding="utf-8")


class TestDiscoverMigrations:
    def test_ordina_per_versione_non_per_nome(self, tmp_path):
        _scrivi_migrazione(tmp_path, "0010_seconda.sql", "SELECT 1;")
        _scrivi_migrazione(tmp_path, "0002_prima.sql", "SELECT 1;")

        trovate = discover_migrations(tmp_path)

        assert [m.version for m in trovate] == [2, 10]

    def test_ignora_i_file_che_non_sono_migrazioni(self, tmp_path):
        _scrivi_migrazione(tmp_path, "0001_valida.sql", "SELECT 1;")
        _scrivi_migrazione(tmp_path, "__init__.py", "")
        _scrivi_migrazione(tmp_path, "leggimi.txt", "note")

        trovate = discover_migrations(tmp_path)

        assert [m.name for m in trovate] == ["0001_valida"]

    @pytest.mark.parametrize(
        "nome_file", ["00003_cinque_cifre.sql", "abc_senza_numero.sql", "0003.sql", "003_tre.py"]
    )
    def test_un_nome_fuori_formato_e_un_errore_non_viene_saltato(self, tmp_path, nome_file):
        _scrivi_migrazione(tmp_path, "0001_valida.sql", "SELECT 1;")
        _scrivi_migrazione(tmp_path, nome_file, "SELECT 1;")

        with pytest.raises(MigrationError, match=nome_file):
            discover_migrations(tmp_path)

    def test_due_file_con_lo_stesso_numero_sono_un_errore(self, tmp_path):
        _scrivi_migrazione(tmp_path, "0002_una.sql", "SELECT 1;")
        _scrivi_migrazione(tmp_path, "0002_altra.sql", "SELECT 1;")

        with pytest.raises(MigrationError, match="0002_altra.*0002_una|0002_una.*0002_altra"):
            discover_migrations(tmp_path)

    def test_le_migrazioni_vere_del_progetto_hanno_nomi_validi_e_numeri_unici(self):
        versioni = [m.version for m in discover_migrations()]
        assert versioni == sorted(set(versioni)) and versioni[0] == 1

    def test_cartella_assente_restituisce_lista_vuota(self, tmp_path):
        assert discover_migrations(tmp_path / "non-esiste") == []


class TestApplyNumberedMigrations:
    @pytest.mark.asyncio
    async def test_applica_una_migrazione_e_la_registra(self, db_pool, tmp_path):
        await ensure_schema_migrations_table(db_pool)
        async with db_pool.acquire() as conn:
            await conn.execute("DROP TABLE IF EXISTS test_migrazione_marker_1")
            await conn.execute("DELETE FROM schema_migrations WHERE version = 9001")

        _scrivi_migrazione(
            tmp_path, "9001_crea_marker.sql", "CREATE TABLE test_migrazione_marker_1 (id INT);"
        )

        applicate = await apply_numbered_migrations(db_pool, tmp_path)

        assert applicate == [9001]
        async with db_pool.acquire() as conn:
            esiste = await conn.fetchval(
                "SELECT to_regclass('public.test_migrazione_marker_1') IS NOT NULL"
            )
            assert esiste is True
            riga = await conn.fetchrow(
                "SELECT name FROM schema_migrations WHERE version = 9001"
            )
            assert riga["name"] == "9001_crea_marker"

            await conn.execute("DROP TABLE test_migrazione_marker_1")
            await conn.execute("DELETE FROM schema_migrations WHERE version = 9001")

    @pytest.mark.asyncio
    async def test_una_migrazione_gia_applicata_non_viene_rieseguita(self, db_pool, tmp_path):
        await ensure_schema_migrations_table(db_pool)
        async with db_pool.acquire() as conn:
            await conn.execute("DROP TABLE IF EXISTS test_migrazione_marker_2")
            await conn.execute("DELETE FROM schema_migrations WHERE version = 9002")

        # Una CREATE TABLE senza IF NOT EXISTS: se venisse rieseguita
        # fallirebbe con "relation already exists" — il modo più
        # diretto per dimostrare che la seconda chiamata la salta.
        _scrivi_migrazione(
            tmp_path, "9002_crea_marker.sql", "CREATE TABLE test_migrazione_marker_2 (id INT);"
        )

        prima = await apply_numbered_migrations(db_pool, tmp_path)
        seconda = await apply_numbered_migrations(db_pool, tmp_path)

        assert prima == [9002]
        assert seconda == []  # non riapplicata, non solleva errori

        async with db_pool.acquire() as conn:
            await conn.execute("DROP TABLE test_migrazione_marker_2")
            await conn.execute("DELETE FROM schema_migrations WHERE version = 9002")

    @pytest.mark.asyncio
    async def test_due_runner_concorrenti_non_la_applicano_due_volte(self, schema_vuoto, tmp_path):
        # Schema vuoto: nemmeno schema_migrations esiste prima del
        # gather, la devono creare i runner stessi sotto il lock.
        pool_a = await _pool_su_schema(schema_vuoto)
        pool_b = await _pool_su_schema(schema_vuoto)
        try:
            # INSERT (non CREATE TABLE) come "effetto" osservabile:
            # se il lock advisory non funzionasse, i due runner
            # concorrenti scriverebbero DUE righe invece di una.
            _scrivi_migrazione(
                tmp_path,
                "9003_side_effect.sql",
                "CREATE TABLE IF NOT EXISTS test_migrazione_marker_3 (id SERIAL PRIMARY KEY);"
                "INSERT INTO test_migrazione_marker_3 DEFAULT VALUES;",
            )

            risultati = await asyncio.gather(
                apply_numbered_migrations(pool_a, tmp_path),
                apply_numbered_migrations(pool_b, tmp_path),
            )

            # Un solo runner deve aver applicato la migrazione,
            # l'altro deve averla trovata già fatta al suo turno.
            assert sorted(risultati) == [[], [9003]]

            conteggio = await pool_a.fetchval("SELECT count(*) FROM test_migrazione_marker_3")
            assert conteggio == 1  # non 2: nessuna doppia applicazione
        finally:
            await pool_a.close()
            await pool_b.close()

    @pytest.mark.asyncio
    async def test_una_migrazione_che_fallisce_non_lascia_metà_schema(self, db_pool, tmp_path):
        await ensure_schema_migrations_table(db_pool)
        async with db_pool.acquire() as conn:
            await conn.execute("DROP TABLE IF EXISTS test_migrazione_marker_4")
            await conn.execute("DELETE FROM schema_migrations WHERE version = 9004")

        # Due statement nella stessa migrazione: il primo crea una
        # tabella, il secondo è SQL apposta invalido — deve fallire.
        # Con la transazione, la CREATE TABLE del primo statement
        # deve sparire insieme al fallimento del secondo.
        _scrivi_migrazione(
            tmp_path,
            "9004_fallisce_a_meta.sql",
            "CREATE TABLE test_migrazione_marker_4 (id INT); "
            "QUESTO NON E SQL VALIDO;",
        )

        with pytest.raises(asyncpg.PostgresSyntaxError):
            await apply_numbered_migrations(db_pool, tmp_path)

        async with db_pool.acquire() as conn:
            esiste = await conn.fetchval(
                "SELECT to_regclass('public.test_migrazione_marker_4') IS NOT NULL"
            )
            assert esiste is False  # rollback: la tabella non è rimasta a metà

            riga = await conn.fetchrow(
                "SELECT 1 FROM schema_migrations WHERE version = 9004"
            )
            assert riga is None  # non registrata come applicata

    @pytest.mark.asyncio
    async def test_nessuna_migrazione_da_applicare_restituisce_lista_vuota(
        self, db_pool, tmp_path
    ):
        assert await apply_numbered_migrations(db_pool, tmp_path) == []


@pytest.fixture
async def schema_vuoto():
    """
    Uno schema Postgres nuovo e vuoto (come un database appena creato),
    con il nome da usare come search_path. I lock advisory valgono per
    tutto il database, quindi i runner si mettono in fila lo stesso.
    """
    nome = f"test_migr_{uuid.uuid4().hex[:12]}"
    conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
    await conn.execute(f'CREATE SCHEMA "{nome}"')
    try:
        yield nome
    finally:
        await conn.execute(f'DROP SCHEMA "{nome}" CASCADE')
        await conn.close()


async def _pool_su_schema(schema: str, **opzioni) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=os.environ["DATABASE_URL"],
        min_size=1,
        max_size=2,
        server_settings={"search_path": schema},
        **opzioni,
    )


class TestRunnerSuDatabaseVuoto:
    async def test_quattro_runner_insieme_su_un_database_vuoto_finiscono_tutti(self, schema_vuoto):
        """Nessuna tabella creata prima: anche la base deve stare dentro il lock."""
        pools = [await _pool_su_schema(schema_vuoto) for _ in range(4)]
        try:
            esiti = await asyncio.gather(
                *(run_all_migrations(pool) for pool in pools), return_exceptions=True
            )
            assert esiti == [None, None, None, None]

            versioni = await pools[0].fetch("SELECT version FROM schema_migrations ORDER BY version")
            assert [r["version"] for r in versioni] == [m.version for m in discover_migrations()]
        finally:
            for pool in pools:
                await pool.close()

    async def test_una_migrazione_lenta_non_scade_con_il_command_timeout_del_pool(
        self, schema_vuoto, tmp_path
    ):
        _scrivi_migrazione(tmp_path, "0001_lenta.sql", "SELECT pg_sleep(0.6);")
        pool = await _pool_su_schema(schema_vuoto, command_timeout=0.2)
        try:
            assert await apply_numbered_migrations(pool, tmp_path) == [1]
        finally:
            await pool.close()

    async def test_l_attesa_del_lock_non_scade_con_il_command_timeout_del_pool(
        self, schema_vuoto, tmp_path
    ):
        _scrivi_migrazione(tmp_path, "0001_veloce.sql", "SELECT 1;")
        pool = await _pool_su_schema(schema_vuoto, command_timeout=0.2)
        altro = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
        await altro.execute("SELECT pg_advisory_lock($1)", ADVISORY_LOCK_ID)
        try:
            runner = asyncio.create_task(apply_numbered_migrations(pool, tmp_path))
            await asyncio.sleep(0.6)
            assert not runner.done()  # in attesa del lock, non in timeout

            await altro.execute("SELECT pg_advisory_unlock($1)", ADVISORY_LOCK_ID)
            assert await asyncio.wait_for(runner, timeout=5) == [1]
        finally:
            await altro.close()
            await pool.close()


class TestMigrazioneDb2Reale:
    """La prima migrazione numerata vera del progetto (core/migrations/
    0001_db2_indici.sql): verifica che il file esista, sia valido, e
    produca gli effetti attesi su un database reale."""

    @pytest.mark.asyncio
    async def test_0001_db2_indici_applicata_da_clean_db(self, clean_db):
        # clean_db (tests/conftest.py) chiama già run_all_migrations,
        # che include core/migrations/0001_db2_indici.sql: se questo
        # test passa, la migrazione reale del progetto ha girato
        # senza errori contro lo schema vero.
        async with clean_db.acquire() as conn:
            riga = await conn.fetchrow(
                "SELECT 1 FROM schema_migrations WHERE version = 1"
            )
            assert riga is not None

            assert await conn.fetchval(
                "SELECT to_regclass('public.idx_event_log_guild_role') IS NULL"
            )
            assert await conn.fetchval(
                "SELECT to_regclass('public.idx_event_log_guild_case') IS NULL"
            )
            assert await conn.fetchval(
                "SELECT to_regclass('public.idx_clans_unofficialized_deadline') IS NOT NULL"
            )
            assert await conn.fetchval(
                "SELECT to_regclass('public.idx_leveling_totals_weekly_decay_due') IS NOT NULL"
            )
