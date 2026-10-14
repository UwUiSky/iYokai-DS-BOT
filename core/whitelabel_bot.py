"""
core/whitelabel_bot.py
======================
Bot con marchio proprio (NF-38, #109): un server premium collega un'applicazione Discord sua, con il suo nome e il suo
avatar. Il client del marchio resta connesso solo a quel server (esce da ogni altro), appare online con il nome
dell'applicazione e mostra il testo di stato scelto. I comandi restano quelli del bot principale: il client del marchio
non li gestisce.
Funzioni coperte: SPEC §23 (NF-38)
Dipende da: core/repositories/whitelabel_repo.py, core/migrations/0133_whitelabel.sql
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import discord

from core.bot_info import url_invito
from core.repositories.whitelabel_repo import Marchio, whitelabel_repo

logger = logging.getLogger("iyokai.whitelabel")

MODULO_MARCHIO = "marchio"
MAX_TESTO_STATO = 100

STATO_FERMO = "fermo"
STATO_ATTIVO = "attivo"
STATO_NON_NEL_SERVER = "non_nel_server"
STATO_TOKEN_NON_VALIDO = "token_non_valido"
STATO_SENZA_PREMIUM = "senza_premium"
STATO_ERRORE = "errore"


class TokenRifiutato(ValueError):
    """Il token non si può usare. `motivo` è la chiave del messaggio per l'utente."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


@dataclass(frozen=True)
class InfoApplicazione:
    bot_user_id: int
    application_id: int
    nome: str


def token_di_sistema(config) -> set[str]:
    """I token del bot stesso (principale, creatore, musica, NSFW): non si possono collegare come marchio."""
    return {t for t in (config.YOKAI_BOT_TOKEN, config.YOKAI_CREATOR_TOKEN, config.NSFW_TOKEN, *config.MUSIC_TOKENS) if t}


async def verifica_token(token: str) -> InfoApplicazione:
    """Prova il token con Discord (login e lettura dell'applicazione). Mai il token nei log o nei messaggi."""
    client = discord.Client(intents=discord.Intents.none())
    try:
        await client.login(token)
        applicazione = await client.application_info()
        utente = client.user
        if utente is None:
            raise TokenRifiutato("mar_token_non_valido")
        return InfoApplicazione(utente.id, applicazione.id, utente.name)
    except discord.LoginFailure as exc:
        raise TokenRifiutato("mar_token_non_valido") from exc
    except discord.HTTPException as exc:
        raise TokenRifiutato("mar_discord_non_risponde") from exc
    finally:
        await client.close()


class _ClientMarchio(discord.Client):
    """Un client senza comandi: sta nel suo server, mostra lo stato e se ne va dagli altri."""

    def __init__(self, guild_id: int, testo_stato: str | None) -> None:
        intenti = discord.Intents.none()
        intenti.guilds = True
        super().__init__(intents=intenti)
        self.guild_id = guild_id
        self.testo_stato = testo_stato

    async def on_ready(self) -> None:
        if self.get_guild(self.guild_id) is None:
            await whitelabel_repo.imposta_stato(self.guild_id, STATO_NON_NEL_SERVER)
        else:
            await whitelabel_repo.imposta_stato(self.guild_id, STATO_ATTIVO)
        for guild in list(self.guilds):
            if guild.id != self.guild_id:
                await self._esci(guild)
        await self.applica_stato()

    async def on_guild_join(self, guild: discord.Guild) -> None:
        if guild.id != self.guild_id:
            await self._esci(guild)
        else:
            await whitelabel_repo.imposta_stato(self.guild_id, STATO_ATTIVO)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        if guild.id == self.guild_id:
            await whitelabel_repo.imposta_stato(self.guild_id, STATO_NON_NEL_SERVER)

    async def _esci(self, guild: discord.Guild) -> None:
        try:
            await guild.leave()
            logger.info("Marchio del server %s: uscito dal server %s (non è il suo).", self.guild_id, guild.id)
        except discord.HTTPException:
            logger.warning("Marchio del server %s: uscita da %s fallita.", self.guild_id, guild.id)

    async def applica_stato(self) -> None:
        attivita = discord.CustomActivity(name=self.testo_stato[:MAX_TESTO_STATO]) if self.testo_stato else None
        await self.change_presence(activity=attivita, status=discord.Status.online)


class GestoreMarchio:
    """Tiene i client dei marchi. Un client per server; nessuno parte senza premium e senza essere abilitato."""

    def __init__(self, bot) -> None:
        self.bot = bot
        self._client: dict[int, _ClientMarchio] = {}
        self._task: dict[int, asyncio.Task] = {}

    def in_esecuzione(self, guild_id: int) -> bool:
        task = self._task.get(guild_id)
        return task is not None and not task.done()

    async def avvia(self, guild_id: int) -> bool:
        """Avvia il client del server. False se non c'è un marchio, è spento o il server non è premium."""
        from core.premium import guild_has_premium_access

        if self.in_esecuzione(guild_id):
            return True
        letto = await whitelabel_repo.get_con_token(guild_id)
        if letto is None or not letto[0].enabled:
            return False
        marchio, token = letto
        if not await guild_has_premium_access(guild_id, MODULO_MARCHIO, bot=self.bot):
            await whitelabel_repo.imposta_stato(guild_id, STATO_SENZA_PREMIUM)
            return False
        client = _ClientMarchio(guild_id, marchio.status_text)
        self._client[guild_id] = client
        self._task[guild_id] = asyncio.create_task(self._esegui(guild_id, client, token), name=f"marchio-{guild_id}")
        return True

    async def _esegui(self, guild_id: int, client: _ClientMarchio, token: str) -> None:
        try:
            await client.start(token)
        except discord.LoginFailure:
            await whitelabel_repo.imposta_stato(guild_id, STATO_TOKEN_NON_VALIDO)
            await whitelabel_repo.imposta_abilitato(guild_id, False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - un marchio rotto non ferma il bot principale
            logger.warning("Marchio del server %s fermato (%s).", guild_id, type(exc).__name__)
            await whitelabel_repo.imposta_stato(guild_id, STATO_ERRORE, type(exc).__name__)

    async def ferma(self, guild_id: int, stato: str = STATO_FERMO) -> None:
        client = self._client.pop(guild_id, None)
        task = self._task.pop(guild_id, None)
        if client is not None:
            await client.close()
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        try:
            await whitelabel_repo.imposta_stato(guild_id, stato)
        except Exception:  # noqa: BLE001 - ad esempio il marchio è già stato cancellato
            logger.debug("Stato del marchio %s non aggiornato.", guild_id)

    async def aggiorna_testo(self, guild_id: int, testo: str | None) -> None:
        client = self._client.get(guild_id)
        if client is not None and self.in_esecuzione(guild_id) and client.is_ready():
            client.testo_stato = testo
            await client.applica_stato()

    async def riconcilia(self) -> None:
        """
        Allinea i client al database: parte chi è abilitato e ha premium, si ferma chi non c'è più, è spento o
        senza premium, o il cui server non ha più il bot principale.
        """
        from core.premium import guild_has_premium_access

        abilitati = {m.guild_id: m for m in await whitelabel_repo.elenco_abilitati()}
        for guild_id in list(self._task):
            m = abilitati.get(guild_id)
            if m is None:
                await self.ferma(guild_id)
            elif self.bot.get_guild(guild_id) is None:
                await self.ferma(guild_id, STATO_FERMO)
            elif not await guild_has_premium_access(guild_id, MODULO_MARCHIO, bot=self.bot):
                await self.ferma(guild_id, STATO_SENZA_PREMIUM)
        for guild_id in abilitati:
            if not self.in_esecuzione(guild_id) and self.bot.get_guild(guild_id) is not None:
                await self.avvia(guild_id)

    async def ferma_tutti(self) -> None:
        for guild_id in list(self._task):
            await self.ferma(guild_id)


async def collega_marchio(guild, token: str, user_id: int, *, config) -> Marchio:
    """
    Verifica il token e lo collega al server. Solleva `TokenRifiutato` (con la chiave del messaggio) se non si può
    usare. Il chiamante poi avvia il client.
    """
    import asyncpg

    from core.repositories.whitelabel_repo import ChiaveNonConfigurata

    token = token.strip()
    if not token or token in token_di_sistema(config):
        raise TokenRifiutato("mar_token_non_valido")
    info = await verifica_token(token)
    principale = getattr(getattr(guild, "me", None), "id", None)
    if info.bot_user_id == principale:
        raise TokenRifiutato("mar_token_non_valido")
    try:
        await whitelabel_repo.salva(guild.id, token, info.bot_user_id, info.application_id, info.nome, user_id)
    except ChiaveNonConfigurata as exc:
        raise TokenRifiutato("mar_chiave_mancante") from exc
    except asyncpg.UniqueViolationError as exc:
        raise TokenRifiutato("mar_gia_usato") from exc
    marchio = await whitelabel_repo.get(guild.id)
    return marchio


def link_invito(marchio: Marchio) -> str | None:
    """Il link per far entrare il bot del marchio nel suo server."""
    return url_invito(marchio.application_id, marchio.guild_id)
