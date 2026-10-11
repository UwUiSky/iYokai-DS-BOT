"""
core/command_sync.py
====================
Sincronizza i comandi con Discord solo se l'albero è cambiato: si calcola
l'impronta (sha256) dei comandi di ogni ambito e la si confronta con
quella salvata nel database (tabella `command_sync_state`). Un errore di
sync non aggiorna l'impronta: all'avvio dopo si riprova.
Funzioni coperte: SPEC §20 (NF-05)
Dipende da: core/migrations/0021_command_sync_state.sql;
revisione/02-piano/MAPPA_COMANDI_F7.md §6
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

import discord
from discord import app_commands

logger = logging.getLogger(__name__)

SCOPE_GLOBALE = "global"
SALTATA = "saltata"
SINCRONIZZATA = "sincronizzata"
ERRORE = "errore"


def scope_guild(guild_id: int) -> str:
    return f"guild:{guild_id}"


def impronta_albero(comandi: Sequence[Any], tree: app_commands.CommandTree) -> str:
    """sha256 dei comandi come li vedrebbe Discord, in ordine di nome (indipendente dall'ordine di registrazione)."""
    ordinati = sorted(comandi, key=lambda c: c.name)
    testo = json.dumps([c.to_dict(tree) for c in ordinati], sort_keys=True, default=str)
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()


class StatoSync(Protocol):
    async def leggi(self, scope: str) -> str | None: ...

    async def salva(self, scope: str, impronta: str) -> None: ...


class StatoSyncDatabase:
    """L'impronta per ambito, nella tabella `command_sync_state`. `pool` è un pool asyncpg."""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def leggi(self, scope: str) -> str | None:
        return await self._pool.fetchval("SELECT tree_hash FROM command_sync_state WHERE scope = $1", scope)

    async def salva(self, scope: str, impronta: str) -> None:
        await self._pool.execute(
            """
            INSERT INTO command_sync_state (scope, tree_hash) VALUES ($1, $2)
            ON CONFLICT (scope) DO UPDATE SET tree_hash = EXCLUDED.tree_hash, synced_at = now()
            """,
            scope,
            impronta,
        )


async def sincronizza_se_cambiato(
    scope: str,
    comandi: Sequence[Any],
    tree: app_commands.CommandTree,
    sync: Callable[[], Awaitable[Any]],
    stato: StatoSync,
) -> str:
    """
    Chiama `sync` solo se l'impronta dei `comandi` è diversa da quella salvata
    (o manca). Restituisce SALTATA, SINCRONIZZATA o ERRORE. Mai eccezioni:
    un errore di Discord o del database non deve fermare l'avvio del bot.
    """
    impronta = impronta_albero(comandi, tree)
    try:
        salvata = await stato.leggi(scope)
    except Exception as exc:
        logger.warning("Sync comandi [%s]: impronta salvata illeggibile (%s), sincronizzo.", scope, type(exc).__name__)
        salvata = None
    if salvata == impronta:
        logger.info("Sync comandi [%s]: albero invariato, sincronizzazione saltata.", scope)
        return SALTATA
    try:
        await sync()
    except Exception as exc:
        logger.warning(
            "Sync comandi [%s] fallita (%s): l'impronta non è stata aggiornata, riprovo al prossimo avvio.",
            scope,
            type(exc).__name__,
        )
        return ERRORE
    logger.info("Sync comandi [%s]: %d comandi sincronizzati.", scope, len(comandi))
    try:
        await stato.salva(scope, impronta)
    except Exception as exc:
        logger.warning("Sync comandi [%s]: impronta non salvata (%s).", scope, type(exc).__name__)
    return SINCRONIZZATA


async def sincronizza_all_avvio(
    tree: app_commands.CommandTree,
    *,
    guild_sviluppo_id: int | None,
    guild_owner_id: int | None,
    stato: StatoSync,
) -> dict[str, str]:
    """
    Sviluppo (`guild_sviluppo_id`): copia il globale nel server di prova e
    sincronizza solo quello. Produzione: globale, più il server dell'owner
    (`/owner`) se `guild_owner_id` c'è. Restituisce {ambito: esito}.
    """
    if guild_sviluppo_id:
        guild = discord.Object(id=guild_sviluppo_id)
        tree.copy_global_to(guild=guild)
        scope = scope_guild(guild_sviluppo_id)
        return {
            scope: await sincronizza_se_cambiato(
                scope, tree.get_commands(guild=guild), tree, lambda: tree.sync(guild=guild), stato
            )
        }
    esiti = {
        SCOPE_GLOBALE: await sincronizza_se_cambiato(
            SCOPE_GLOBALE, tree.get_commands(), tree, lambda: tree.sync(), stato
        )
    }
    if guild_owner_id:
        guild = discord.Object(id=guild_owner_id)
        scope = scope_guild(guild_owner_id)
        esiti[scope] = await sincronizza_se_cambiato(
            scope, tree.get_commands(guild=guild), tree, lambda: tree.sync(guild=guild), stato
        )
    return esiti
