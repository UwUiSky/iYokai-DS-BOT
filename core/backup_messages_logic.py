"""
core/backup_messages_logic.py
=============================
D8 / M 12.17 (#68): copia degli ultimi N messaggi di ogni canale di testo
nel server di backup, impersonando l'autore con il webhook del canale
(quello del mirror, già creato).

Regole di sicurezza:
- un invio alla volta, ognuno atteso (``wait=True``): l'ordine resta
  cronologico anche quando discord.py aspetta sui limiti di frequenza;
  canali in serie, mai in parallelo;
- nessuna menzione vera (``AllowedMentions.none()``);
- un canale di backup che ha già messaggi non si ricopia (rilanci senza
  doppioni) e, se non si riesce a controllarlo, non si scrive;
- un errore su un canale o su un messaggio non ferma la copia.
"""

from __future__ import annotations

import logging

import aiohttp
import discord

from core.backup_mirror_logic import nome_sicuro_per_webhook

logger = logging.getLogger("iyokai.backup_messages")

MESSAGGI_PER_CANALE = 50
MAX_CONTENUTO = 2000
_TIPI_COPIABILI = (discord.MessageType.default, discord.MessageType.reply)


def contenuto_da_copiare(message) -> str | None:
    """Testo + link degli allegati, entro 2000 caratteri. None se non c'è nulla da copiare
    (messaggi di sistema, solo embed)."""
    if message.type not in _TIPI_COPIABILI:
        return None
    contenuto = message.content or ""
    if message.attachments:
        link = "\n".join(a.url for a in message.attachments)
        contenuto = f"{contenuto}\n{link}" if contenuto else link
    contenuto = contenuto[:MAX_CONTENUTO]
    return contenuto or None


def _webhook(url: str, sessione) -> discord.Webhook:
    return discord.Webhook.from_url(url, session=sessione)


async def _destinazione_vuota(canale) -> bool:
    """True solo se si è controllato e il canale non ha messaggi."""
    try:
        async for _ in canale.history(limit=1):
            return False
    except discord.HTTPException:
        return False
    return True


async def _copia_canale(sorgente, webhook, limite: int, riepilogo) -> None:
    try:
        recenti = [m async for m in sorgente.history(limit=limite)]
    except discord.HTTPException:
        riepilogo.canali_messaggi_saltati += 1
        return
    for message in reversed(recenti):  # dal più vecchio al più nuovo
        contenuto = contenuto_da_copiare(message)
        if contenuto is None:
            riepilogo.messaggi_saltati += 1
            continue
        try:
            await webhook.send(
                content=contenuto,
                username=nome_sicuro_per_webhook(message.author.display_name),
                avatar_url=str(message.author.display_avatar.url),
                allowed_mentions=discord.AllowedMentions.none(),
                wait=True,
            )
        except (discord.NotFound, discord.Forbidden):
            logger.warning("Webhook di copia non più valido (canale %s): canale abbandonato.", sorgente.id)
            riepilogo.canali_messaggi_saltati += 1
            return
        except discord.HTTPException:
            riepilogo.messaggi_falliti += 1
            continue
        riepilogo.messaggi_copiati += 1


async def copia_messaggi(
    main_guild,
    backup_guild,
    mappa_canali: dict[int, int],
    mappa_webhook: dict[int, str],
    riepilogo,
    limite: int = MESSAGGI_PER_CANALE,
    sessione: aiohttp.ClientSession | None = None,
) -> None:
    """``mappa_canali``: canale del main -> canale del backup; ``mappa_webhook``: canale del main -> URL."""
    propria = sessione is None
    sessione = sessione or aiohttp.ClientSession()
    try:
        for canale_id, backup_id in mappa_canali.items():
            sorgente = main_guild.get_channel(canale_id)
            destinazione = backup_guild.get_channel(backup_id)
            url = mappa_webhook.get(canale_id)
            if not isinstance(sorgente, discord.TextChannel):
                continue  # voce e altro: niente messaggi da copiare
            if (
                not isinstance(destinazione, discord.TextChannel)
                or url is None
                or not await _destinazione_vuota(destinazione)
            ):
                riepilogo.canali_messaggi_saltati += 1
                continue
            await _copia_canale(sorgente, _webhook(url, sessione), limite, riepilogo)
    finally:
        if propria:
            await sessione.close()
