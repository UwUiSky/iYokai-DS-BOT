"""
tests/test_scheduler.py
==========================
Test dello scheduler CONTRO IL DATABASE VERO (vedi tests/conftest.py:
la fixture clean_db apre un pool reale su PostgreSQL locale). Non
sono mock: se una query SQL in core/scheduler.py ha un errore di
sintassi o di nome colonna, questi test falliscono per davvero, come
farebbero in produzione.

Quello che NON testano: la connessione a Discord, perché lo scheduler
in sé non ne ha bisogno — gli handler la useranno, ma qui li
sostituiamo con funzioni finte che registrano solo "sono stato
chiamato con questi argomenti".
"""

import asyncio
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

from core.scheduler import Scheduler


@pytest.mark.asyncio
async def test_azione_scaduta_viene_eseguita(clean_db, monkeypatch):
    # Sostituiamo core.database.db.pool con il pool di test, perché
    # Scheduler._run_due_actions() fa "from core.database import db"
    # e usa db.pool internamente.
    import core.database as database_module

    class _FakeDbWithPool:
        pool = clean_db

    monkeypatch.setattr(database_module, "db", _FakeDbWithPool())

    scheduler = Scheduler()
    chiamate = []

    async def handler_finto(guild_id, user_id, payload):
        chiamate.append((guild_id, user_id, payload))

    scheduler.register_handler("test_action", handler_finto)

    # Pianifichiamo un'azione nel PASSATO, così risulta già scaduta.
    passato = datetime.now(timezone.utc) - timedelta(seconds=5)
    action_id = await scheduler.schedule(
        guild_id=111,
        user_id=222,
        action_type="test_action",
        execute_at=passato,
        payload={"motivo": "test"},
    )
    assert isinstance(action_id, int)

    await scheduler._run_due_actions()

    assert chiamate == [(111, 222, {"motivo": "test"})]

    # L'azione deve risultare marcata come eseguita nel DB, non solo
    # "l'handler è stato chiamato" — altrimenti al giro successivo
    # verrebbe rieseguita di nuovo.
    row = await clean_db.fetchrow(
        "SELECT executed FROM scheduled_actions WHERE id = $1", action_id
    )
    assert row["executed"] is True


@pytest.mark.asyncio
async def test_azione_futura_non_viene_eseguita(clean_db, monkeypatch):
    import core.database as database_module

    class _FakeDbWithPool:
        pool = clean_db

    monkeypatch.setattr(database_module, "db", _FakeDbWithPool())

    scheduler = Scheduler()
    chiamate = []

    async def handler_finto(guild_id, user_id, payload):
        chiamate.append((guild_id, user_id))

    scheduler.register_handler("test_action", handler_finto)

    futuro = datetime.now(timezone.utc) + timedelta(hours=1)
    await scheduler.schedule(
        guild_id=111, user_id=222, action_type="test_action", execute_at=futuro
    )

    await scheduler._run_due_actions()

    # Non deve essere stata eseguita: è pianificata tra un'ora, non ora.
    assert chiamate == []


@pytest.mark.asyncio
async def test_cancel_impedisce_esecuzione(clean_db, monkeypatch):
    import core.database as database_module

    class _FakeDbWithPool:
        pool = clean_db

    monkeypatch.setattr(database_module, "db", _FakeDbWithPool())

    scheduler = Scheduler()
    chiamate = []

    async def handler_finto(guild_id, user_id, payload):
        chiamate.append((guild_id, user_id))

    scheduler.register_handler("test_action", handler_finto)

    passato = datetime.now(timezone.utc) - timedelta(seconds=5)
    action_id = await scheduler.schedule(
        guild_id=111, user_id=222, action_type="test_action", execute_at=passato
    )

    # Annulliamo PRIMA che il loop la esegua (simula: un admin fa
    # /unban manuale prima che scada il tempban automatico).
    await scheduler.cancel(action_id)

    await scheduler._run_due_actions()

    assert chiamate == []


@pytest.mark.asyncio
async def test_handler_mancante_non_crasha_il_loop(clean_db, monkeypatch):
    # Se arriva un'azione con un action_type per cui nessun handler è
    # registrato (es. un cog è stato rimosso ma la riga era rimasta
    # nel DB), il loop deve loggare e continuare, non esplodere.
    import core.database as database_module

    class _FakeDbWithPool:
        pool = clean_db

    monkeypatch.setattr(database_module, "db", _FakeDbWithPool())

    scheduler = Scheduler()  # nessun handler registrato

    passato = datetime.now(timezone.utc) - timedelta(seconds=5)
    await scheduler.schedule(
        guild_id=111,
        user_id=222,
        action_type="tipo_sconosciuto",
        execute_at=passato,
    )

    # Non deve sollevare eccezioni.
    await scheduler._run_due_actions()


@pytest.mark.asyncio
async def test_handler_che_fallisce_non_marca_come_eseguita(clean_db, monkeypatch):
    # Se l'handler solleva un'eccezione (es. Discord momentaneamente
    # irraggiungibile), l'azione NON deve essere marcata come
    # eseguita: va ritentata al giro successivo, altrimenti un
    # tempban potrebbe non essere mai revocato per un errore
    # temporaneo.
    import core.database as database_module

    class _FakeDbWithPool:
        pool = clean_db

    monkeypatch.setattr(database_module, "db", _FakeDbWithPool())

    scheduler = Scheduler()

    async def handler_che_fallisce(guild_id, user_id, payload):
        raise RuntimeError("simulazione di un errore temporaneo")

    scheduler.register_handler("test_action", handler_che_fallisce)

    passato = datetime.now(timezone.utc) - timedelta(seconds=5)
    action_id = await scheduler.schedule(
        guild_id=111, user_id=222, action_type="test_action", execute_at=passato
    )

    await scheduler._run_due_actions()

    row = await clean_db.fetchrow(
        "SELECT executed, attempts, failed_reason FROM scheduled_actions WHERE id = $1", action_id
    )
    assert row["executed"] is False
    assert row["attempts"] == 1
    assert row["failed_reason"] is None  # non ancora fallita: verrà riprovata


def _collega_pool_di_test(monkeypatch, clean_db) -> None:
    import core.database as database_module

    class _FakeDbWithPool:
        pool = clean_db

    monkeypatch.setattr(database_module, "db", _FakeDbWithPool())


@pytest.mark.asyncio
async def test_list_pending_for_user_filtra_per_utente_e_tipo(clean_db, monkeypatch):
    _collega_pool_di_test(monkeypatch, clean_db)
    scheduler = Scheduler()
    futuro = datetime.now(timezone.utc) + timedelta(days=1)

    await scheduler.schedule(guild_id=1, user_id=100, action_type="reminder", execute_at=futuro)
    await scheduler.schedule(guild_id=1, user_id=200, action_type="reminder", execute_at=futuro)
    await scheduler.schedule(guild_id=1, user_id=100, action_type="altro_tipo", execute_at=futuro)

    risultato = await scheduler.list_pending_for_user(100, "reminder")

    assert len(risultato) == 1
    assert risultato[0]["guild_id"] == 1


@pytest.mark.asyncio
async def test_list_pending_for_user_esclude_azioni_gia_eseguite(clean_db, monkeypatch):
    _collega_pool_di_test(monkeypatch, clean_db)
    scheduler = Scheduler()
    passato = datetime.now(timezone.utc) - timedelta(seconds=5)

    scheduler.register_handler("reminder", lambda g, u, p: None)
    action_id = await scheduler.schedule(
        guild_id=1, user_id=100, action_type="reminder", execute_at=passato
    )
    await clean_db.execute(
        "UPDATE scheduled_actions SET executed = TRUE WHERE id = $1", action_id
    )

    risultato = await scheduler.list_pending_for_user(100, "reminder")
    assert risultato == []


@pytest.mark.asyncio
async def test_list_pending_for_user_ordina_per_data_di_esecuzione(clean_db, monkeypatch):
    _collega_pool_di_test(monkeypatch, clean_db)
    scheduler = Scheduler()
    ora = datetime.now(timezone.utc)

    id_lontano = await scheduler.schedule(
        guild_id=1, user_id=100, action_type="reminder", execute_at=ora + timedelta(days=5)
    )
    id_vicino = await scheduler.schedule(
        guild_id=1, user_id=100, action_type="reminder", execute_at=ora + timedelta(hours=1)
    )

    risultato = await scheduler.list_pending_for_user(100, "reminder")

    assert [r["id"] for r in risultato] == [id_vicino, id_lontano]


@pytest.mark.asyncio
async def test_list_pending_for_user_include_il_payload_deserializzato(clean_db, monkeypatch):
    _collega_pool_di_test(monkeypatch, clean_db)
    scheduler = Scheduler()
    futuro = datetime.now(timezone.utc) + timedelta(days=1)

    await scheduler.schedule(
        guild_id=1, user_id=100, action_type="reminder", execute_at=futuro,
        payload={"message": "Comprare il latte"},
    )

    risultato = await scheduler.list_pending_for_user(100, "reminder")
    assert risultato[0]["payload"] == {"message": "Comprare il latte"}


@pytest.mark.asyncio
async def test_get_pending_action_restituisce_i_dati_corretti(clean_db, monkeypatch):
    _collega_pool_di_test(monkeypatch, clean_db)
    scheduler = Scheduler()
    futuro = datetime.now(timezone.utc) + timedelta(days=1)

    action_id = await scheduler.schedule(
        guild_id=1, user_id=100, action_type="reminder", execute_at=futuro,
        payload={"message": "Test"},
    )

    azione = await scheduler.get_pending_action(action_id)

    assert azione["user_id"] == 100
    assert azione["guild_id"] == 1
    assert azione["executed"] is False
    assert azione["payload"] == {"message": "Test"}


@pytest.mark.asyncio
async def test_get_pending_action_inesistente_restituisce_none(clean_db, monkeypatch):
    _collega_pool_di_test(monkeypatch, clean_db)
    scheduler = Scheduler()
    assert await scheduler.get_pending_action(999999) is None


@pytest.mark.asyncio
async def test_list_pending_for_guild_filtra_per_server_e_tipo(clean_db, monkeypatch):
    _collega_pool_di_test(monkeypatch, clean_db)
    scheduler = Scheduler()
    futuro = datetime.now(timezone.utc) + timedelta(days=1)

    await scheduler.schedule(guild_id=100, user_id=1, action_type="scheduled_message", execute_at=futuro)
    await scheduler.schedule(guild_id=200, user_id=1, action_type="scheduled_message", execute_at=futuro)
    await scheduler.schedule(guild_id=100, user_id=1, action_type="altro_tipo", execute_at=futuro)

    risultato = await scheduler.list_pending_for_guild(100, "scheduled_message")

    assert len(risultato) == 1


@pytest.mark.asyncio
async def test_list_pending_for_guild_mostra_azioni_di_utenti_diversi(clean_db, monkeypatch):
    # Diversamente da list_pending_for_user: qui conta il SERVER, non
    # chi ha creato l'azione - un admin deve vedere tutti i messaggi
    # programmati del proprio server, non solo i propri.
    _collega_pool_di_test(monkeypatch, clean_db)
    scheduler = Scheduler()
    futuro = datetime.now(timezone.utc) + timedelta(days=1)

    await scheduler.schedule(guild_id=100, user_id=1, action_type="scheduled_message", execute_at=futuro)
    await scheduler.schedule(guild_id=100, user_id=2, action_type="scheduled_message", execute_at=futuro)

    risultato = await scheduler.list_pending_for_guild(100, "scheduled_message")

    assert len(risultato) == 2
    assert {r["user_id"] for r in risultato} == {1, 2}


class TestRegisterHandler:
    """
    Stessa correzione già fatta in PremiumRegistry.register()
    (tests/test_premium_registry.py): trovato con un test reale su
    un cog vero che bot.reload_extension() rompeva QUALSIASI cog
    con un handler scheduler, perché register_handler() sollevava un
    errore alla seconda registrazione dello stesso action_type — cosa
    che succede sempre a un reload, dato che setup() lo richiama di
    nuovo con un NUOVO bound method (nuova istanza del cog).
    """

    def test_primo_register_funziona(self):
        scheduler = Scheduler()

        async def handler(guild_id, user_id, payload):
            pass

        scheduler.register_handler("test_action", handler)
        assert "test_action" in scheduler._handlers

    def test_re_register_stesso_metodo_non_solleva(self):
        class Cog:
            async def handle_azione(self, guild_id, user_id, payload):
                pass

        scheduler = Scheduler()
        prima_istanza = Cog()
        seconda_istanza = Cog()  # come dopo un reload: nuova istanza, stesso metodo

        scheduler.register_handler("test_action", prima_istanza.handle_azione)
        scheduler.register_handler("test_action", seconda_istanza.handle_azione)  # non deve sollevare

        # L'handler attivo ora è quello della SECONDA istanza, non
        # più agganciato a quella vecchia (che il reload ha distrutto).
        assert scheduler._handlers["test_action"].__self__ is seconda_istanza

    def test_re_register_metodo_di_classe_diversa_solleva(self):
        class CogA:
            async def handle_azione(self, guild_id, user_id, payload):
                pass

        class CogB:
            async def handle_azione(self, guild_id, user_id, payload):
                pass

        scheduler = Scheduler()
        scheduler.register_handler("test_action", CogA().handle_azione)

        with pytest.raises(ValueError):
            scheduler.register_handler("test_action", CogB().handle_azione)

    def test_action_type_diversi_non_si_scontrano(self):
        scheduler = Scheduler()

        async def handler_a(guild_id, user_id, payload):
            pass

        async def handler_b(guild_id, user_id, payload):
            pass

        scheduler.register_handler("azione_a", handler_a)
        scheduler.register_handler("azione_b", handler_b)

        assert "azione_a" in scheduler._handlers
        assert "azione_b" in scheduler._handlers


# ---------------------------------------------------------------------------
# BUG-8: lo scheduler non deve fermarsi per sempre
# ---------------------------------------------------------------------------


def _collega_db_finto(monkeypatch, clean_db):
    import core.database as database_module

    class _FakeDbWithPool:
        pool = clean_db

    monkeypatch.setattr(database_module, "db", _FakeDbWithPool())


async def _fai_passare_il_tempo(pool) -> None:
    """Simula l'attesa: i tentativi rimandati diventano di nuovo scaduti."""
    await pool.execute(
        "UPDATE scheduled_actions SET next_attempt_at = now() - interval '1 second' "
        "WHERE next_attempt_at IS NOT NULL"
    )


async def _riga(pool, action_id):
    return await pool.fetchrow(
        "SELECT executed, attempts, next_attempt_at, failed_reason, execute_at "
        "FROM scheduled_actions WHERE id = $1",
        action_id,
    )


@pytest.mark.asyncio
async def test_un_errore_nel_giro_non_ferma_il_loop_e_la_pausa_cresce(monkeypatch, caplog):
    import core.scheduler as scheduler_module

    pause = []

    async def _sleep_finto(secondi):
        pause.append(secondi)

    monkeypatch.setattr(scheduler_module.asyncio, "sleep", _sleep_finto)
    scheduler = Scheduler()

    async def giro_che_esplode():
        raise ConnectionError("database irraggiungibile")

    monkeypatch.setattr(scheduler, "_run_due_actions", giro_che_esplode)

    await scheduler._giro()  # non deve sollevare: il loop tasks.loop non si ferma
    await scheduler._giro()
    await scheduler._giro()

    assert "database irraggiungibile" in caplog.text
    assert pause == sorted(pause) and len(set(pause)) == 3  # attesa crescente
    for _ in range(20):
        await scheduler._giro()
    assert max(pause) == scheduler_module.PAUSA_MASSIMA_ERRORE_SECONDI

    async def giro_riuscito():
        return None

    monkeypatch.setattr(scheduler, "_run_due_actions", giro_riuscito)
    pause.clear()
    await scheduler._giro()
    assert pause == []  # database tornato: nessuna pausa, contatore azzerato
    assert scheduler._errori_di_fila == 0


# ---------------------------------------------------------------------------
# BUG-27: nuovi tentativi con attesa crescente, una transazione per azione
# ---------------------------------------------------------------------------


def test_attesa_prima_di_riprovare_cresce_fino_al_massimo():
    from core.scheduler import ATTESE_RIPROVA, attesa_prima_di_riprovare

    attese = [attesa_prima_di_riprovare(n) for n in range(1, 12)]
    assert attese[0] == timedelta(minutes=1)
    assert attese == sorted(attese)
    assert attese[-1] == ATTESE_RIPROVA[-1] == timedelta(hours=6)


@pytest.mark.asyncio
async def test_azione_senza_handler_viene_rimandata_e_non_blocca_la_coda(clean_db, monkeypatch):
    _collega_db_finto(monkeypatch, clean_db)
    scheduler = Scheduler()
    chiamate = []

    async def handler_finto(guild_id, user_id, payload):
        chiamate.append(user_id)

    scheduler.register_handler("noto", handler_finto)
    passato = datetime.now(timezone.utc) - timedelta(seconds=5)
    orfana = await scheduler.schedule(1, 10, "tipo_senza_handler", passato)
    valida = await scheduler.schedule(1, 20, "noto", passato + timedelta(seconds=1))

    await scheduler._run_due_actions()

    assert chiamate == [20]  # l'azione orfana non ha bloccato quella valida
    riga = await _riga(clean_db, orfana)
    assert riga["executed"] is False
    assert riga["failed_reason"] is None  # non è persa: verrà riprovata
    assert riga["attempts"] == 1
    assert riga["next_attempt_at"] > datetime.now(timezone.utc)
    assert (await _riga(clean_db, valida))["executed"] is True


@pytest.mark.asyncio
async def test_azione_senza_handler_viene_eseguita_quando_l_handler_arriva(clean_db, monkeypatch):
    """Un cog che non si carica a un avvio non fa perdere i tempban scaduti."""
    _collega_db_finto(monkeypatch, clean_db)
    scheduler = Scheduler()
    passato = datetime.now(timezone.utc) - timedelta(days=3)  # bot spento per giorni
    azione = await scheduler.schedule(1, 10, "tempban_scaduto", passato, {"reason": "x"})

    await scheduler._run_due_actions()
    await scheduler._run_due_actions()  # troppo presto: non è un nuovo tentativo
    assert (await _riga(clean_db, azione))["attempts"] == 1

    chiamate = []

    async def handler(guild_id, user_id, payload):
        chiamate.append((guild_id, user_id, payload))

    scheduler.register_handler("tempban_scaduto", handler)  # il cog ora è caricato
    await _fai_passare_il_tempo(clean_db)
    await scheduler._run_due_actions()

    assert chiamate == [(1, 10, {"reason": "x"})]
    riga = await _riga(clean_db, azione)
    assert riga["executed"] is True and riga["failed_reason"] is None
    assert riga["execute_at"] == passato  # la scadenza originale non viene toccata


@pytest.mark.asyncio
async def test_handler_che_solleva_sempre_finisce_failed_dopo_il_massimo_dei_tentativi(
    clean_db, monkeypatch, caplog
):
    from core.scheduler import MAX_TENTATIVI

    _collega_db_finto(monkeypatch, clean_db)
    scheduler = Scheduler()
    chiamate = []

    async def handler_rotto(guild_id, user_id, payload):
        chiamate.append(user_id)
        raise RuntimeError("canale sparito")

    scheduler.register_handler("rotto", handler_rotto)
    azione = await scheduler.schedule(1, 10, "rotto", datetime.now(timezone.utc))

    for _ in range(MAX_TENTATIVI - 1):
        await scheduler._run_due_actions()
        assert (await _riga(clean_db, azione))["failed_reason"] is None
        await _fai_passare_il_tempo(clean_db)
    caplog.clear()
    await scheduler._run_due_actions()

    riga = await _riga(clean_db, azione)
    assert riga["attempts"] == MAX_TENTATIVI == len(chiamate)
    assert "RuntimeError: canale sparito" in riga["failed_reason"]
    assert riga["executed"] is False
    assert any(
        r.levelname == "ERROR" and "abbandonata" in r.getMessage() for r in caplog.records
    )

    await _fai_passare_il_tempo(clean_db)
    await scheduler._run_due_actions()
    assert len(chiamate) == MAX_TENTATIVI  # failed: non viene più riprovata


@pytest.mark.asyncio
async def test_azioni_che_falliscono_sempre_non_affamano_quelle_piu_nuove(clean_db, monkeypatch):
    from core.scheduler import AZIONI_PER_GIRO

    _collega_db_finto(monkeypatch, clean_db)
    scheduler = Scheduler()
    riuscite = []

    async def handler_rotto(guild_id, user_id, payload):
        raise RuntimeError("sempre rotto")

    async def handler_buono(guild_id, user_id, payload):
        riuscite.append(user_id)

    scheduler.register_handler("rotto", handler_rotto)
    scheduler.register_handler("buono", handler_buono)
    vecchio = datetime.now(timezone.utc) - timedelta(hours=1)
    for n in range(AZIONI_PER_GIRO + 10):
        await scheduler.schedule(1, n, "rotto", vecchio)
    await scheduler.schedule(1, 999, "buono", datetime.now(timezone.utc))

    await scheduler._run_due_actions()
    assert riuscite == []  # il primo giro è pieno di azioni rotte più vecchie
    await scheduler._run_due_actions()
    assert riuscite == [999]  # le rotte sono rimandate: non occupano più il giro


@pytest.mark.asyncio
async def test_errore_del_database_su_una_azione_non_fa_rieseguire_le_precedenti(
    clean_db, monkeypatch
):
    """Ogni azione ha la sua transazione: un errore non annulla i flag già scritti."""
    _collega_db_finto(monkeypatch, clean_db)
    scheduler = Scheduler()
    chiamate = []

    async def handler(guild_id, user_id, payload):
        chiamate.append(user_id)

    scheduler.register_handler("noto", handler)
    base = datetime.now(timezone.utc) - timedelta(minutes=1)
    for n, user_id in enumerate((10, 20, 30)):
        await scheduler.schedule(1, user_id, "noto", base + timedelta(seconds=n))

    # Errore vero del database quando si segna eseguita l'azione di 20.
    await clean_db.execute(
        """
        CREATE OR REPLACE FUNCTION test_bug27_esplode() RETURNS trigger AS $$
        BEGIN
            IF NEW.user_id = 20 AND NEW.executed THEN
                RAISE EXCEPTION 'errore finto del database';
            END IF;
            RETURN NEW;
        END $$ LANGUAGE plpgsql;
        CREATE TRIGGER test_bug27_trigger BEFORE UPDATE ON scheduled_actions
            FOR EACH ROW EXECUTE FUNCTION test_bug27_esplode();
        """
    )
    try:
        with pytest.raises(asyncpg.PostgresError):
            await scheduler._run_due_actions()
    finally:
        await clean_db.execute(
            "DROP TRIGGER test_bug27_trigger ON scheduled_actions;"
            "DROP FUNCTION test_bug27_esplode();"
        )
    assert chiamate == [10, 20]

    await scheduler._run_due_actions()

    assert chiamate.count(10) == 1  # era già committata: non riparte
    assert chiamate == [10, 20, 20, 30]


@pytest.mark.asyncio
async def test_cancelled_error_esce_dallo_scheduler_e_non_conta_come_tentativo(
    clean_db, monkeypatch
):
    _collega_db_finto(monkeypatch, clean_db)
    scheduler = Scheduler()

    async def handler_cancellato(guild_id, user_id, payload):
        raise asyncio.CancelledError()

    scheduler.register_handler("lento", handler_cancellato)
    azione = await scheduler.schedule(1, 10, "lento", datetime.now(timezone.utc))

    with pytest.raises(asyncio.CancelledError):
        await scheduler._giro()

    riga = await _riga(clean_db, azione)
    assert riga["attempts"] == 0 and riga["failed_reason"] is None and riga["executed"] is False
