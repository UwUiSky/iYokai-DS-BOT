"""
core/backup_mirror_dispatch.py
==================================
Il "collante" del mirroring in tempo reale (SPEC.md §11.9): decide,
per ogni messaggio ricevuto da Main, se va inoltrato al webhook di
backup e lo inoltra impersonando l'autore originale (nome + avatar).

Separato da un semplice listener nel Cog per essere testabile senza
una vera connessione a Discord: BackupMirrorDispatcher.handle_message
prende decisioni pure (bot? già un webhook? rate limit? mappa
esistente?) e isola l'unica chiamata di rete reale in _send(), che i
test possono sostituire con un finto.
"""

from __future__ import annotations

import logging
import time

import aiohttp
import discord

from core.backup_mirror_logic import MirrorRateLimiter

logger = logging.getLogger("iyokai.backup_mirror")

# Limite reale di Discord per il contenuto di un messaggio — un
# webhook lo rifiuta se superato.
MAX_CONTENT_LENGTH = 2000

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

    def _get_session(self) -> aiohttp.ClientSession:
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def close(self) -> None:
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None

    async def handle_message(self, message: discord.Message) -> bool:
        """
        Restituisce True se il messaggio è stato inoltrato, False se
        è stato scartato (nessun mirror configurato per quel canale,
        autore un bot/webhook, o rate limit superato) — utile ai test
        e a chi vuole loggare senza dover ripetere la stessa logica.
        """
        if message.author.bot:
            return False  # evita loop: non mirroriamo bot/webhook (incluso il nostro)

        if message.guild is None:
            return False  # DM: nessun canale di backup possibile

        webhook_url = await self._mirror_repo.get_webhook_url(message.channel.id)
        if webhook_url is None:
            return False  # canale non mappato (nessun backup attivo per questo main)

        if not self._rate_limiter.allow(message.channel.id, time.monotonic()):
            logger.info(
                "Mirror scartato per rate limit sul canale %s (burst > 5 msg/5s).",
                message.channel.id,
            )
            return False

        await self._send(webhook_url, message)
        return True

    async def _send(self, webhook_url: str, message: discord.Message) -> None:
        contenuto = message.content or ""
        if message.attachments:
            link_allegati = "\n".join(allegato.url for allegato in message.attachments)
            contenuto = f"{contenuto}\n{link_allegati}" if contenuto else link_allegati
        if not contenuto:
            contenuto = ZERO_WIDTH_SPACE
        contenuto = contenuto[:MAX_CONTENT_LENGTH]

        webhook = discord.Webhook.from_url(webhook_url, session=self._get_session())
        try:
            await webhook.send(
                content=contenuto,
                username=message.author.display_name,
                avatar_url=str(message.author.display_avatar.url),
                # SEC-22: un webhook creato da URL non eredita le
                # allowed_mentions del bot — senza questo un @everyone
                # scritto nel server principale diventa un ping vero
                # nel server di backup.
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            # Un webhook cancellato/canale sparito nel server di
            # backup non deve far crashare on_message del server
            # MAIN — il mirror è un servizio accessorio, non deve
            # mai interrompere il flusso normale dei messaggi.
            logger.warning("Invio al webhook di mirror fallito (canale %s).", message.channel.id)
