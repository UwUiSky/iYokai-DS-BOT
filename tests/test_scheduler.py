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
