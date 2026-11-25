"""
tests/support/proxy_guasto.py
=============================
Un proxy TCP davanti a PostgreSQL (o a qualsiasi servizio) che si può «staccare» e «riattaccare» a metà prova:
`interrompi()` chiude tutte le connessioni aperte e smette di ascoltare (chi si collega riceve «connessione
rifiutata»), `ripristina()` ricomincia a ascoltare sulla STESSA porta. Simula un database che cade e torna senza
toccare il server vero, che altri test usano nello stesso momento.
"""

from __future__ import annotations

import asyncio
import socket


def porta_libera() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ProxyGuasto:
    def __init__(self, host_destinazione: str, porta_destinazione: int) -> None:
        self._dest = (host_destinazione, porta_destinazione)
        self.porta = porta_libera()
        self._server: asyncio.AbstractServer | None = None
        self._connessioni: set[asyncio.StreamWriter] = set()
        self._compiti: set[asyncio.Task] = set()

    async def avvia(self) -> None:
        self._server = await asyncio.start_server(self._gestisci, "127.0.0.1", self.porta, reuse_address=True)

    async def _gestisci(self, lettore: asyncio.StreamReader, scrittore: asyncio.StreamWriter) -> None:
        try:
            lettore_d, scrittore_d = await asyncio.open_connection(*self._dest)
        except OSError:
            scrittore.close()
            return
        self._connessioni.update((scrittore, scrittore_d))

        async def passa(da: asyncio.StreamReader, a: asyncio.StreamWriter) -> None:
            try:
                while dati := await da.read(65536):
                    a.write(dati)
                    await a.drain()
            except (ConnectionError, asyncio.CancelledError):
                pass
            finally:
                a.close()

        compiti = [asyncio.ensure_future(passa(lettore, scrittore_d)), asyncio.ensure_future(passa(lettore_d, scrittore))]
        self._compiti.update(compiti)
        await asyncio.wait(compiti, return_when=asyncio.FIRST_COMPLETED)
        for c in compiti:
            c.cancel()
        self._compiti.difference_update(compiti)
        self._connessioni.difference_update((scrittore, scrittore_d))

    async def interrompi(self) -> None:
        """Il servizio «cade»: via tutte le connessioni, nessuno può più collegarsi."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        for c in list(self._compiti):
            c.cancel()
        for s in list(self._connessioni):
            s.transport.abort()
        self._connessioni.clear()
        await asyncio.sleep(0.05)

    async def ripristina(self) -> None:
        """Il servizio «torna»."""
        if self._server is None:
            await self.avvia()

    async def chiudi(self) -> None:
        await self.interrompi()

    @property
    def dsn_base(self) -> str:
        return f"127.0.0.1:{self.porta}"
