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
    Import locale (non in cima al file) per essere sicuri che le
    variabili d'ambiente sopra siano già impostate quando i moduli
    core.* vengono importati.
    """
    from core.database import db as db_singleton
    from core.scheduler import run_migrations as scheduler_migrations
    from core.repositories.moderation_repo import (
        run_migrations as moderation_migrations,
    )
    from core.repositories.automod_repo import (
        run_migrations as automod_migrations,
    )
    from core.repositories.ticket_repo import (
        run_migrations as ticket_migrations,
    )
    from core.repositories.voice_temp_repo import (
        run_migrations as voice_temp_migrations,
    )
    from core.repositories.leveling_repo import (
        run_migrations as leveling_migrations,
    )
    from core.repositories.spam_trap_repo import (
        run_migrations as spam_trap_migrations,
    )
    from core.repositories.verify_repo import (
        run_migrations as verify_migrations,
    )
    from core.repositories.role_menu_repo import (
        run_migrations as role_menu_migrations,
    )
    from core.repositories.greetings_repo import (
        run_migrations as greetings_migrations,
    )
    from core.repositories.escalation_repo import (
        run_migrations as escalation_migrations,
    )
    from core.repositories.event_log_repo import (
        run_migrations as event_log_migrations,
    )
    from core.repositories.sticky_message_repo import (
        run_migrations as sticky_message_migrations,
    )
    from core.repositories.suggestion_repo import (
        run_migrations as suggestion_migrations,
    )
    from core.repositories.custom_command_request_repo import (
        run_migrations as custom_command_request_migrations,
    )
    from core.repositories.blacklist_repo import (
        run_migrations as blacklist_migrations,
    )
    from core.repositories.eval_shell_log_repo import (
        run_migrations as eval_shell_log_migrations,
    )
    from core.repositories.feed_subscription_repo import (
        run_migrations as feed_subscription_migrations,
    )
    from core.repositories.custom_webhook_repo import (
        run_migrations as custom_webhook_migrations,
    )
    from core.repositories.music_session_repo import (
        run_migrations as music_session_migrations,
    )
    from core.repositories.twitch_subscription_repo import (
        run_migrations as twitch_subscription_migrations,
    )
    from core.repositories.youtube_subscription_repo import (
        run_migrations as youtube_subscription_migrations,
    )
    from core.repositories.main_radio_repo import (
        run_migrations as main_radio_migrations,
    )
    from core.repositories.backup_repo import run_migrations as backup_migrations
    from core.repositories.backup_mirror_repo import (
        run_migrations as backup_mirror_migrations,
    )
    from core.repositories.backup_user_snapshot_repo import (
        run_migrations as backup_user_snapshot_migrations,
    )
    from core.repositories.restore_oauth_repo import (
        run_migrations as restore_oauth_migrations,
    )
    from core.repositories.level_reward_repo import (
        run_migrations as level_reward_migrations,
    )
    from core.repositories.monthly_winners_repo import (
        run_migrations as monthly_winners_migrations,
    )
    from core.repositories.clan_leaderboard_config_repo import (
        run_migrations as clan_leaderboard_config_migrations,
    )
    from core.repositories.module_subscription_repo import (
        run_migrations as module_subscription_migrations,
    )
    from core.repositories.shop_repo import run_migrations as shop_migrations
    from core.repositories.giveaway_repo import run_migrations as giveaway_migrations
    from core.repositories.guild_clan_repo import (
        run_migrations as guild_clan_migrations,
    )
    from core.repositories.clan_voice_activity_repo import (
        run_migrations as clan_voice_activity_migrations,
    )
    from core.repositories.guild_chest_repo import (
        run_migrations as guild_chest_migrations,
    )
    from core.repositories.guild_premium_repo import (
        run_migrations as guild_premium_migrations,
    )
    from core.repositories.automod_advanced_repo import (
        run_migrations as automod_advanced_migrations,
    )
    from core.repositories.security_repo import run_migrations as security_migrations
    from core.repositories.global_ban_repo import (
        run_migrations as global_ban_migrations,
    )

    # Riusiamo lo stesso pool del test per le migration, invece di
    # farne aprire uno secondo al singleton: gli passiamo il pool
    # direttamente.
    await db_singleton_run_migrations_with_pool(db_pool)
    await scheduler_migrations(db_pool)
    await moderation_migrations(db_pool)
    await automod_migrations(db_pool)
    await ticket_migrations(db_pool)
    await voice_temp_migrations(db_pool)
    await leveling_migrations(db_pool)
    await spam_trap_migrations(db_pool)
    await verify_migrations(db_pool)
    await role_menu_migrations(db_pool)
    await greetings_migrations(db_pool)
    await escalation_migrations(db_pool)
    await event_log_migrations(db_pool)
    await sticky_message_migrations(db_pool)
    await suggestion_migrations(db_pool)
    await custom_command_request_migrations(db_pool)
    await blacklist_migrations(db_pool)
    await eval_shell_log_migrations(db_pool)
    await feed_subscription_migrations(db_pool)
    await custom_webhook_migrations(db_pool)
    await music_session_migrations(db_pool)
    await twitch_subscription_migrations(db_pool)
    await youtube_subscription_migrations(db_pool)
    await main_radio_migrations(db_pool)
    await backup_migrations(db_pool)
    await backup_mirror_migrations(db_pool)
    await backup_user_snapshot_migrations(db_pool)
    await restore_oauth_migrations(db_pool)
    await level_reward_migrations(db_pool)
    await monthly_winners_migrations(db_pool)
    await clan_leaderboard_config_migrations(db_pool)
    await module_subscription_migrations(db_pool)
    await shop_migrations(db_pool)
    await giveaway_migrations(db_pool)
    await guild_clan_migrations(db_pool)
    await clan_voice_activity_migrations(db_pool)
    await guild_chest_migrations(db_pool)
    await guild_premium_migrations(db_pool)
    await automod_advanced_migrations(db_pool)
    await security_migrations(db_pool)
    await global_ban_migrations(db_pool)

    # Pulizia: TRUNCATE è più veloce di DELETE e resetta i contatori
    # SERIAL, utile perché alcuni test controllano id progressivi.
    tables = [
        "scheduled_actions",
        "moderation_cases",
        "moderation_notes",
        "moderation_case_counters",
        "automod_config",
        "automod_last_synced",
        "automod_advanced_config",
        "automod_action_log",
        "security_config",
        "security_action_log",
        "global_ban_log",
        "tickets",
        "ticket_counters",
        "ticket_categories",
        "voice_temp_config",
        "voice_temp_channels",
        "leveling_totals",
        "leveling_activity",
        "spam_trap_config",
        "spam_trap_message_index",
        "spam_trap_appeals",
        "spam_trap_incidents",
        "spam_trap_join_invites",
        "verify_config",
        "verify_attempts",
        "verify_whitelist",
        "verify_blacklist",
        "role_menus",
        "role_menu_options",
        "greetings_config",
        "automod_violations",
        "automod_escalation_config",
        "automod_escalation_steps",
        "event_log",
        "sticky_messages",
        "suggestions",
        "custom_command_requests",
        "user_blacklist",
        "guild_blacklist",
        "eval_shell_log",
        "feed_subscriptions",
        "custom_webhooks",
        "music_sessions",
        "twitch_subscriptions",
        "youtube_subscriptions",
        "main_radio_tracks",
        "main_radio_state",
        "backup_pairs",
        "level_reward_roles",
        "monthly_winners_config",
        "clan_leaderboard_config",
        "module_subscriptions",
        "shop_items",
        "shop_purchases",
        "giveaways",
        "giveaway_entries",
        "clans",
        "clan_members",
        "clan_treasury_ledger",
        "clan_monthly_xp",
        "clan_voice_activity",
        "guild_chest",
        "guild_chest_ledger",
        "guild_premium_purchases",
        "guild_premium_status",
        "backup_jobs",
        "backup_mirror_webhooks",
        "backup_user_snapshots",
        "restore_oauth_tokens",
        "guild_config",
        "guild_config_history",
        "premium_whitelist",
        "premium_module_flags",
        "premium_toggle_history",
    ]
    async with db_pool.acquire() as conn:
        for table in tables:
            exists = await conn.fetchval(
                "SELECT to_regclass($1) IS NOT NULL", f"public.{table}"
            )
            if exists:
                await conn.execute(f"TRUNCATE TABLE {table} CASCADE")

    yield db_pool


async def db_singleton_run_migrations_with_pool(pool):
    """
    core.database.Database.run_migrations() usa self.pool, che
    richiede connect() già chiamato sul singleton. Nei test non
    vogliamo aprire un secondo pool globale: eseguiamo lo stesso SQL
    delle migration passando il pool di test direttamente.
    Tenuto in sync manualmente con core/database.py.run_migrations().
    """
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id        BIGINT PRIMARY KEY,
            modules         JSONB NOT NULL DEFAULT '{}'::jsonb,
            prefix          TEXT,
            language        TEXT NOT NULL DEFAULT 'it',
            setup_completed BOOLEAN NOT NULL DEFAULT FALSE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS premium_whitelist (
            guild_id  BIGINT PRIMARY KEY,
            added_by  BIGINT NOT NULL,
            reason    TEXT,
            added_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS premium_module_flags (
            module_name TEXT PRIMARY KEY,
            is_active   BOOLEAN NOT NULL DEFAULT FALSE,
            updated_by  BIGINT,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


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
    yield registry
    registry._modules = stato_originale
