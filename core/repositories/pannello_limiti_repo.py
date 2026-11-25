"""
core/repositories/pannello_limiti_repo.py
=========================================
I limiti del pannello web che devono reggere anche a un riavvio (marchio, sincronia dei permessi, copia dei dati):
ogni colpo è una riga nel database, il conteggio guarda solo la finestra. Il controllo e la scrittura sono una
transazione sola con un blocco per (nome, soggetto): due richieste insieme non superano il tetto. Se il database
non risponde il colpo NON passa (meglio un «riprova» che saltare il limite).
Funzioni coperte: blocco A (voce 6)
Dipende da: core/migrations/0982_nonce_ripristino_limiti_pannello.sql
"""

from __future__ import annotations

import logging

import asyncpg

logger = logging.getLogger("iyokai.pannello_limiti")

AMBITI = ("server", "utente")


class LimitePersistente:
    """Al massimo `massimo` colpi per soggetto in `finestra` secondi, contati nel database."""

    def __init__(self, nome: str, massimo: int, finestra: int, ambito: str, pool_provider=None) -> None:
        if ambito not in AMBITI:
            raise ValueError("ambito non valido")
        self.nome, self.massimo, self.finestra, self.ambito = nome, massimo, finestra, ambito
        self._pool_provider = pool_provider or _get_pool

    async def consenti(self, soggetto: int) -> bool:
        try:
            async with self._pool_provider().acquire() as conn, conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"{self.nome}:{soggetto}")
                await conn.execute(
                    "DELETE FROM pannello_limiti WHERE nome = $1 AND soggetto = $2 AND colpito_il <= now() - make_interval(secs => $3)",
                    self.nome, soggetto, float(self.finestra),
                )
                fatti = await conn.fetchval("SELECT count(*) FROM pannello_limiti WHERE nome = $1 AND soggetto = $2", self.nome, soggetto)
                if fatti >= self.massimo:
                    return False
                await conn.execute(
                    "INSERT INTO pannello_limiti (nome, ambito, soggetto) VALUES ($1, $2, $3)", self.nome, self.ambito, soggetto
                )
                return True
        except (asyncpg.PostgresError, OSError):
            logger.warning("Limite %s non controllabile: la richiesta non passa.", self.nome, exc_info=True)
            return False


def _get_pool():
    from core.database import db

    return db.pool
