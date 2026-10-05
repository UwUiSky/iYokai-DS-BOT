"""
core/database.py
==================
Layer UNICO di accesso al database. Regola ferrea del progetto:

    NESSUN cog scrive mai SQL direttamente.
    Ogni query passa da un metodo di questa classe (o di una classe
    "repository" simile, quando il file crescerà — vedi nota in fondo).

Perché questa regola è importante qui in particolare: è la stessa
ragione per cui, nella discussione di progetto, il passaggio da
SQLite a PostgreSQL era rischioso SOLO se le query erano sparse nei
cog. Con questo layer in mezzo, il giorno in cui cambierà qualcosa
nello schema del database (es. partizionamento di una tabella),
si tocca questo file, non quaranta cog diversi.

Connection pool
-----------------
asyncpg gestisce da solo un pool di connessioni riutilizzabili.
Non è mai necessario aprire/chiudere una connessione manualmente nei
cog: si prende una connessione dal pool solo per la durata della
singola query, e torna disponibile subito dopo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

import asyncpg

from core.bounded_cache import BoundedCache
from core.config import config


@dataclass(frozen=True)
class ConfigHistoryEntry:
    id: int
    guild_id: int
    changed_by: int | None
    change_type: str  # "module" | "setting"
    key_name: str
    old_value: object  # già deserializzato (bool, int, str, None...)
    new_value: object
    created_at: datetime


class Database:
    """
    Wrapper attorno al pool di connessioni.
    Un'unica istanza condivisa da tutto il bot (vedi `db` in fondo).
    """

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None
        # Cache della colonna "modules" per server (BACKLOG.md §1,
        # priorità accettata dopo l'analisi delle proposte esterne):
        # ogni cog che condivide on_message/on_raw_reaction_add
        # (leveling, spam_trap, verify, role_menus, greetings — e in
        # crescita) chiamava is_module_active_for_guild() con una
        # query separata ad ogni singolo evento. Un dizionario intero
        # per chiave (non una entry per singolo modulo) così più cog
        # che controllano moduli diversi per LO STESSO server
        # condividono la stessa riga già in cache, invece di avere
        # una entry ciascuno.
        self._modules_cache: BoundedCache[int, dict] = BoundedCache(max_size=10_000)

    async def connect(self) -> None:
        """
        Apre il pool. Va chiamato UNA volta, all'avvio del bot
        (vedi main.py). Se viene chiamato due volte per errore,
        solleva un'eccezione chiara invece di creare due pool
        silenziosamente.
        """
        if self._pool is not None:
            raise RuntimeError("Il pool del database è già aperto.")

        self._pool = await asyncpg.create_pool(
            dsn=config.DATABASE_URL,
            min_size=config.DB_POOL_MIN,
            max_size=config.DB_POOL_MAX,
            # Timeout di comando: se una query impiega più di 30s,
            # meglio fallire rumorosamente che bloccare il bot.
            command_timeout=30,
        )

    async def close(self) -> None:
        """Chiude il pool in modo pulito. Va chiamato allo spegnimento."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        """
        Accesso diretto al pool per query non ancora "wrappate" in
        un metodo dedicato. Va usato con parsimonia: se un cog usa
        `db.pool.fetch(...)` direttamente più di una volta per la
        stessa cosa, quella query merita il suo metodo qui sotto.
        """
        if self._pool is None:
            raise RuntimeError(
                "Il pool del database non è ancora stato aperto. "
                "connect() va chiamato prima di qualsiasi query."
            )
        return self._pool

    # ================================================================
    # SCHEMA — creazione tabelle e migrazioni
    # ================================================================
    # DB-1/#25: la logica vera vive in core/migrations.py (tabelle di
    # base idempotenti, poi le run_migrations() di ogni repository,
    # poi le migrazioni numerate non ancora applicate) — UNICO punto
    # usato sia qui in produzione sia da tests/conftest.py, non due
    # copie tenute "in sync manualmente" come prima di DB-1.
    async def run_migrations(self) -> None:
        from core.migrations import run_all_migrations
        await run_all_migrations(self.pool)

    # ================================================================
    # Guild config — metodi di base
    # ================================================================
    async def ensure_guild_exists(self, guild_id: int) -> None:
        """
        Crea la riga di configurazione per un server se non esiste
        già. Chiamato da on_guild_join. ON CONFLICT DO NOTHING evita
        una race condition se per qualche motivo viene chiamato due
        volte in rapida successione.
        """
        await self.pool.execute(
            """
            INSERT INTO guild_config (guild_id)
            VALUES ($1)
            ON CONFLICT (guild_id) DO NOTHING
            """,
            guild_id,
        )

    async def get_guild_joined_at(self, guild_id: int) -> datetime | None:
        """
        Approssimazione della data di join del bot nel server: il
        momento in cui la riga di `guild_config` è stata creata per
        la prima volta (`ensure_guild_exists`, chiamato da
        `on_guild_join`, non la sovrascrive più su conflitto — vedi
        quel metodo). Usata dal doppio cancello temporale del
        premium via cassa (SPEC.md §15.15). None se il server non ha
        ancora una riga di configurazione.
        """
        return await self.pool.fetchval(
            "SELECT created_at FROM guild_config WHERE guild_id = $1", guild_id
        )

    async def is_module_active_for_guild(
        self, guild_id: int, module_name: str
    ) -> bool:
        """
        Controlla se un server ha attivato un certo modulo dal
        pannello di setup. Usato dal check runtime dei cog per
        decidere se rispondere o ignorare un comando o un evento
        (on_message, on_raw_reaction_add, ecc.).

        Passa dalla cache dei moduli per server (invalidata
        esplicitamente da set_module_active_for_guild, non a
        scadenza temporale — non c'è modo che diventi stantia senza
        che qualcuno l'abbia già aggiornata).
        """
        modules = self._modules_cache.get(guild_id)
        if modules is None:
            row = await self.pool.fetchrow(
                "SELECT modules FROM guild_config WHERE guild_id = $1",
                guild_id,
            )
            # asyncpg non ha un codec JSONB registrato in questo
            # progetto (vedi get_guild_setting più sotto, stesso
            # pattern): il campo torna come stringa JSON grezza, va
            # deserializzato esplicitamente.
            modules = json.loads(row["modules"]) if row is not None else {}
            self._modules_cache.set(guild_id, modules)

        return bool(modules.get(module_name, False))

    async def set_module_active_for_guild(
        self, guild_id: int, module_name: str, active: bool, changed_by: int | None = None
    ) -> None:
        """
        Attiva/disattiva un modulo per un server specifico. Crea la
        riga di config se non esiste ancora (server nuovo che non ha
        ancora ricevuto on_guild_join, capita nei test).

        changed_by è opzionale (default None) per restare compatibile
        con i chiamanti esistenti che non lo passano ancora — ogni
        scrittura viene comunque registrata nello storico
        (guild_config_history, BACKLOG.md §11 Config Diff & Rollback),
        anche con changed_by NULL se l'autore non è noto al chiamante.
        """
        await self.ensure_guild_exists(guild_id)

        # Leggiamo il valore PRIMA di sovrascriverlo: senza questo,
        # lo storico non avrebbe nulla da confrontare per un diff.
        old_row = await self.pool.fetchrow(
            "SELECT (modules -> $2)::boolean AS old_value FROM guild_config WHERE guild_id = $1",
            guild_id,
            module_name,
        )
        old_value = old_row["old_value"] if old_row is not None else None

        await self.pool.execute(
            """
            UPDATE guild_config
            SET modules = jsonb_set(modules, ARRAY[$2], to_jsonb($3::boolean)),
                updated_at = now()
            WHERE guild_id = $1
            """,
            guild_id,
            module_name,
            active,
        )
        # Invalida (non aggiorna in-place): alla prossima lettura la
        # cache si ripopola dal DB da zero, così non c'è mai il
        # rischio che una scrittura parziale lasci la cache
        # disallineata da quello che è realmente su disco.
        self._modules_cache.delete(guild_id)

        await self._record_config_change(
            guild_id, changed_by, "module", module_name, old_value, active
        )

    # ================================================================
    # Guild settings — configurazione libera per-modulo (JSONB)
    # ================================================================
    # A differenza di "modules" (solo True/False per ogni modulo),
    # "settings" tiene valori arbitrari: l'ID di un canale, un testo,
    # un numero. Ogni modulo usa una chiave propria (es.
    # "report_channel_id", "mute_role_id") per non calpestare le
    # impostazioni degli altri moduli.
    async def get_guild_setting(
        self, guild_id: int, key: str, default=None
    ):
        row = await self.pool.fetchrow(
            "SELECT settings -> $2 AS value FROM guild_config WHERE guild_id = $1",
            guild_id,
            key,
        )
        if row is None or row["value"] is None:
            return default
        # asyncpg restituisce il JSONB già come stringa JSON; lo
        # decodifichiamo per dare al chiamante il tipo Python atteso
        # (int, str, bool...) invece di una stringa JSON grezza.
        valore = json.loads(row["value"])
        # BUG-31: un `null` salvato vale "chiave assente", come se la
        # riga non l'avesse: i cog non si aspettano None al posto del
        # default (es. una lista).
        return default if valore is None else valore

    async def set_guild_setting(
        self, guild_id: int, key: str, value, changed_by: int | None = None
    ) -> None:
        await self.ensure_guild_exists(guild_id)

        old_row = await self.pool.fetchrow(
            "SELECT settings -> $2 AS value FROM guild_config WHERE guild_id = $1",
            guild_id,
            key,
        )
        old_value = json.loads(old_row["value"]) if old_row and old_row["value"] is not None else None

        await self.pool.execute(
            """
            UPDATE guild_config
            SET settings = jsonb_set(settings, ARRAY[$2], $3::jsonb),
                updated_at = now()
            WHERE guild_id = $1
            """,
            guild_id,
            key,
            json.dumps(value),
        )

        await self._record_config_change(
            guild_id, changed_by, "setting", key, old_value, value
        )

    # ================================================================
    # Config Diff & Rollback (BACKLOG.md §11, estensione di SPEC.md §2.7)
    # ================================================================
    async def _record_config_change(
        self,
        guild_id: int,
        changed_by: int | None,
        change_type: str,
        key_name: str,
        old_value,
        new_value,
    ) -> None:
        await self.pool.execute(
            """
            INSERT INTO guild_config_history
                (guild_id, changed_by, change_type, key_name, old_value, new_value)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            guild_id,
            changed_by,
            change_type,
            key_name,
            json.dumps(old_value),
            json.dumps(new_value),
        )

    def _row_to_history_entry(self, row) -> ConfigHistoryEntry:
        return ConfigHistoryEntry(
            id=row["id"],
            guild_id=row["guild_id"],
            changed_by=row["changed_by"],
            change_type=row["change_type"],
            key_name=row["key_name"],
            old_value=json.loads(row["old_value"]) if row["old_value"] is not None else None,
            new_value=json.loads(row["new_value"]),
            created_at=row["created_at"],
        )

    async def get_config_history(
        self, guild_id: int, limit: int = 10
    ) -> list[ConfigHistoryEntry]:
        rows = await self.pool.fetch(
            """
            SELECT * FROM guild_config_history
            WHERE guild_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            guild_id,
            limit,
        )
        return [self._row_to_history_entry(r) for r in rows]

    async def get_config_history_entry(self, entry_id: int) -> ConfigHistoryEntry | None:
        row = await self.pool.fetchrow(
            "SELECT * FROM guild_config_history WHERE id = $1", entry_id
        )
        return self._row_to_history_entry(row) if row is not None else None

    async def rollback_config_change(self, entry_id: int, rolled_back_by: int | None) -> bool:
        """
        Ripristina old_value di una voce di storico. Restituisce
        False se la voce non esiste o NON si può ripristinare (BUG-6:
        mai un successo finto). Il rollback stesso viene registrato
        come una NUOVA voce di storico, scritta dagli stessi metodi
        usati dai comandi — un rollback lascia traccia di sé.

        - module: torna al valore precedente (mai impostato = False);
        - setting "language": cambia la colonna `language`;
        - setting normale: se prima non esisteva la chiave viene
          RIMOSSA (non messa a null);
        - reset/import: old_value è la configurazione intera
          (modules, settings, language) e viene ripristinata intera.
        """
        entry = await self.get_config_history_entry(entry_id)
        if entry is None:
            return False

        if entry.change_type == "module":
            valore_da_ripristinare = bool(entry.old_value)
            await self.set_module_active_for_guild(
                entry.guild_id, entry.key_name, valore_da_ripristinare, changed_by=rolled_back_by
            )
        elif entry.change_type == "setting":
            if entry.key_name == "language":
                if not isinstance(entry.old_value, str):
                    return False
                await self.set_guild_language(
                    entry.guild_id, entry.old_value, changed_by=rolled_back_by
                )
            elif entry.old_value is None:
                await self.remove_guild_setting(entry.guild_id, entry.key_name, rolled_back_by)
            else:
                await self.set_guild_setting(
                    entry.guild_id, entry.key_name, entry.old_value, changed_by=rolled_back_by
                )
        elif entry.change_type in ("reset", "import"):
            old = entry.old_value
            if not (
                isinstance(old, dict)
                and isinstance(old.get("modules"), dict)
                and isinstance(old.get("settings"), dict)
                and isinstance(old.get("language"), str)
            ):
                return False
            await self.import_full_config(
                entry.guild_id, old["modules"], old["settings"], old["language"],
                changed_by=rolled_back_by,
            )
        else:
            return False
        return True

    async def remove_guild_setting(
        self, guild_id: int, key: str, changed_by: int | None
    ) -> None:
        """Toglie del tutto una chiave da settings (non la mette a null) e la registra nello storico."""
        old_row = await self.pool.fetchrow(
            "SELECT settings -> $2 AS value FROM guild_config WHERE guild_id = $1",
            guild_id,
            key,
        )
        old_value = json.loads(old_row["value"]) if old_row and old_row["value"] is not None else None
        await self.pool.execute(
            "UPDATE guild_config SET settings = settings - $2::text, updated_at = now() WHERE guild_id = $1",
            guild_id,
            key,
        )
        await self._record_config_change(guild_id, changed_by, "setting", key, old_value, None)

    # ================================================================
    # Export / Import / Reset configurazione (SPEC.md §2.1/§2.5/§2.6)
    # ================================================================
    async def get_full_config(self, guild_id: int) -> dict:
        """
        SPEC.md §2.5 (Esporta configurazione): l'intero stato
        configurabile di un server in un dict serializzabile in JSON
        — moduli attivi, settings libere, lingua. Usato sia
        dall'export vero e proprio sia da reset/import per registrare
        il valore "prima" nello storico.
        """
        row = await self.pool.fetchrow(
            "SELECT modules, settings, language FROM guild_config WHERE guild_id = $1",
            guild_id,
        )
        if row is None:
            return {"modules": {}, "settings": {}, "language": "it"}
        return {
            "modules": json.loads(row["modules"]),
            "settings": json.loads(row["settings"]),
            "language": row["language"],
        }

    async def import_full_config(
        self,
        guild_id: int,
        modules: dict,
        settings: dict,
        language: str,
        changed_by: int | None = None,
    ) -> None:
        """
        SPEC.md §2.6 (Importa configurazione): sovrascrive modules/
        settings/language IN BLOCCO (non un merge) — importare un file
        esportato da un altro server deve riprodurne esattamente lo
        stato, non mescolarlo con quello attuale. Un'unica voce di
        storico (change_type="import") invece di una per ogni chiave,
        altrimenti un import con 40 moduli riempirebbe lo storico di
        40 righe per un singolo comando.
        """
        await self.ensure_guild_exists(guild_id)
        old = await self.get_full_config(guild_id)
        # Una chiave a `null` vale "assente": non la si scrive (BUG-31).
        settings = {chiave: valore for chiave, valore in settings.items() if valore is not None}

        await self.pool.execute(
            """
            UPDATE guild_config
            SET modules = $2::jsonb, settings = $3::jsonb, language = $4, updated_at = now()
            WHERE guild_id = $1
            """,
            guild_id,
            json.dumps(modules),
            json.dumps(settings),
            language,
        )
        self._modules_cache.delete(guild_id)

        await self._record_config_change(
            guild_id,
            changed_by,
            "import",
            "guild_config",
            old,
            {"modules": modules, "settings": settings, "language": language},
        )

    async def reset_guild_config(self, guild_id: int, changed_by: int | None = None) -> None:
        """
        SPEC.md §2.1 (bottone "Reset configurazione"): torna allo
        stato di un server appena creato — nessun modulo attivo,
        nessuna setting, lingua italiana di default. Registrato come
        un'unica voce di storico (change_type="reset"), ripristinabile
        con /config rollback come qualunque altra voce.
        """
        await self.ensure_guild_exists(guild_id)
        old = await self.get_full_config(guild_id)

        await self.pool.execute(
            """
            UPDATE guild_config
            SET modules = '{}'::jsonb, settings = '{}'::jsonb, language = 'it', updated_at = now()
            WHERE guild_id = $1
            """,
            guild_id,
        )
        self._modules_cache.delete(guild_id)

        await self._record_config_change(
            guild_id,
            changed_by,
            "reset",
            "guild_config",
            old,
            {"modules": {}, "settings": {}, "language": "it"},
        )

    # ================================================================
    # Lingua per server (SPEC.md §2.3)
    # ================================================================
    async def get_guild_language(self, guild_id: int) -> str:
        row = await self.pool.fetchrow(
            "SELECT language FROM guild_config WHERE guild_id = $1", guild_id
        )
        return row["language"] if row is not None else "it"

    async def set_guild_language(
        self, guild_id: int, language: str, changed_by: int | None = None
    ) -> None:
        await self.ensure_guild_exists(guild_id)
        old = await self.get_guild_language(guild_id)
        await self.pool.execute(
            "UPDATE guild_config SET language = $2, updated_at = now() WHERE guild_id = $1",
            guild_id,
            language,
        )
        await self._record_config_change(
            guild_id, changed_by, "setting", "language", old, language
        )

    # ================================================================
    # Premium whitelist
    # ================================================================
    async def is_guild_whitelisted(self, guild_id: int) -> bool:
        row = await self.pool.fetchrow(
            "SELECT 1 FROM premium_whitelist WHERE guild_id = $1",
            guild_id,
        )
        return row is not None

    async def add_guild_to_whitelist(
        self, guild_id: int, added_by: int, reason: str | None = None
    ) -> None:
        await self.pool.execute(
            """
            INSERT INTO premium_whitelist (guild_id, added_by, reason)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE
                SET added_by = EXCLUDED.added_by,
                    reason = EXCLUDED.reason
            """,
            guild_id,
            added_by,
            reason,
        )

    async def remove_guild_from_whitelist(self, guild_id: int) -> None:
        await self.pool.execute(
            "DELETE FROM premium_whitelist WHERE guild_id = $1",
            guild_id,
        )

    async def list_premium_whitelist(self) -> list[dict]:
        """SPEC.md §3.2: esisteva add/remove ma non un modo per
        ELENCARE la whitelist — l'unico modo per controllarla era
        interrogare il database a mano."""
        righe = await self.pool.fetch(
            """
            SELECT guild_id, added_by, reason, added_at
            FROM premium_whitelist
            ORDER BY added_at ASC
            """
        )
        return [
            {
                "guild_id": r["guild_id"],
                "added_by": r["added_by"],
                "reason": r["reason"],
                "added_at": r["added_at"],
            }
            for r in righe
        ]


# Istanza unica, condivisa da tutto il progetto.
db = Database()


# ====================================================================
# NOTA SULLA CRESCITA DI QUESTO FILE
# ====================================================================
# Man mano che si aggiungono moduli (moderation, leveling, gilde...),
# le loro tabelle e i loro metodi NON vanno tutti ammassati qui
# dentro: questo file resta per Database/Premium/Config di base.
# Ogni modulo avrà il proprio repository, es.:
#
#   core/repositories/moderation_repo.py
#   core/repositories/leveling_repo.py
#
# ognuno con il proprio run_migrations() (aggiunto alla lista in
# core/migrations.py's run_all_repo_migrations(), chiamata in
# sequenza da run_migrations() qui sopra) e i propri metodi, ma tutti
# condividono lo stesso pool tramite `db.pool`. Questo tiene il file
# principale piccolo e ogni repository leggibile per il modulo a cui
# appartiene.
