"""
core/backup_mirror_dispatch.py
==================================
Il "collante" del mirroring in tempo reale (SPEC.md §11.9): decide,
per ogni messaggio ricevuto da Main, se va inoltrato al webhook di
backup e lo inoltra impersonando l'autore originale (nome + avatar).
Ogni canale ha una sua coda: i messaggi partono nell'ordine in cui sono
arrivati, uno alla volta (ognuno atteso), al massimo 5 ogni 5 secondi;
sui picchi si aspetta (oltre 200 in attesa i nuovi si scartano). L'URL si
rilegge a ogni invio: se il mirror del canale viene tolto la coda si ferma.
Gli allegati vanno come file fino a 10 MiB; i messaggi di sistema non si copiano.

Separato da un semplice listener nel Cog per essere testabile senza
una vera connessione a Discord: BackupMirrorDispatcher.handle_message
prende decisioni pure (bot? già un webhook? rate limit? mappa
esistente?) e isola l'unica chiamata di rete reale in _send(), che i
test possono sostituire con un finto.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

import aiohttp
import discord

from core.backup_messages_logic import (
    TIPI_COPIABILI,
    allegati_come_file,
    contenuto_da_copiare,
    file_degli_allegati,
)
from core.backup_mirror_logic import MirrorRateLimiter, nome_sicuro_per_webhook

logger = logging.getLogger("iyokai.backup_mirror")

# Limite reale di Discord per il contenuto di un messaggio — un
# webhook lo rifiuta se superato.
MAX_CONTENT_LENGTH = 2000

# Messaggi in attesa per canale: oltre questo numero i nuovi si scartano (si logga).
MAX_CODA_PER_CANALE = 200
PAUSA_RATE_LIMIT = 0.25

# Un webhook di Discord rifiuta un content completamente vuoto (per
# esempio un messaggio composto solo da un embed non testuale che qui
# non gestiamo, o un messaggio "di sistema"): un carattere invisibile
# a larghezza zero evita l'errore senza produrre un mirror leggibile
# come "vuoto e strano".
ZERO_WIDTH_SPACE = "​"


class BackupMirrorDispatcher:
    def __init__(self, mirror_repo, rate_limiter: MirrorRateLimiter | None = None) -> None:
        self._mirror_repo = mirror_repo
        self._rate_limiter = rate_limiter or MirrorRateLimiter()
        self._http_session: aiohttp.ClientSession | None = None
        self._code: dict[int, deque[discord.Message]] = {}
        self._lavoratori: dict[int, asyncio.Task] = {}

    def _get_session(self) -> aiohttp.ClientSession:
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def close(self) -> None:
        for lavoratore in list(self._lavoratori.values()):
            lavoratore.cancel()
        for lavoratore in list(self._lavoratori.values()):
            try:
                await lavoratore
            except asyncio.CancelledError:
                pass
        self._lavoratori.clear()
        self._code.clear()
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None

    async def svuota(self) -> None:
        """Aspetta che tutte le code siano state inviate (test e chiusura ordinata)."""
        while self._lavoratori:
            await asyncio.gather(*list(self._lavoratori.values()), return_exceptions=True)

    async def handle_message(self, message: discord.Message) -> bool:
        """
        Restituisce True se il messaggio è stato messo in coda per l'invio,
        False se è stato scartato (nessun mirror per quel canale, autore
        un bot/webhook, messaggio di sistema, coda piena).
        """
        if message.author.bot:
            return False  # evita loop: non mirroriamo bot/webhook (incluso il nostro)

        if message.guild is None:
            return False  # DM: nessun canale di backup possibile

        if getattr(message, "type", discord.MessageType.default) not in TIPI_COPIABILI:
            return False  # messaggi di sistema (ingressi, boost, ecc.)

        webhook_url = await self._mirror_repo.get_webhook_url(message.channel.id)
        if webhook_url is None:
            return False  # canale non mappato (nessun backup attivo per questo main)

        canale = message.channel.id
        coda = self._code.get(canale)
        if coda is None:
            coda = self._code[canale] = deque()
        if len(coda) >= MAX_CODA_PER_CANALE:
            logger.warning("Coda del mirror piena nel canale %s: messaggio scartato.", canale)
            return False
        coda.append(message)
        if canale not in self._lavoratori:
            self._lavoratori[canale] = asyncio.create_task(self._svuota_canale(canale))
        return True

    async def _svuota_canale(self, canale: int) -> None:
        """Invia la coda del canale in ordine, uno alla volta, con la regola 5 messaggi / 5 s."""
        coda = self._code[canale]
        try:
            while coda:
                while not self._rate_limiter.allow(canale, time.monotonic()):
                    await asyncio.sleep(PAUSA_RATE_LIMIT)
                message = coda.popleft()
                try:
                    # L'URL si rilegge a ogni invio: se la coppia è stata scollegata
                    # (promozione, nuovo backup) la coda si ferma e non scrive più lì.
                    webhook_url = await self._mirror_repo.get_webhook_url(canale)
                    if webhook_url is None:
                        logger.info("Mirror tolto dal canale %s: %d messaggi lasciati.", canale, len(coda))
                        coda.clear()
                        break
                    await self._send(webhook_url, message)
                except Exception:
                    logger.exception("Invio al mirror fallito (canale %s).", canale)
        finally:
            # nessun await tra l'ultimo controllo e questa pulizia: un messaggio nuovo
            # troverà la coda già tolta e farà partire un nuovo lavoratore.
            self._code.pop(canale, None)
            self._lavoratori.pop(canale, None)

    async def _send(self, webhook_url: str, message: discord.Message) -> None:
        come_file = allegati_come_file(message.attachments)
        contenuto = contenuto_da_copiare(message, come_file) or ""
        file = await file_degli_allegati(come_file) if come_file else []
        if not contenuto and not file:
            contenuto = ZERO_WIDTH_SPACE
        contenuto = contenuto[:MAX_CONTENT_LENGTH]

        webhook = discord.Webhook.from_url(webhook_url, session=self._get_session())
        kwargs = {"files": file} if file else {}
        try:
            await webhook.send(
                content=contenuto,
                username=nome_sicuro_per_webhook(message.author.display_name),
                avatar_url=str(message.author.display_avatar.url),
                # SEC-22: un webhook creato da URL non eredita le
                # allowed_mentions del bot — senza questo un @everyone
                # scritto nel server principale diventa un ping vero
                # nel server di backup.
                allowed_mentions=discord.AllowedMentions.none(),
                # D8: ogni invio atteso fino alla risposta, così l'ordine resta
                # quello originale anche quando discord.py aspetta sui 429.
                wait=True,
                **kwargs,
            )
        except discord.HTTPException:
            # Un webhook cancellato/canale sparito nel server di
            # backup non deve far crashare on_message del server
            # MAIN — il mirror è un servizio accessorio, non deve
            # mai interrompere il flusso normale dei messaggi.
            logger.warning("Invio al webhook di mirror fallito (canale %s).", message.channel.id)
