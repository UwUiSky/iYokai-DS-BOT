"""
core/whitelabel_bot.py
======================
Bot con marchio proprio (NF-38, #109): un server premium collega un'applicazione Discord sua, con il suo nome e il suo
avatar. Il client del marchio resta connesso solo a quel server (esce da ogni altro), appare online con il nome
dell'applicazione e mostra il testo di stato scelto.
I comandi sono quelli del bot principale: all'avvio si registrano sull'applicazione del marchio, solo in quel server
(`core/command_sync.py`, impronta per marchio), e ogni interazione che il client del marchio riceve passa al bot
principale, che la esegue con i suoi cog. La risposta esce con il nome e l'avatar del marchio.
Funzioni coperte: SPEC §23 (NF-38)
Dipende da: core/repositories/whitelabel_repo.py, core/command_sync.py, core/migrations/0133_whitelabel.sql
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import discord

from core.bot_info import url_invito
from core import marchio_errori as errori_marchio
from core.repositories.whitelabel_repo import Marchio, whitelabel_repo

logger = logging.getLogger("iyokai.whitelabel")

MODULO_MARCHIO = "marchio"
MAX_TESTO_STATO = 100
ATTESA_SYNC_SECONDI = 300

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
    """I token del bot stesso (principale, creatore, Mod, musica, NSFW, App): non si possono collegare come marchio."""
    return {
        t
        for t in (
            config.YOKAI_BOT_TOKEN, config.YOKAI_CREATOR_TOKEN, config.YOKAI_MOD_TOKEN, config.NSFW_TOKEN,
            getattr(config, "YOKAI_APP_TOKEN", ""), *config.MUSIC_TOKENS,
        )
        if t
    }


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


def scope_marchio(guild_id: int) -> str:
    return f"marchio:{guild_id}"


def inoltra_interazioni(client: discord.Client, bot) -> None:
    """
    Le interazioni che arrivano al client del marchio le esegue il bot principale: l'oggetto `Interaction` nasce
    dallo stato del principale (suoi cog, sua cache, suoi controlli) e risponde con il token dell'interazione,
    cioè con l'identità del marchio. Si cambia solo il gestore dell'evento INTERAZIONE_CREATE di questo client.
    Passano solo le interazioni del server del marchio: chi possiede l'applicazione può registrarle comandi suoi
    (installazione utente, DM) e farli arrivare da altri server, dove il principale non deve eseguirli.
    """
    principale = bot._connection
    server = str(client.guild_id)

    def inoltra(dati) -> None:
        if str(dati.get("guild_id")) != server:
            logger.info("Marchio del server %s: interazione da fuori server ignorata.", server)
            return
        try:
            principale.parse_interaction_create(dati)
        except Exception as exc:  # noqa: BLE001 - un'interazione rotta non ferma il client
            errori_marchio.registra(client.guild_id, "interazione", exc)
            raise

    client._connection.parsers["INTERACTION_CREATE"] = inoltra


class _StatoForzato:
    """Per la risincronizzazione a mano: l'impronta salvata non conta, ma quella nuova si salva."""

    def __init__(self, stato) -> None:
        self._stato = stato

    async def leggi(self, scope: str) -> str | None:
        return None

    async def salva(self, scope: str, impronta: str) -> None:
        await self._stato.salva(scope, impronta)


async def sincronizza_comandi_marchio(
    client: discord.Client, bot, guild_id: int, application_id: int, stato, *, forza: bool = False
) -> str:
    """
    Registra i comandi globali del principale sull'applicazione del marchio, solo nel suo server. Solo se l'albero
    è cambiato dall'ultima volta (impronta salvata per questo marchio), a meno che `forza` (CFG-032). Mai eccezioni;
    un errore finisce nel registro degli errori del marchio.
    """
    from core.command_sync import sincronizza_se_cambiato

    if forza:
        stato = _StatoForzato(stato)

    albero = bot.tree
    comandi = list(albero.get_commands())
    traduttore = getattr(albero, "translator", None)

    async def sync() -> None:
        payload = [
            await c.get_translated_payload(albero, traduttore) if traduttore is not None else c.to_dict(albero)
            for c in comandi
        ]
        try:
            await client.http.bulk_upsert_guild_commands(application_id, guild_id, payload)
        except Exception as exc:
            errori_marchio.registra(guild_id, "comandi", exc)
            raise

    return await sincronizza_se_cambiato(scope_marchio(guild_id), comandi, albero, sync, stato)


class _ClientMarchio(discord.Client):
    """Un client che sta nel suo server, mostra lo stato, se ne va dagli altri e passa i comandi al principale."""

    def __init__(
        self, guild_id: int, testo_stato: str | None, bot=None, application_id: int | None = None
    ) -> None:
        intenti = discord.Intents.none()
        intenti.guilds = True
        super().__init__(intents=intenti)
        self.guild_id = guild_id  # prima di inoltra_interazioni, che lo legge
        self.testo_stato = testo_stato
        self.bot = bot
        self.application_id_marchio = application_id
        if bot is not None:
            inoltra_interazioni(self, bot)

    async def on_ready(self) -> None:
        if self.get_guild(self.guild_id) is None:
            await whitelabel_repo.imposta_stato(self.guild_id, STATO_NON_NEL_SERVER)
        else:
            await whitelabel_repo.imposta_stato(self.guild_id, STATO_ATTIVO)
            await self._registra_comandi()
        for guild in list(self.guilds):
            if guild.id != self.guild_id:
                await self._esci(guild)
        await self.applica_stato()

    async def _registra_comandi(self) -> None:
        """Un errore (per esempio manca lo scope dei comandi nell'invito) non ferma il marchio."""
        if self.bot is None or not self.application_id_marchio:
            return
        from core.command_sync import StatoSyncDatabase
        from core.database import db

        try:
            await sincronizza_comandi_marchio(
                self, self.bot, self.guild_id, self.application_id_marchio, StatoSyncDatabase(db.pool)
            )
        except Exception as exc:  # noqa: BLE001
            errori_marchio.registra(self.guild_id, "comandi", exc)
            logger.warning("Marchio del server %s: comandi non registrati (%s).", self.guild_id, type(exc).__name__)

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
        # Due `avvia` insieme (giro di allineamento e collegamento) non devono aprire due client con lo stesso token.
        self._blocco_avvio = asyncio.Lock()
        self._ultima_sync: dict[int, float] = {}
        self._sync_in_corso: set[int] = set()

    def in_esecuzione(self, guild_id: int) -> bool:
        task = self._task.get(guild_id)
        return task is not None and not task.done()

    async def avvia(self, guild_id: int) -> bool:
        """Avvia il client del server. False se non c'è un marchio, è spento o il server non è premium."""
        async with self._blocco_avvio:
            return await self._avvia(guild_id)

    async def _avvia(self, guild_id: int) -> bool:
        from core.premium import guild_has_premium_access

        if self.in_esecuzione(guild_id):
            return True
        try:
            letto = await whitelabel_repo.get_con_token(guild_id)
        except Exception as exc:  # noqa: BLE001 - token illeggibile (chiave cambiata, riga rovinata): solo questo marchio
            errori_marchio.registra(guild_id, "avvio", exc)
            logger.warning("Marchio del server %s: token non leggibile (%s).", guild_id, type(exc).__name__)
            await whitelabel_repo.imposta_stato(guild_id, STATO_ERRORE, type(exc).__name__)
            return False
        if letto is None or not letto[0].enabled:
            return False
        marchio, token = letto
        if not await guild_has_premium_access(guild_id, MODULO_MARCHIO, bot=self.bot):
            await whitelabel_repo.imposta_stato(guild_id, STATO_SENZA_PREMIUM)
            return False
        client = _ClientMarchio(guild_id, marchio.status_text, self.bot, marchio.application_id)
        self._client[guild_id] = client
        self._task[guild_id] = asyncio.create_task(self._esegui(guild_id, client, token), name=f"marchio-{guild_id}")
        return True

    async def _esegui(self, guild_id: int, client: _ClientMarchio, token: str) -> None:
        try:
            await client.start(token)
        except discord.LoginFailure as exc:
            errori_marchio.registra(guild_id, "login", exc)
            await whitelabel_repo.imposta_stato(guild_id, STATO_TOKEN_NON_VALIDO)
            await whitelabel_repo.imposta_abilitato(guild_id, False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - un marchio rotto non ferma il bot principale
            errori_marchio.registra(guild_id, "client", exc)
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

    async def risincronizza(self, guild_id: int) -> tuple[str, dict]:
        """
        Riscrive i comandi del marchio anche se l'albero non è cambiato (CFG-032). Restituisce la chiave del messaggio
        e i suoi valori. Una alla volta per server e non più di una ogni `ATTESA_SYNC_SECONDI` (se riuscita).
        """
        from core.command_sync import SINCRONIZZATA, StatoSyncDatabase
        from core.database import db

        client = self._client.get(guild_id)
        if client is None or not self.in_esecuzione(guild_id) or not client.is_ready() or not client.application_id_marchio:
            return "mar_non_acceso", {}
        if guild_id in self._sync_in_corso:
            return "mar_sync_in_corso", {}
        trascorso = time.monotonic() - self._ultima_sync.get(guild_id, -ATTESA_SYNC_SECONDI)
        if trascorso < ATTESA_SYNC_SECONDI:
            return "mar_sync_attesa", {"secondi": int(ATTESA_SYNC_SECONDI - trascorso) + 1}
        self._sync_in_corso.add(guild_id)
        try:
            esito = await sincronizza_comandi_marchio(
                client, self.bot, guild_id, client.application_id_marchio, StatoSyncDatabase(db.pool), forza=True
            )
        finally:
            self._sync_in_corso.discard(guild_id)
        if esito != SINCRONIZZATA:
            return "mar_sync_errore", {}
        self._ultima_sync[guild_id] = time.monotonic()
        return "mar_sync_ok", {}

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
                try:
                    await self.avvia(guild_id)
                except Exception:  # noqa: BLE001 - un marchio rotto non blocca gli altri
                    logger.warning("Marchio del server %s non avviato.", guild_id, exc_info=True)

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


def puo_usare_strumenti(user_id: int, proprietario_server: int | None, marchio: Marchio | None) -> bool:
    """
    Gli strumenti del marchio (risincronizza, errori) sono di chi possiede il bot con marchio: il proprietario del
    server o chi l'ha collegato. Un admin qualunque no (CFG-032).
    """
    if marchio is None:
        return False
    return user_id in {i for i in (proprietario_server, marchio.created_by) if i}


# ---------------------------------------------- punto unico (D16): comando e pannello
AZIONI = ("testo", "avvia", "ferma", "rimuovi")
AZIONI_CON_PREMIUM = frozenset({"imposta", "avvia", "testo"})


async def ha_premium(bot, guild_id: int) -> bool:
    """Il server ha sbloccato il marchio (premium o fase alpha)."""
    from core.premium import guild_has_premium_access

    return await guild_has_premium_access(guild_id, MODULO_MARCHIO, bot=bot)


def pulisci_testo(testo: str | None) -> str | None:
    """Il testo di stato: spazi tolti, vuoto = nessuno. ValueError se supera `MAX_TESTO_STATO`."""
    testo = (testo or "").strip()
    if len(testo) > MAX_TESTO_STATO:
        raise ValueError("Testo di stato troppo lungo.")
    return testo or None


async def collega_e_avvia(gestore: GestoreMarchio, bot, guild, token: str, user_id: int, *, config) -> Marchio:
    """
    Collega un token nuovo e riaccende il client (quello col token vecchio si ferma prima).
    Solleva `TokenRifiutato` con la chiave del messaggio, anche senza premium.
    Lo collega SOLO il proprietario del server: il bot con marchio riceve le interazioni dello staff, un admin
    qualunque non deve poterci mettere un bot suo. Un collegamento riuscito lascia una riga nello storico del server
    e un avviso a chi lo ha chiesto.
    """
    if user_id != getattr(guild, "owner_id", None):
        raise TokenRifiutato("mar_solo_proprietario")
    if not await ha_premium(bot, guild.id):
        raise TokenRifiutato("mar_richiede_premium")
    marchio = await collega_marchio(guild, token, user_id, config=config)
    await gestore.ferma(guild.id)
    await gestore.avvia(guild.id)
    await registra_modifica(bot, guild, user_id, "collegato", marchio.bot_name)
    return marchio


async def registra_modifica(bot, guild, user_id: int, cosa: str, nome_bot: str | None = None) -> None:
    """
    Una riga nello storico delle modifiche del server («marchio») e un avviso di sicurezza: chi cambia il bot con
    marchio lascia una traccia. Mai un'eccezione: la traccia mancata non annulla l'azione già fatta.
    """
    from core import web_panel_avvisi
    from core.database import db
    from core.i18n import testo_guild

    try:
        await db._record_config_change(guild.id, user_id, "setting", "marchio", None, cosa if not nome_bot else f"{cosa}:{nome_bot}"[:200])
        chiave = "mar_avviso_collegato" if cosa == "collegato" else "mar_avviso_rimosso"
        await web_panel_avvisi.avvisa(
            bot, guild, "sicurezza", await testo_guild(guild, chiave, utente=f"<@{user_id}>", nome=nome_bot or "-")
        )
    except Exception:  # noqa: BLE001
        logger.warning("Traccia del marchio non scritta nel server %s.", getattr(guild, "id", "?"), exc_info=True)


async def applica_azione(
    gestore: GestoreMarchio, bot, guild_id: int, azione: str, testo: str | None = None, *, autore_id: int | None = None
) -> str:
    """
    Una delle `AZIONI` su un marchio già collegato. Restituisce la chiave del messaggio per l'utente.
    ValueError per un'azione sconosciuta o un testo troppo lungo.
    """
    if azione not in AZIONI:
        raise ValueError("Azione del marchio sconosciuta.")
    testo = pulisci_testo(testo) if azione == "testo" else None
    if azione in AZIONI_CON_PREMIUM and not await ha_premium(bot, guild_id):
        return "mar_richiede_premium"
    if await whitelabel_repo.get(guild_id) is None:
        return "mar_nessun_marchio"
    if azione == "testo":
        await whitelabel_repo.imposta_testo_stato(guild_id, testo)
        await gestore.aggiorna_testo(guild_id, testo)
        return "mar_testo_ok" if testo else "mar_testo_azzerato"
    if azione == "avvia":
        await whitelabel_repo.imposta_abilitato(guild_id, True)
        return "mar_avviato" if await gestore.avvia(guild_id) else "mar_non_avviato"
    if azione == "ferma":
        await whitelabel_repo.imposta_abilitato(guild_id, False)
        await gestore.ferma(guild_id)
        return "mar_fermato"
    await gestore.ferma(guild_id)
    await whitelabel_repo.elimina(guild_id)
    guild = bot.get_guild(guild_id)
    if guild is not None and autore_id is not None:
        await registra_modifica(bot, guild, autore_id, "scollegato")
    return "mar_rimosso"
