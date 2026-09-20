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

from datetime import datetime, timedelta, timezone

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
        "SELECT executed FROM scheduled_actions WHERE id = $1", action_id
    )
    assert row["executed"] is False


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
