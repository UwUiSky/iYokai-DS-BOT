"""
core/soundboard_log_service.py
==================================
Log soundboard (SPEC.md §8.13) — a differenza di ogni altro evento
del Logging Avanzato (cogs/logging/advanced_logs.py), discord.py 2.7
non espone un evento GATEWAY per la creazione/modifica/eliminazione
di un suono soundboard (nessun `on_soundboard_sound_...`). L'AUDIT
LOG del server lo registra comunque
(`discord.AuditLogAction.soundboard_sound_create/update/delete`,
verificato leggendo l'enum reale della libreria installata) — quindi
va INTERROGATO a intervalli, non atteso via listener. Stesso
principio architetturale di core/event_log_retention.py: una classe
con un tasks.loop periodico, avviata una volta da main.py, non un Cog
con listener.

**Watermark persistito per evitare doppioni e per non riversare lo
storico alla prima attivazione**: ogni server ha il proprio
"timestamp dell'ultima voce già processata"
(SETTING_SOUNDBOARD_WATERMARK, un guild setting generico come
SETTING_LOG_CHANNEL — nessuna nuova tabella). Logica pura di
filtro/avanzamento in core/logging_advanced_logic.py
(`new_entries_since`/`next_watermark`), testata a sé.
Funzioni coperte: REVIEW.md LC-8 (errori isolati per server nel giro).
"""

# DA FARE (issue #61, fase F1): correzioni aperte per questo file in
#   revisione/02-piano/MODIFICHE_ESISTENTE.md §5 (Log).

from __future__ import annotations

import logging
from datetime import datetime

import discord
from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.database import db
from core.guild_iteration import for_each_guild_safely
from core.logging_advanced_logic import new_entries_since, next_watermark
from core.repositories.event_log_repo import event_log_repo

logger = logging.getLogger("iyokai.soundboard_log_service")

# Il soundboard cambia raramente rispetto ad altri eventi (ruoli,
# canali...): un intervallo di 5 minuti resta ampiamente sufficiente
# a non far sembrare il log "in ritardo", senza interrogare l'audit
# log di ogni server ad ogni istante.
TICK_SECONDS = 5 * 60

_SOUNDBOARD_ACTIONS = {
    discord.AuditLogAction.soundboard_sound_create: "soundboard_sound_create",
    discord.AuditLogAction.soundboard_sound_update: "soundboard_sound_update",
    discord.AuditLogAction.soundboard_sound_delete: "soundboard_sound_delete",
}


def _entry_name(entry) -> str:
    """
    Il nome del suono non ha un transformer dedicato in
    discord.py (nessun tipo `SoundboardSound` risolto per l'audit
    log) — ma la chiave "name" arriva comunque grezza nel diff
    prima/dopo (AuditLogChanges assegna ogni chiave non riconosciuta
    così com'è, vedi discord/audit_logs.py). Se anche questo manca
    (voce malformata/versione futura dell'API), un fallback con il
    solo ID resta meglio di far sparire l'evento.
    """
    nome = getattr(entry.after, "name", None) or getattr(entry.before, "name", None)
    if nome:
        return nome
    target_id = getattr(entry.target, "id", None)
    return f"suono {target_id}" if target_id is not None else "suono sconosciuto"


class SoundboardLogService:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def _fetch_recent_entries(self, guild: discord.Guild) -> list[dict]:
        entries: list[dict] = []
        for action, event_type in _SOUNDBOARD_ACTIONS.items():
            try:
                async for entry in guild.audit_logs(action=action, limit=10):
                    entries.append(
                        {
                            "created_at": entry.created_at,
                            "action_type": event_type,
                            "actor_id": entry.user_id,
                            "name": _entry_name(entry),
                        }
                    )
            except discord.Forbidden:
                logger.warning(
                    "Permessi insufficienti per leggere l'audit log soundboard "
                    "nel server %s.", guild.id,
                )
                continue
            except discord.HTTPException:
                logger.warning(
                    "Errore temporaneo leggendo l'audit log soundboard nel "
                    "server %s.", guild.id,
                )
                continue
        return entries

    async def tick(self, bot: commands.Bot) -> None:
        # Import qui, non in cima al file: evita un ciclo di import
        # con cogs.logging.advanced_logs, che a sua volta non importa
        # questo modulo, ma tenerli comunque separati mantiene ogni
        # file caricabile isolatamente nei test.
        from cogs.logging.advanced_logs import (
            MODULE_LOGGING_ADVANCED,
            SETTING_SOUNDBOARD_WATERMARK,
            send_event_embed,
        )

        async def _per_server(guild) -> None:
            if not await db.is_module_active_for_guild(guild.id, MODULE_LOGGING_ADVANCED):
                return

            raw_watermark = await db.get_guild_setting(guild.id, SETTING_SOUNDBOARD_WATERMARK)
            watermark = datetime.fromisoformat(raw_watermark) if raw_watermark else None

            entries = await self._fetch_recent_entries(guild)
            nuove = new_entries_since(entries, watermark)

            for entry in nuove:
                await event_log_repo.log_event(
                    guild.id,
                    entry["action_type"],
                    actor_id=entry["actor_id"],
                    details={"name": entry["name"]},
                )
                descrizione = f"`{entry['name']}`"
                if entry["actor_id"] is not None:
                    descrizione += f" — <@{entry['actor_id']}>"
                await send_event_embed(guild, entry["action_type"], descrizione)

            aggiornato = next_watermark(entries, watermark)
            if aggiornato is not None and aggiornato != watermark:
                await db.set_guild_setting(
                    guild.id, SETTING_SOUNDBOARD_WATERMARK, aggiornato.isoformat()
                )

        # LC-8: un server problematico non blocca gli altri.
        await for_each_guild_safely(bot.guilds, _per_server, nome_worker="Log soundboard")

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel tick del log soundboard")

        @_loop.before_loop
        async def _before():
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Log soundboard avviato (controllo ogni %ds).", TICK_SECONDS)


# Istanza unica, condivisa da tutto il progetto — coerente con
# core/event_log_retention.py, core/memory_guard.py, core/scheduler.py.
soundboard_log_service = SoundboardLogService()
