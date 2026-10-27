"""
core/backup_messages_logic.py
=============================
Messaggi via webhook, impersonando l'autore: la copia degli ultimi N messaggi
di ogni canale nel server di backup (D8, M 12.17) e le chat salvate di un
canale (fino a 1000 messaggi) da ricaricare dopo, anche in un altro canale.
Gli allegati si ricaricano come file finché il link vale (≤ 10 MiB per
messaggio), poi come link; i messaggi fissati si rifissano.

Regole di sicurezza:
- un invio alla volta, ognuno atteso (``wait=True``): l'ordine resta
  cronologico anche quando discord.py aspetta sui limiti di frequenza;
  canali in serie, mai in parallelo;
- nessuna menzione vera (``AllowedMentions.none()``);
- un canale di backup che ha già messaggi non si ricopia (rilanci senza
  doppioni) e, se non si riesce a controllarlo, non si scrive;
- un errore su un canale o su un messaggio non ferma la copia.
Funzioni coperte: SPEC §11.15, M 12.17, BKP-013, BKP-016, BKP-026, BKP-027
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

import aiohttp
import discord

from core.backup_mirror_logic import nome_sicuro_per_webhook

logger = logging.getLogger("iyokai.backup_messages")

MESSAGGI_PER_CANALE = 50
MAX_CONTENUTO = 2000
TIPI_COPIABILI = (discord.MessageType.default, discord.MessageType.reply)


MAX_ALLEGATI_BYTE = 10 * 1024 * 1024  # LIMITI Parte 4, punto 13


def allegati_come_file(allegati) -> list:
    """BKP-013: gli allegati da ricaricare come file (in ordine, finché il totale resta ≤ 10 MiB)."""
    scelti, totale = [], 0
    for a in allegati:
        dimensione = getattr(a, "size", None)
        if dimensione is None or not hasattr(a, "to_file") or totale + dimensione > MAX_ALLEGATI_BYTE:
            continue
        scelti.append(a)
        totale += dimensione
    return scelti


def contenuto_da_copiare(message, come_file=()) -> str | None:
    """Testo + link degli allegati che non vanno come file, entro 2000 caratteri.
    None se non c'è nulla da copiare (messaggi di sistema, solo embed)."""
    if message.type not in TIPI_COPIABILI:
        return None
    contenuto = message.content or ""
    link = "\n".join(a.url for a in message.attachments if a not in come_file)
    if link:
        contenuto = f"{contenuto}\n{link}" if contenuto else link
    contenuto = contenuto[:MAX_CONTENUTO]
    return contenuto or None


async def _rifissa(destinazione, inviato) -> None:
    """BKP-016: il messaggio copiato torna fissato (serve il permesso di fissare)."""
    if destinazione is None or inviato is None:
        return
    try:
        await destinazione.get_partial_message(inviato.id).pin()
    except discord.HTTPException:
        logger.info("Messaggio %s non rifissato in %s", inviato.id, destinazione.id)


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


async def file_degli_allegati(allegati) -> list[discord.File]:
    file = []
    for a in allegati:
        try:
            file.append(await a.to_file())
        except discord.HTTPException:
            continue  # link scaduto o file sparito: resta fuori
    return file


async def _copia_canale(sorgente, webhook, limite: int, riepilogo, destinazione=None) -> None:
    try:
        recenti = [m async for m in sorgente.history(limit=limite)]
    except discord.HTTPException:
        riepilogo.canali_messaggi_saltati += 1
        return
    for message in reversed(recenti):  # dal più vecchio al più nuovo
        if message.type not in TIPI_COPIABILI:
            riepilogo.messaggi_saltati += 1
            continue
        come_file = allegati_come_file(message.attachments)
        file = await file_degli_allegati(come_file)
        contenuto = contenuto_da_copiare(message, come_file)
        if contenuto is None and not file:
            riepilogo.messaggi_saltati += 1
            continue
        try:
            inviato = await webhook.send(
                content=contenuto,
                username=nome_sicuro_per_webhook(message.author.display_name),
                avatar_url=str(message.author.display_avatar.url),
                allowed_mentions=discord.AllowedMentions.none(),
                wait=True,
                **({"files": file} if file else {}),
            )
        except (discord.NotFound, discord.Forbidden):
            logger.warning("Webhook di copia non più valido (canale %s): canale abbandonato.", sorgente.id)
            riepilogo.canali_messaggi_saltati += 1
            return
        except discord.HTTPException:
            riepilogo.messaggi_falliti += 1
            continue
        riepilogo.messaggi_copiati += 1
        if getattr(message, "pinned", False):
            await _rifissa(destinazione, inviato)


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
            await _copia_canale(sorgente, _webhook(url, sessione), limite, riepilogo, destinazione)
    finally:
        if propria:
            await sessione.close()


# ---------------------------------------------------------------- chat salvate (BKP-026/027)
MAX_CHAT = 1000
MAX_ALLEGATI_PER_MESSAGGIO = 10
NOME_WEBHOOK_CHAT = "iYokai Backup"
MAX_WEBHOOK_PER_CANALE = 15


async def leggi_chat(canale, quanti: int) -> list[dict]:
    """Gli ultimi `quanti` messaggi (≤ 1000), dal più vecchio, come dati."""
    righe = []
    async for m in canale.history(limit=max(1, min(quanti, MAX_CHAT))):
        if m.type not in TIPI_COPIABILI:
            continue
        righe.append({
            "autore": m.author.display_name[:80],
            "avatar": str(m.author.display_avatar.url),
            "contenuto": (m.content or "")[:MAX_CONTENUTO],
            "allegati": [
                {"nome": a.filename[:100], "url": a.url, "size": a.size}
                for a in m.attachments[:MAX_ALLEGATI_PER_MESSAGGIO]
            ],
            "fissato": bool(getattr(m, "pinned", False)),
            "ora": m.created_at.isoformat(timespec="seconds"),
        })
    righe.reverse()
    return righe


async def webhook_chat(canale):
    """Il webhook «iYokai Backup» del canale (riusato se c'è). None se il canale ne ha già 15."""
    esistenti = await canale.webhooks()
    for hook in esistenti:
        if hook.name == NOME_WEBHOOK_CHAT and hook.token:
            return hook
    if len(esistenti) >= MAX_WEBHOOK_PER_CANALE:
        return None
    return await canale.create_webhook(name=NOME_WEBHOOK_CHAT, reason="Ricarica di una chat salvata")


@dataclass
class RiepilogoChat:
    copiati: int = 0
    saltati: int = 0
    falliti: int = 0
    allegati_come_link: int = 0
    annullato: bool = False

    def testo(self) -> str:
        righe = [f"✅ Messaggi ricaricati: {self.copiati}"]
        if self.annullato:
            righe.insert(0, "⏹️ Ricarica annullata: i messaggi già inviati restano.")
        if self.saltati:
            righe.append(f"⏭️ Vuoti, saltati: {self.saltati}")
        if self.falliti:
            righe.append(f"⚠️ Non inviati: {self.falliti}")
        if self.allegati_come_link:
            righe.append(f"🔗 Allegati scaduti o troppo grandi, rimessi come link: {self.allegati_come_link}")
        return "\n".join(righe)


async def _allegati_salvati(allegati: list[dict], scarica) -> tuple[list[discord.File], list[str]]:
    """BKP-013: file finché il link vale e il totale resta ≤ 10 MiB; il resto come link."""
    file, link, totale = [], [], 0
    for a in allegati:
        dati = None
        if (a.get("size") or 0) + totale <= MAX_ALLEGATI_BYTE:
            dati = await scarica(a["url"], MAX_ALLEGATI_BYTE - totale)
        if dati is None:
            link.append(a["url"])
            continue
        totale += len(dati)
        file.append(discord.File(io.BytesIO(dati), filename=a.get("nome") or "file"))
    return file, link


async def ricarica_chat(
    messaggi: list[dict],
    webhook,
    destinazione,
    avanza: Callable[[str, int, int], Awaitable[bool]],
    scarica: Callable[[str, int], Awaitable[bytes | None]],
) -> RiepilogoChat:
    """Un messaggio alla volta, in ordine; `avanza` salva lo stato e dice se fermarsi."""
    r = RiepilogoChat()
    for indice, m in enumerate(messaggi, 1):
        if await avanza("messaggi", indice, len(messaggi)):
            r.annullato = True
            break
        file, link = await _allegati_salvati(m.get("allegati", []), scarica)
        r.allegati_come_link += len(link)
        contenuto = "\n".join(x for x in [m.get("contenuto") or "", *link] if x)[:MAX_CONTENUTO]
        if not contenuto and not file:
            r.saltati += 1
            continue
        try:
            inviato = await webhook.send(
                content=contenuto or None,
                username=nome_sicuro_per_webhook(m.get("autore") or "Utente"),
                avatar_url=m.get("avatar"),
                allowed_mentions=discord.AllowedMentions.none(),
                wait=True,
                **({"files": file} if file else {}),
            )
        except (discord.NotFound, discord.Forbidden):
            r.falliti += len(messaggi) - indice + 1
            break  # webhook cancellato: inutile insistere
        except discord.HTTPException:
            r.falliti += 1
            continue
        r.copiati += 1
        if m.get("fissato"):
            await _rifissa(destinazione, inviato)
    return r
