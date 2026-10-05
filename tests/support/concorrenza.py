"""
tests/support/concorrenza.py
============================
Aiuto per i test che lanciano due chiamate insieme sul database vero.
"""

from __future__ import annotations

import asyncio

import asyncpg


async def apri_connessioni(pool: asyncpg.Pool, quante: int = 3) -> None:
    """
    Apre subito `quante` connessioni del pool. Senza questo passo la
    seconda chiamata di un asyncio.gather aspetterebbe l'apertura di una
    connessione nuova, e le due chiamate non partirebbero insieme: un
    test di concorrenza passerebbe anche con il codice sbagliato.
    """
    await asyncio.gather(*(pool.fetchval("SELECT pg_sleep(0.05)") for _ in range(quante)))
