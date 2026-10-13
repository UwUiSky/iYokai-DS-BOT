"""
core/music_nodes.py
=======================
Nodi Lavalink dei bot musicali (F2, issue #64, D10, LIM-40/41/42/54).

Un nodo wavelink è legato a UN solo utente bot (l'header `User-Id` del
collegamento): se i nodi sono collegati con il bot principale, dai 5 bot
musicali non esce audio. Qui ogni bot (principale + 5 worker) ha un nodo
per ogni server Lavalink, con identificatore proprio
(`<base>@<chiave del bot>`: il Pool ne tiene uno per identificatore).

- Ogni nodo si collega in un task suo, con tentativi limitati: un nodo
  morto non blocca gli altri né l'avvio del cog.
- Dopo il collegamento si legge `/v4/info`: sotto Lavalink 4.2.0 il nodo
  viene scartato con un avviso (DAVE).
- `close()` ferma i task e chiude i nodi (`Pool.close()` allo spegnimento).
- La scelta del nodo è esplicita (`node_for`): pubblici prima, locale per
  ultimo, solo tra i nodi del bot che parla.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable

import wavelink

from core.music_logic import (
    LOCAL_NODE_BASE,
    NODE_CONNECT_RETRIES,
    LavalinkNodeConfig,
    choose_node,
    is_supported_lavalink,
    node_identifier,
    order_nodes,
    public_node_base,
)

logger = logging.getLogger("iyokai.music")

MAIN_KEY = "main"

# Dopo i tentativi di wavelink un nodo non resta scartato per sempre: nuovo giro
# con pause crescenti (secondi); l'ultima si ripete.
RETRY_PAUSES = (30.0, 60.0, 120.0, 300.0)


def worker_key(worker_index: int) -> str:
    return f"w{worker_index}"


async def _connetti_con_wavelink(node: wavelink.Node, client) -> None:
    await wavelink.Pool.connect(nodes=[node], client=client)


async def _versione_del_nodo(node: wavelink.Node) -> str | None:
    info = await node.fetch_info()
    return info.version.semver


class MusicNodeManager:
    def __init__(
        self,
        pubblici: Iterable[LavalinkNodeConfig],
        locale: LavalinkNodeConfig | None,
        *,
        connetti: Callable[..., Awaitable[None]] = _connetti_con_wavelink,
        leggi_versione: Callable[..., Awaitable[str | None]] = _versione_del_nodo,
        retries: int = NODE_CONNECT_RETRIES,
        attesa_pronto: float = 15.0,
        pause_riprova: tuple[float, ...] = RETRY_PAUSES,
    ) -> None:
        self._attesa_pronto = attesa_pronto
        self._pause_riprova = pause_riprova
        self._pubblici = list(pubblici)
        self._locale = locale
        self._connetti = connetti
        self._leggi_versione = leggi_versione
        self._retries = retries
        self._nodi: dict[str, list[wavelink.Node]] = {}
        self._client_di_nodo: dict[str, object] = {}
        self.tasks: set[asyncio.Task] = set()

    # ---- costruzione ----
    def costruisci_nodi(self, client, chiave: str) -> list[wavelink.Node]:
        """I nodi di UN bot: pubblici prima, locale per ultimo (LIM-42)."""
        nodi = [
            wavelink.Node(
                identifier=node_identifier(public_node_base(c.uri), chiave),
                uri=c.uri,
                password=c.password,
                client=client,
                retries=self._retries,
            )
            for c in self._pubblici
        ]
        if self._locale is not None:
            nodi.append(
                wavelink.Node(
                    identifier=node_identifier(LOCAL_NODE_BASE, chiave),
                    uri=self._locale.uri,
                    password=self._locale.password,
                    client=client,
                    retries=self._retries,
                    # NB: niente `inactive_channel_tokens=None` qui: varrebbe per OGNI
                    # player del nodo. L'esenzione e' solo sul player della radio.
                )
            )
        self._nodi[chiave] = nodi
        return nodi

    def avvia(self, client, chiave: str) -> list[asyncio.Task]:
        """Un task per nodo, conservato: i nodi non si aspettano a vicenda."""
        task = []
        for nodo in self.costruisci_nodi(client, chiave):
            self._client_di_nodo[nodo.identifier] = client
            t = asyncio.create_task(self._collega_uno(client, nodo))
            self.tasks.add(t)
            t.add_done_callback(self.tasks.discard)
            task.append(t)
        return task

    async def _collega_uno(self, client, nodo: wavelink.Node) -> None:
        """Collega il nodo; se non riesce (o e' troppo vecchio) riprova con pause crescenti."""
        tentativo = 0
        while True:
            try:
                if await self._tenta(client, nodo):
                    return
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Collegamento del nodo Lavalink %s fallito.", nodo.identifier)
                await self._scarta(nodo)
            pausa = self._pause_riprova[min(tentativo, len(self._pause_riprova) - 1)]
            tentativo += 1
            logger.info("Nodo %s: nuovo tentativo tra %s secondi.", nodo.identifier, pausa)
            await asyncio.sleep(pausa)

    async def _tenta(self, client, nodo: wavelink.Node) -> bool:
        wait = getattr(client, "wait_until_ready", None)
        if wait is not None:
            await wait()  # l'header User-Id richiede client.user
        await self._connetti(nodo, client)
        if not await self._attendi_connesso(nodo):
            logger.warning("Nodo Lavalink %s non raggiungibile: scartato.", nodo.identifier)
            await self._scarta(nodo)
            return False
        versione = await self._leggi_versione(nodo)
        if not is_supported_lavalink(versione):
            logger.warning(
                "Nodo Lavalink %s scartato: versione %s sotto la 4.2.0 "
                "(serve per la cifratura vocale DAVE).",
                nodo.identifier,
                versione,
            )
            await self._scarta(nodo)
            return False
        return True

    async def _attendi_connesso(self, nodo: wavelink.Node) -> bool:
        """
        `Pool.connect` torna con il nodo ancora CONNECTING: CONNECTED arriva col
        messaggio `ready` di Lavalink. Si aspetta (polling) fino a `attesa_pronto`.
        """
        fine = asyncio.get_running_loop().time() + self._attesa_pronto
        while True:
            if nodo.status is wavelink.NodeStatus.CONNECTED:
                return True
            ws = nodo._websocket
            if ws is not None and not ws.is_connected():
                return False  # tentativi esauriti: wavelink ha chiuso tutto
            if asyncio.get_running_loop().time() >= fine:
                return False
            await asyncio.sleep(0.05)

    async def _scarta(self, nodo: wavelink.Node) -> None:
        try:
            await nodo.close(eject=True)
        except Exception:
            logger.debug("Chiusura del nodo %s non riuscita.", nodo.identifier, exc_info=True)
        sessione = getattr(nodo, "_session", None)
        if sessione is not None and not sessione.closed:
            await sessione.close()

    # ---- uso ----
    def nodi_di(self, chiave: str) -> list[wavelink.Node]:
        return list(self._nodi.get(chiave, []))

    def nodi_ordinati(self, chiave: str) -> list[wavelink.Node]:
        return order_nodes(self.nodi_di(chiave))

    def node_for(self, chiave: str) -> wavelink.Node | None:
        """Il nodo di QUESTO bot su cui creare il player e cercare."""
        return choose_node(self.nodi_di(chiave))

    def locale_di(self, chiave: str) -> wavelink.Node | None:
        for nodo in self.nodi_ordinati(chiave):
            if nodo.identifier == node_identifier(LOCAL_NODE_BASE, chiave):
                return nodo
        return None

    # ---- spegnimento ----
    async def close(self) -> None:
        for t in list(self.tasks):
            t.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        try:
            await wavelink.Pool.close()
        except Exception:
            logger.debug("Pool.close() non riuscita.", exc_info=True)
        for nodi in self._nodi.values():
            for nodo in nodi:
                await self._scarta(nodo)
