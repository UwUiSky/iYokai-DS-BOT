"""
core/log_webhook.py
===================
Log via webhook (#113, D33): se il server lo ha acceso (`/log webhook`), le righe di log di un canale di testo
escono da un webhook del canale, raggruppate fino a 10 embed in un solo messaggio (attesa massima 2 secondi).
I webhook hanno limiti di frequenza propri, separati da quelli del bot: un picco di log non consuma le richieste
del bot. Messaggi con bottoni o file e ogni errore del webhook (cancellato, permesso tolto) tornano al canale normale.
Funzioni coperte: SPEC §E (iYokai Mod), #113
Dipende da: core/repositories/log_webhook_repo.py, core/migrations/0361_log_webhooks.sql
"""

from __future__ import annotations

import asyncio
import logging

import discord

from core.repositories.log_webhook_repo import ChiaveNonConfigurata, log_webhook_repo

logger = logging.getLogger("iyokai.log_webhook")

SETTING_LOG_WEBHOOK = "log_webhook"
NOME_WEBHOOK = "iYokai log"
ATTESA_RAGGRUPPO = 2.0
MAX_EMBED_PER_MESSAGGIO = 10  # limite di Discord per un messaggio di webhook
MAX_CARATTERI_MESSAGGIO = 5500  # il limite di Discord è 6000 per messaggio: margine
_SOLO_EMBED = frozenset({"embed", "embeds"})

# (guild_id, channel_id) -> wrapper vivo: tiene la coda e il webhook in cache.
_vivi: dict[tuple[int, int], "CanaleWebhook"] = {}


class CanaleWebhook:
    """Un canale di log visto come destinazione: ha `id`, `guild` e `send`, come un TextChannel."""

    def __init__(self, canale: discord.TextChannel, webhook: discord.Webhook) -> None:
        self._canale = canale
        self._webhook = webhook
        self.id = canale.id
        self.guild = canale.guild
        self._coda: list[discord.Embed] = []
        self._task: asyncio.Task | None = None

    def __getattr__(self, nome):  # il resto (name, mention, permissions_for...) è del canale vero
        return getattr(self._canale, nome)

    async def send(self, **kw):
        if set(kw) <= _SOLO_EMBED and (kw.get("embed") is not None or kw.get("embeds")):
            embeds = [kw["embed"]] if kw.get("embed") is not None else list(kw["embeds"])
            for embed in embeds:
                await self._accoda(embed)
            return None
        if kw.get("view") is not None:  # i bottoni li ha solo il bot
            return await self._canale.send(**kw)
        try:
            return await self._webhook.send(wait=True, **kw)
        except (discord.NotFound, discord.Forbidden):
            await self._dimentica()
        return await self._canale.send(**kw)

    async def _accoda(self, embed: discord.Embed) -> None:
        if self._coda and (
            len(self._coda) >= MAX_EMBED_PER_MESSAGGIO
            or sum(len(e) for e in self._coda) + len(embed) > MAX_CARATTERI_MESSAGGIO
        ):
            await self.svuota()
        self._coda.append(embed)
        if len(self._coda) >= MAX_EMBED_PER_MESSAGGIO:
            await self.svuota()
        elif self._task is None or self._task.done():
            self._task = asyncio.create_task(self._dopo_attesa(), name=f"log-webhook-{self.id}")

    async def _dopo_attesa(self) -> None:
        await asyncio.sleep(ATTESA_RAGGRUPPO)
        await self.svuota()

    async def svuota(self) -> None:
        """Manda la coda in un solo messaggio. Se il webhook non va, riga per riga dal canale normale."""
        lotto, self._coda = self._coda, []
        if not lotto:
            return
        try:
            await self._webhook.send(embeds=lotto, allowed_mentions=discord.AllowedMentions.none())
            return
        except (discord.NotFound, discord.Forbidden):
            await self._dimentica()
        except discord.HTTPException as errore:
            logger.warning("Webhook dei log del canale %s non ha risposto (%s): scrive il canale.", self.id, errore.status)
        for embed in lotto:
            try:
                await self._canale.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                logger.warning("Log non inviato nel canale %s.", self.id)

    async def _dimentica(self) -> None:
        _vivi.pop((self.guild.id, self.id), None)
        await log_webhook_repo.elimina(self.guild.id, self.id)


async def _crea_o_leggi(canale: discord.TextChannel, client) -> discord.Webhook | None:
    registrato = await log_webhook_repo.get(canale.guild.id, canale.id)
    if registrato is not None:
        return discord.Webhook.partial(registrato[0], registrato[1], client=client)
    me = canale.guild.me
    if me is None or not canale.permissions_for(me).manage_webhooks:
        return None
    try:
        nuovo = await canale.create_webhook(name=NOME_WEBHOOK, reason="Log via webhook (/log webhook)")
        await log_webhook_repo.salva(canale.guild.id, canale.id, nuovo.id, nuovo.token)
    except ChiaveNonConfigurata:
        await nuovo.delete(reason="Chiave di cifratura mancante")
        return None
    except discord.HTTPException as errore:
        logger.info("Webhook dei log non creato nel canale %s (%s).", canale.id, errore.status)
        return None
    return nuovo


async def acceso(guild_id: int) -> bool:
    """Il server ha acceso i log via webhook. Senza database o con un errore: no (si scrive dal canale)."""
    from core.database import db

    try:
        return await db.get_guild_setting(guild_id, SETTING_LOG_WEBHOOK) is True
    except Exception:  # noqa: BLE001
        return False


def _client_di(canale: discord.TextChannel):
    """Il client che ha in cache il canale: serve la sua sessione HTTP per parlare al webhook."""
    return canale.guild._state._get_client()


async def avvolgi(canale: discord.TextChannel, attivo: bool):
    """
    La destinazione di log per `canale`: il webhook (con raggruppamento) se il server lo ha acceso e si può,
    altrimenti `canale` stesso. Mai solleva.
    """
    if not attivo:
        return canale
    chiave = (canale.guild.id, canale.id)
    vivo = _vivi.get(chiave)
    if vivo is not None:
        vivo._canale = canale  # il canale visto dal bot di turno (principale o Mod)
        return vivo
    try:
        webhook = await _crea_o_leggi(canale, _client_di(canale))
    except Exception:  # noqa: BLE001 - un errore qui non deve fermare il log
        logger.warning("Webhook dei log non disponibile per il canale %s.", canale.id, exc_info=True)
        return canale
    if webhook is None:
        return canale
    nuovo = CanaleWebhook(canale, webhook)
    _vivi[chiave] = nuovo
    return nuovo


async def svuota_tutti() -> None:
    """Allo spegnimento: manda le righe in coda."""
    for vivo in list(_vivi.values()):
        await vivo.svuota()


async def spegni_server(guild: discord.Guild, client) -> int:
    """Log via webhook spenti: toglie i webhook dal database e da Discord (se si può). Restituisce quanti."""
    for (g, c), vivo in list(_vivi.items()):
        if g == guild.id:
            await vivo.svuota()
            _vivi.pop((g, c), None)
    righe = await log_webhook_repo.elimina_server(guild.id)
    for _canale_id, webhook_id, token in righe:
        if token is None:
            continue
        try:
            await discord.Webhook.partial(webhook_id, token, client=client).delete(reason="Log via webhook spenti")
        except discord.HTTPException:
            logger.info("Webhook %s non cancellato da Discord (già tolto o permesso mancante).", webhook_id)
    return len(righe)
