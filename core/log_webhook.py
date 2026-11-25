"""
core/log_webhook.py
===================
Log via webhook (#113, D33): se il server lo ha acceso (`/admin-log webhook`), le righe di log di un canale di testo
escono da un webhook del canale, raggruppate fino a 10 embed in un solo messaggio (attesa massima 2 secondi).
I webhook hanno limiti di frequenza propri, separati da quelli del bot: un picco di log non consuma le richieste
del bot. Messaggi con bottoni o file e ogni errore del webhook (cancellato, permesso tolto) tornano al canale normale.
Log a nome dell'utente (D74, #160): spento di base; se acceso (`log_webhook_utente`) i log dei messaggi modificati e
cancellati escono dal webhook con il nome e l'avatar di chi ha scritto (nome pulito, suffisso « · log», nessuna menzione),
un messaggio al secondo per canale e al massimo 20 in attesa (oltre, la riga esce raggruppata e senza identità).
Funzioni coperte: SPEC §E (iYokai Mod), #113, #160, LOG-025 (righe vicine in un solo messaggio)
Dipende da: core/repositories/log_webhook_repo.py, core/migrations/0361_log_webhooks.sql
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata

import discord

from core.repositories.log_webhook_repo import ChiaveNonConfigurata, log_webhook_repo
from core.blocchi_deboli import BlocchiDeboli

logger = logging.getLogger("iyokai.log_webhook")

SETTING_LOG_WEBHOOK = "log_webhook"
SETTING_LOG_WEBHOOK_UTENTE = "log_webhook_utente"
SUFFISSO_NOME = " · log"
MAX_NOME_WEBHOOK = 80  # limite di Discord per il nome di un messaggio di webhook
MAX_NOMI_IN_CODA = 20
PAUSA_TRA_NOMI = 1.0
NOME_PREDEFINITO = "utente"
# Discord rifiuta questi nomi dentro `username` di un webhook.
_NOMI_VIETATI = re.compile(r"discord|clyde", re.IGNORECASE)
NOME_WEBHOOK = "iYokai log"
ATTESA_RAGGRUPPO = 2.0
MAX_EMBED_PER_MESSAGGIO = 10  # limite di Discord per un messaggio di webhook
MAX_CARATTERI_MESSAGGIO = 5500  # il limite di Discord è 6000 per messaggio: margine
_SOLO_EMBED = frozenset({"embed", "embeds"})
_SOLO_CANALE = ("view", "file", "files")  # bottoni: li gestisce il bot; file: il webhook li chiude anche se fallisce

# (guild_id, channel_id) -> wrapper vivo: tiene la coda e il webhook in cache.
_vivi: dict[tuple[int, int], "CanaleWebhook"] = {}
# (guild_id, channel_id) -> blocco: righe insieme su un canale nuovo creano un solo webhook.
_blocchi = BlocchiDeboli()


def nome_a_nome_utente(nome: str | None) -> str:
    """
    Il nome mostrato dal webhook: da 1 a 80 caratteri, senza caratteri di controllo né le parole che Discord
    rifiuta («discord», «clyde»), con il suffisso « · log». Un nome vuoto diventa «utente».
    """
    testo = unicodedata.normalize("NFKC", nome or "")
    testo = "".join(c for c in testo if unicodedata.category(c)[0] != "C")
    while True:
        nuovo = _NOMI_VIETATI.sub("", testo)
        if nuovo == testo:
            break
        testo = nuovo
    testo = " ".join(testo.split())
    testo = testo[: MAX_NOME_WEBHOOK - len(SUFFISSO_NOME)].strip() or NOME_PREDEFINITO
    return testo + SUFFISSO_NOME


class CanaleWebhook:
    """Un canale di log visto come destinazione: ha `id`, `guild` e `send`, come un TextChannel."""

    def __init__(self, canale: discord.TextChannel, webhook: discord.Webhook) -> None:
        self._canale = canale
        self._webhook = webhook
        self.id = canale.id
        self.guild = canale.guild
        self._coda: list[discord.Embed] = []
        self._task: asyncio.Task | None = None
        self._coda_nomi: list[tuple[discord.Embed, str, str | None]] = []
        self._task_nomi: asyncio.Task | None = None

    def __getattr__(self, nome):  # il resto (name, mention, permissions_for...) è del canale vero
        return getattr(self._canale, nome)

    async def send(self, **kw):
        if set(kw) <= _SOLO_EMBED and (kw.get("embed") is not None or kw.get("embeds")):
            embeds = [kw["embed"]] if kw.get("embed") is not None else list(kw["embeds"])
            for embed in embeds:
                await self._accoda(embed)
            return None
        if any(kw.get(nome) for nome in _SOLO_CANALE):
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

    async def invia_a_nome(self, embed: discord.Embed, nome: str, avatar_url: str | None) -> None:
        """Un log col nome e l'avatar di un utente: un messaggio al secondo; con la coda piena esce raggruppato."""
        if len(self._coda_nomi) >= MAX_NOMI_IN_CODA:
            await self._accoda(embed)
            return
        self._coda_nomi.append((embed, nome, avatar_url))
        if self._task_nomi is None or self._task_nomi.done():
            self._task_nomi = asyncio.create_task(self._svuota_nomi(), name=f"log-webhook-nomi-{self.id}")

    async def _svuota_nomi(self) -> None:
        while self._coda_nomi:
            embed, nome, avatar_url = self._coda_nomi.pop(0)
            try:
                await self._webhook.send(
                    embed=embed, username=nome, avatar_url=avatar_url, allowed_mentions=discord.AllowedMentions.none()
                )
            except (discord.NotFound, discord.Forbidden):
                await self._dimentica()
                await self._dal_canale(embed)
            except discord.HTTPException as errore:
                logger.warning("Webhook dei log del canale %s non ha risposto (%s): scrive il canale.", self.id, errore.status)
                await self._dal_canale(embed)
            if self._coda_nomi:
                await asyncio.sleep(PAUSA_TRA_NOMI)

    async def _dal_canale(self, embed: discord.Embed) -> None:
        try:
            await self._canale.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            logger.warning("Log non inviato nel canale %s.", self.id)

    async def svuota_finale(self) -> None:
        """Allo spegnimento: le righe a nome utente escono raggruppate, senza pausa."""
        resto, self._coda_nomi = self._coda_nomi, []
        for embed, _nome, _avatar in resto:
            self._coda.append(embed)
        await self.svuota()

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
        nuovo = await canale.create_webhook(name=NOME_WEBHOOK, reason="Log via webhook (/admin-log webhook)")
        await log_webhook_repo.salva(canale.guild.id, canale.id, nuovo.id, nuovo.token)
    except ChiaveNonConfigurata:
        await nuovo.delete(reason="Chiave di cifratura mancante")
        return None
    except discord.HTTPException as errore:
        logger.info("Webhook dei log non creato nel canale %s (%s).", canale.id, errore.status)
        return None
    return nuovo


async def a_nome_utente_acceso(guild_id: int) -> bool:
    """I log dei messaggi escono col nome dell'utente (base: no). Senza database o con un errore: no."""
    from core.database import db

    try:
        return await db.get_guild_setting(guild_id, SETTING_LOG_WEBHOOK_UTENTE) is True
    except Exception:  # noqa: BLE001
        return False


async def imposta_a_nome_utente(guild_id: int, attivo: bool, changed_by: int | None) -> None:
    """Il punto unico (D16) per accendere o spegnere i log a nome utente: lo usano il comando e il pannello."""
    from core.database import db

    await db.set_guild_setting(guild_id, SETTING_LOG_WEBHOOK_UTENTE, bool(attivo), changed_by)


async def invia_a_nome_utente(dest, embed: discord.Embed, autore) -> bool:
    """
    Manda `embed` col nome e l'avatar di `autore` se `dest` è un webhook e il server lo ha acceso.
    True se l'ha preso in carico; False: si scrive come sempre.
    """
    if not isinstance(dest, CanaleWebhook) or autore is None:
        return False
    if not await a_nome_utente_acceso(dest.guild.id):
        return False
    try:
        avatar = autore.display_avatar.url
    except Exception:  # noqa: BLE001
        avatar = None
    await dest.invia_a_nome(embed, nome_a_nome_utente(getattr(autore, "display_name", None)), avatar)
    return True


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
    async with _blocchi.prendi(chiave):
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
        await vivo.svuota_finale()


async def spegni_server(guild: discord.Guild, client) -> int:
    """Log via webhook spenti: toglie i webhook dal database e da Discord (se si può). Restituisce quanti."""
    for (g, c), vivo in list(_vivi.items()):
        if g == guild.id:
            await vivo.svuota_finale()
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
