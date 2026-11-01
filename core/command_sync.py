"""
core/command_sync.py
====================
Sincronizza i comandi con Discord solo se l'albero è cambiato: si calcola
l'impronta (sha256) dei comandi di ogni ambito e la si confronta con
quella salvata nel database (tabella `command_sync_state`). Un errore di
sync non aggiorna l'impronta: all'avvio dopo si riprova.
`SincronizzatoreDifferito` unisce i cambi dell'albero a bot avviato (D57).
Funzioni coperte: SPEC §20 (NF-05), D57
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


async def impronta_albero_tradotto(comandi: Sequence[Any], tree: app_commands.CommandTree) -> str:
    """
    Come `impronta_albero`, ma con le traduzioni dei comandi (NF-06): senza, cambiare un testo in
    locales/en-US/comandi.json non farebbe risincronizzare. Senza traduttore, o se la traduzione
    fallisce, ricade sull'impronta semplice.
    """
    traduttore = getattr(tree, "translator", None)
    if traduttore is None:
        return impronta_albero(comandi, tree)
    try:
        ordinati = sorted(comandi, key=lambda c: c.name)
        payload = [await c.get_translated_payload(tree, traduttore) for c in ordinati]
    except Exception as exc:
        logger.warning("Impronta con traduzioni non calcolabile (%s): uso quella semplice.", type(exc).__name__)
        return impronta_albero(comandi, tree)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


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
    impronta = await impronta_albero_tradotto(comandi, tree)
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


class SincronizzatoreDifferito:
    """
    Sincronizza l'albero dopo un cambio, con attesa: tanti cambi ravvicinati fanno una
    sola sync, e tra due sync passa almeno `intervallo_minimo` secondi (limiti di Discord).
    Un cambio che arriva mentre la sync è in corso ne chiede un'altra, dopo l'intervallo.
    `sync` è una funzione asincrona senza argomenti; `pronto` (facoltativa) aspetta che il
    bot sia collegato, perché prima la sync darebbe solo errore.
    """

    def __init__(
        self,
        sync: Callable[[], Awaitable[Any]],
        *,
        attesa: float = 30.0,
        intervallo_minimo: float = 120.0,
        pronto: Callable[[], Awaitable[Any]] | None = None,
    ) -> None:
        self._sync = sync
        self._pronto = pronto
        self._attesa = attesa
        self._intervallo = intervallo_minimo
        self._compito = None
        self._in_sync = False
        self._ancora = False
        self._ultima: float | None = None
        self.eseguite = 0

    def richiedi(self) -> None:
        """Chiede una sync; se ce n'è già una in attesa non ne aggiunge un'altra."""
        import asyncio

        if self._compito is not None and not self._compito.done():
            if self._in_sync:
                self._ancora = True  # l'albero è cambiato dopo l'inizio della sync in corso
            return
        self._compito = asyncio.get_running_loop().create_task(self._esegui())

    async def _esegui(self) -> None:
        import asyncio

        while True:
            attesa = self._attesa
            if self._ultima is not None:
                trascorso = asyncio.get_running_loop().time() - self._ultima
                attesa = max(attesa, self._intervallo - trascorso)
            await asyncio.sleep(attesa)
            if self._pronto is not None:
                await self._pronto()
            self._ancora = False
            self._in_sync = True
            try:
                await self._sync()
            except Exception as exc:
                logger.warning("Sync differita fallita (%s).", type(exc).__name__)
            finally:
                self._in_sync = False
            self.eseguite += 1
            self._ultima = asyncio.get_running_loop().time()
            if not self._ancora:
                return

    async def attendi(self) -> None:
        """Aspetta la sync in corso (per i test e per lo spegnimento)."""
        if self._compito is not None:
            await self._compito

    def ferma(self) -> None:
        if self._compito is not None and not self._compito.done():
            self._compito.cancel()
