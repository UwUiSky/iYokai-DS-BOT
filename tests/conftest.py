"""
tests/conftest.py
====================
Configurazione condivisa dei test. Due responsabilità:

1. Imposta variabili d'ambiente FITTIZIE prima che qualsiasi modulo
   del progetto venga importato. core/config.py valida tutto
   all'import (è la sua caratteristica principale, vedi quel file)
   quindi nei test serve popolare comunque tutte le variabili
   obbligatorie — con valori finti per Discord (non serve un vero
   bot online per testare la logica o il database), ma con un
   DATABASE_URL VERO che punta al database Postgres locale di test
   installato nel container.

2. Fornisce una fixture `db_pool` che apre/chiude un pool reale
   verso quel database per i test che ne hanno bisogno, e una
   fixture `clean_db` che pulisce le tabelle tra un test e l'altro
   così i test non si influenzano a vicenda.
"""

import os

# Deve avvenire PRIMA di ogni import da "core.*": core/config.py
# valida le variabili al momento dell'import del modulo stesso.
os.environ.setdefault("YOKAI_BOT_TOKEN", "test-token-fittizio")
os.environ.setdefault("YOKAI_CREATOR_TOKEN", "test-token-fittizio")
for i in range(1, 6):
    os.environ.setdefault(f"MUSIC_TOKEN_{i}", "test-token-fittizio")
os.environ.setdefault("NSFW_TOKEN", "test-token-fittizio")
os.environ.setdefault("OWNER_ID", "123456789")
os.environ.setdefault("MAIN_GUILD_ID", "987654321")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:testpass@127.0.0.1:5432/iyokai_test",
)
os.environ.setdefault("ENVIRONMENT", "development")

import asyncio

import aiohttp
import asyncpg
import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def db_pool():
    """
    Pool reale, aperto e chiuso per ogni test che lo richiede.
    Scope "function" (default): ogni test parte con un pool pulito,
    niente stato condiviso accidentale tra test diversi.
    """
    pool = await asyncpg.create_pool(
        dsn=os.environ["DATABASE_URL"], min_size=1, max_size=3
    )
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def clean_db(db_pool):
    """
    Applica le migration e SVUOTA le tabelle prima di ogni test.

    DB-1/#25: prima questa fixture duplicava a mano l'elenco di TUTTE
    le run_migrations() dei repository (una copia "tenuta in sync
    manualmente" con core/database.py, il problema che DB-1 doveva
    risolvere) e un elenco fisso di tabelle da svuotare. Ora chiama
    lo STESSO runner usato in produzione (core.migrations.
    run_all_migrations) e legge l'elenco delle tabelle da svuotare
    direttamente da information_schema — nessuna delle due liste va
    più aggiornata a mano quando si aggiunge un repository.
    """
    from core.migrations import run_all_migrations

    # Riusiamo lo stesso pool del test per le migration, invece di
    # farne aprire uno secondo al singleton: gli passiamo il pool
    # direttamente (run_all_migrations prende un pool, non il
    # singleton Database).
    await run_all_migrations(db_pool)

    # Pulizia: TRUNCATE è più veloce di DELETE e resetta i contatori
    # SERIAL, utile perché alcuni test controllano id progressivi.
    # schema_migrations resta ESCLUSA apposta: svuotarla farebbe
    # riapplicare ad ogni test le migrazioni numerate, che non sono
    # tutte sicure da rieseguire (a differenza delle run_migrations()
    # idempotenti di base).
    async with db_pool.acquire() as conn:
        righe = await conn.fetch(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
              AND table_name != 'schema_migrations'
            """
        )
        for riga in righe:
            await conn.execute(f'TRUNCATE TABLE "{riga["table_name"]}" CASCADE')

    yield db_pool


# ============================================================================
# RT-3 — Igiene della suite (PIANO_FIX.md).
#
# Modalità SOLO AVVISO: raccoglie, per ogni test, le aiohttp.ClientSession
# rimaste aperte e le eccezioni di task asyncio mai lette, e le stampa in
# un riepilogo a fine sessione — senza far fallire nessun test. Quando
# l'elenco sarà vuoto, questa fixture va resa bloccante (assert invece di
# solo warning) come richiesto dal piano.
# ============================================================================

_SESSIONI_NON_CHIUSE_PER_TEST: dict[str, int] = {}
_ECCEZIONI_TASK_PER_TEST: dict[str, list[str]] = {}
_ClientSession_init_originale = aiohttp.ClientSession.__init__


@pytest.fixture(autouse=True)
async def _rt3_igiene_risorse(request):
    """
    Traccia le ClientSession aperte durante il singolo test e installa
    un exception handler sul loop del test per catturare le eccezioni
    di task mai lette (quelle che altrimenti finiscono solo nei log
    come "Task exception was never retrieved").
    """
    sessioni_create: list[aiohttp.ClientSession] = []

    def _init_tracciato(self, *args, **kwargs):
        _ClientSession_init_originale(self, *args, **kwargs)
        sessioni_create.append(self)

    aiohttp.ClientSession.__init__ = _init_tracciato

    eccezioni_catturate: list[str] = []
    loop = asyncio.get_running_loop()
    handler_originale = loop.get_exception_handler()

    def _handler_tracciato(loop, context):
        eccezioni_catturate.append(context.get("message", str(context)))
        if handler_originale is not None:
            handler_originale(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(_handler_tracciato)

    try:
        yield
    finally:
        aiohttp.ClientSession.__init__ = _ClientSession_init_originale
        loop.set_exception_handler(handler_originale)

        non_chiuse = [s for s in sessioni_create if not s.closed]
        if non_chiuse:
            _SESSIONI_NON_CHIUSE_PER_TEST[request.node.nodeid] = len(non_chiuse)
        if eccezioni_catturate:
            _ECCEZIONI_TASK_PER_TEST[request.node.nodeid] = eccezioni_catturate


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """RT-3: riepilogo a fine sessione, solo avviso (non fa fallire nulla)."""
    if _SESSIONI_NON_CHIUSE_PER_TEST:
        terminalreporter.section("RT-3: aiohttp.ClientSession non chiuse")
        for nodeid, conteggio in sorted(_SESSIONI_NON_CHIUSE_PER_TEST.items()):
            terminalreporter.write_line(f"  {nodeid}: {conteggio} sessione/i")

    if _ECCEZIONI_TASK_PER_TEST:
        terminalreporter.section("RT-3: eccezioni di task asyncio mai lette")
        for nodeid, messaggi in sorted(_ECCEZIONI_TASK_PER_TEST.items()):
            for messaggio in messaggi:
                terminalreporter.write_line(f"  {nodeid}: {messaggio}")


@pytest.fixture
def reset_premium_registry():
    """
    Fixture riusabile (NON autouse) per i test che devono osservare il
    PremiumRegistry isolato dalle registrazioni fatte dagli altri cog
    già importati nel processo di test. Salva lo stato attuale e lo
    ripristina dopo il test, invece di svuotarlo (svuotarlo romperebbe
    i test successivi nello stesso processo, che si aspettano i moduli
    reali già registrati).
    """
    from core.premium import registry

    stato_originale = dict(registry._modules)
    # I moduli sono oggetti condivisi: la copia del dizionario non basta,
    # va salvata anche la spunta "premium" di ciascuno.
    spunte_originali = {nome: m.is_premium_active for nome, m in stato_originale.items()}
    yield registry
    registry._modules = stato_originale
    for nome, modulo in stato_originale.items():
        modulo.is_premium_active = spunte_originali[nome]
