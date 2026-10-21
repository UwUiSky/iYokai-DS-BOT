"""
core/panel_bridge.py
====================
Il ponte tra il pannello web e il bot. Il pannello gira nello stesso
processo del bot: legge i server dalla memoria del bot, controlla i
permessi a ogni richiesta e scrive SOLO dai punti unici dei comandi
(D16: `core.config_schema`, `core.command_access.imposta_ruolo`).
Le cache del database si svuotano a ogni scrittura: il bot vede subito
il cambio, senza riavvio.
Anche i permessi dei gruppi di comandi per ruolo (#148): stato, link di
autorizzazione, risincronizzazione e revoca, dalle funzioni di
`core/command_permissions.py`. La verifica dalla pagina web (NF-21) passa di qui: impronte, doppi, poi gli
stessi controlli e ruoli del bottone di verifica. Il bot con marchio proprio (NF-38) passa dalle
stesse funzioni di `core/whitelabel_bot.py` usate da `/admin premium marchio`; l'aspetto del bot per
server (CFG-030) da `core/bot_aspetto.py`. La pagina «I miei dati» (#46) usa le funzioni di
`/utility privacy esporta|cancella`.
Funzioni coperte: SPEC §24.1–24.4, §24.7, §4.2, §4.3, §23.15 (NF-20, issue #91; NF-22, #93; NF-21, #92; #148; NF-38, #109; CFG-030, #122; #46)
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict

import discord

from core.command_access import (
    Livello,
    RuoloAdminNegato,
    TipoRuolo,
    decidi_accesso,
    imposta_ruolo,
    leggi_ruolo,
)
from core import alt_detection_logic as doppi_logica
from core.command_search_logic import ComandoInfo, raccogli_comandi
from core.config import config
from core.config_history_logic import TIPI_MODIFICA
from core.config_schema import ImpostazioneNonValida, imposta_lingua_server, imposta_modulo
from core.database import db
from core.premium import registry
from core.repositories.fingerprint_repo import fingerprint_repo
from core.web_panel_logic import pannello_configurato

logger = logging.getLogger("iyokai.panel_bridge")

MAX_RUOLI_MOSTRATI = 250
MAX_STORICO = 100
_DURATA_CACHE_COMANDI = 300.0
# Membri chiesti a Discord (non nella memoria del bot): tenuti poco, così ogni
# clic non diventa una chiamata all'API, ma un permesso tolto vale entro 30 secondi.
DURATA_CACHE_MEMBRI = 30.0
MAX_CACHE_MEMBRI = 1000
_cache_membri: OrderedDict[tuple[int, int], tuple[float, discord.Member | None]] = OrderedDict()

ETICHETTE_RUOLI = {
    TipoRuolo.ADMIN: "Ruolo admin del bot",
    TipoRuolo.MOD: "Ruolo mod del bot",
    TipoRuolo.MODBAN: "Ruolo ban del bot",
}


# ---------------------------------------------------------------- permessi
async def _membro(guild: discord.Guild, user_id: int, *, chiedi_a_discord: bool) -> discord.Member | None:
    membro = guild.get_member(user_id)
    if membro is not None or not chiedi_a_discord:
        return membro
    chiave = (guild.id, user_id)
    adesso = time.monotonic()
    salvato = _cache_membri.get(chiave)
    if salvato is not None and salvato[0] > adesso:
        return salvato[1]
    try:
        membro = await guild.fetch_member(user_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        membro = None
    _cache_membri.pop(chiave, None)
    _cache_membri[chiave] = (adesso + DURATA_CACHE_MEMBRI, membro)
    while len(_cache_membri) > MAX_CACHE_MEMBRI:
        _cache_membri.popitem(last=False)
    return membro


async def puo_gestire(guild: discord.Guild, user_id: int, *, chiedi_a_discord: bool = True) -> bool:
    """
    Stessa regola dei comandi di `/admin` (Livello.ADMIN): «Gestisci server»,
    il ruolo admin del bot o il proprietario del server. Si controlla a ogni
    richiesta, con lo stato attuale del server.
    """
    membro = await _membro(guild, user_id, chiedi_a_discord=chiedi_a_discord)
    if membro is None:
        return False
    ruolo_admin = await leggi_ruolo(guild.id, TipoRuolo.ADMIN)
    return decidi_accesso(
        Livello.ADMIN,
        user_id=user_id,
        owner_bot_id=config.OWNER_ID,
        guild_owner_id=guild.owner_id,
        permessi=membro.guild_permissions,
        ruoli_utente_ids=[r.id for r in membro.roles],
        ruolo_configurato_id=ruolo_admin,
        ruolo_esiste=ruolo_admin is not None and guild.get_role(ruolo_admin) is not None,
    )


async def server_gestibile(bot, guild_id: int, user_id: int) -> discord.Guild | None:
    """Il server, solo se il bot c'è e l'utente lo può gestire adesso."""
    guild = bot.get_guild(guild_id)
    if guild is None or not await puo_gestire(guild, user_id):
        return None
    return guild


async def server_gestibili(bot, user_id: int) -> list[discord.Guild]:
    """I server dove il bot c'è e l'utente può gestirli (solo dalla memoria del bot)."""
    risultato = []
    for guild in bot.guilds:
        if await puo_gestire(guild, user_id, chiedi_a_discord=False):
            risultato.append(guild)
    return sorted(risultato, key=lambda g: g.name.lower())


# ----------------------------------------------------------------- lettura
async def stato_server(guild: discord.Guild) -> dict:
    """Moduli (per categoria), ruoli del bot e lingua del server."""
    moduli = []
    for modulo in registry.all_modules():
        moduli.append(
            {
                "nome": modulo.name,
                "titolo": modulo.display_name,
                "descrizione": modulo.description,
                "categoria": modulo.category,
                "premium": registry.is_module_premium(modulo.name),
                "attivo": await db.is_module_active_for_guild(guild.id, modulo.name),
            }
        )
    ruoli_bot = [
        {"tipo": tipo.name.lower(), "etichetta": ETICHETTE_RUOLI[tipo], "attuale": await leggi_ruolo(guild.id, tipo)}
        for tipo in TipoRuolo
    ]
    ruoli_server = [
        {"id": r.id, "nome": r.name}
        for r in sorted(guild.roles, key=lambda r: -r.position)
        if r.id != guild.id and not r.managed
    ][:MAX_RUOLI_MOSTRATI]
    return {
        "moduli": moduli,
        "ruoli_bot": ruoli_bot,
        "ruoli_server": ruoli_server,
        "lingua": await db.get_guild_language(guild.id),
    }


async def storico(guild_id: int, tipo: str | None = None) -> list:
    """Le ultime modifiche (comandi e pannello insieme: lo storico è uno solo)."""
    tipo = tipo if tipo in TIPI_MODIFICA else None
    return await db.get_config_history_filtrato(guild_id, limit=MAX_STORICO, change_type=tipo)


async def stato_premium(bot, guild: discord.Guild) -> dict:
    """Le stesse righe di `/admin premium stato`, più il link al negozio di Discord."""
    from cogs.utility.premium_server import url_negozio
    from core.premium import get_guild_premium_breakdown
    from core.premium_status_logic import righe_stato_server
    from core.repositories.module_subscription_repo import module_subscription_repo

    dettaglio = await get_guild_premium_breakdown(guild.id, bot=bot)
    scadenze = [
        f"{s.module_name} fino al {s.expires_at.date().isoformat()}"
        for s in await module_subscription_repo.list_for_guild(guild.id)
    ]
    return {
        "righe": righe_stato_server(dettaglio, scadenze),
        "alpha": bool(config.PREMIUM_ALPHA_UNLOCK_ALL),
        "negozio": url_negozio(getattr(bot, "application_id", None)),
    }


_cache_comandi: tuple[float, int, list[ComandoInfo]] | None = None


def comandi_del_bot(bot) -> list[ComandoInfo]:
    """L'albero dei comandi (la stessa fonte della ricerca dei comandi nel bot), in memoria per 5 minuti."""
    global _cache_comandi
    adesso = time.monotonic()
    if _cache_comandi is not None and _cache_comandi[1] == id(bot) and _cache_comandi[0] > adesso:
        return _cache_comandi[2]
    comandi = sorted(raccogli_comandi(bot.tree.get_commands()), key=lambda c: c.percorso)
    _cache_comandi = (adesso + _DURATA_CACHE_COMANDI, id(bot), comandi)
    return comandi


# ---------------------------------------------------------------- scrittura
async def applica_modulo(bot, guild: discord.Guild, nome: str, attivo: bool, user_id: int) -> bool:
    return await imposta_modulo(bot, guild.id, nome, attivo, user_id)


async def applica_lingua(guild: discord.Guild, codice: str, user_id: int) -> str:
    return await imposta_lingua_server(guild.id, codice, user_id)


async def applica_ruolo(guild: discord.Guild, tipo_nome: str, ruolo_id: int | None, user_id: int) -> None:
    """
    `tipo_nome`: admin, mod o modban. `ruolo_id` None toglie il ruolo.
    Il ruolo admin nuovo richiede «Amministratore» o il proprietario (D28).
    """
    try:
        tipo = TipoRuolo[tipo_nome.upper()]
    except KeyError:
        raise ImpostazioneNonValida("Tipo di ruolo non valido.") from None
    ruolo = None
    if ruolo_id is not None:
        ruolo = guild.get_role(ruolo_id)
        if ruolo is None or ruolo.managed:
            raise ImpostazioneNonValida("Questo ruolo non esiste in questo server.")
    try:
        await imposta_ruolo(
            guild, tipo, ruolo, changed_by=user_id, autore=await _membro(guild, user_id, chiedi_a_discord=True)
        )
    except RuoloAdminNegato:
        raise
    except ValueError as errore:
        raise ImpostazioneNonValida(str(errore)) from None


# ------------------------------------------------------- verifica web (NF-21)
METODO_WEB = "web"
MODULO_VERIFY = "verify"


def link_verifica_web(guild_id: int, user_id: int) -> str | None:
    """Il link personale della verifica web, o None se il pannello non è acceso."""
    if not pannello_configurato(
        config.OAUTH2_CLIENT_ID, config.OAUTH2_CLIENT_SECRET, config.WEB_PANEL_SECRET_KEY, config.WEB_PANEL_PUBLIC_URL
    ):
        return None
    token = doppi_logica.crea_token(config.WEB_PANEL_SECRET_KEY, guild_id, user_id)
    return doppi_logica.url_verifica(config.WEB_PANEL_PUBLIC_URL, token)


async def _verifica_aperta(bot, guild_id: int, user_id: int):
    """(server, membro) se il server usa la verifica web e il membro c'è; altrimenti (None, motivo)."""
    from core.repositories.verify_repo import verify_repo

    guild = bot.get_guild(guild_id)
    if guild is None:
        return None, "Il bot non è più in questo server."
    if not await db.is_module_active_for_guild(guild_id, MODULO_VERIFY):
        return None, "La verifica non è attiva in questo server."
    if (await verify_repo.get_config(guild_id)).method != METODO_WEB:
        return None, "Questo server non usa più la verifica dalla pagina web: torna su Discord."
    membro = await _membro(guild, user_id, chiedi_a_discord=True)
    if membro is None:
        return None, "Non sei (più) in questo server."
    return (guild, membro), None


async def pagina_verifica(bot, guild_id: int, user_id: int) -> tuple[str | None, str | None]:
    """(nome del server, None) se la verifica si può fare, altrimenti (None, motivo)."""
    trovato, motivo = await _verifica_aperta(bot, guild_id, user_id)
    return (trovato[0].name, None) if trovato else (None, motivo)


async def verifica_web(
    bot, chiave: str, guild_id: int, user_id: int, ip: str, user_agent: str | None, lingua: str | None
) -> tuple[bool, str]:
    """
    La verifica dalla pagina: salva le impronte (mai l'IP), cerca i doppi nello
    stesso server e li segnala allo staff (nessun ban automatico), poi gli
    stessi controlli e ruoli del bottone di verifica. (riuscita, testo).
    """
    trovato, motivo = await _verifica_aperta(bot, guild_id, user_id)
    if trovato is None:
        return False, motivo
    guild, membro = trovato
    cog = bot.get_cog("VerifyCog")
    if cog is None:
        return False, "La verifica non è disponibile in questo momento. Riprova tra poco."
    impronte = doppi_logica.impronte_richiesta(chiave, guild_id, ip, user_agent, lingua)
    uguali = await fingerprint_repo.registra(guild_id, user_id, impronte)
    doppi = doppi_logica.valuta_doppi(uguali, user_id, ipv4=doppi_logica.e_ipv4(ip))
    if doppi:
        from cogs.security.alt_detection import avvisa_staff

        nuovi = await fingerprint_repo.salva_doppi(guild_id, user_id, [(d.altro_user_id, d.livello) for d in doppi])
        if nuovi:
            await avvisa_staff(guild, membro, [d for d in doppi if d.altro_user_id in nuovi])
    esito = await cog.run_checks_and_finalize(guild, membro, captcha_ok=True)
    return esito.success, esito.reason


# ------------------------------------------- comandi nascosti per ruolo (#148)
async def stato_permessi_comandi(guild: discord.Guild, user_id: int) -> dict:
    """
    Se il server ha autorizzato il bot a scrivere i permessi dei gruppi di comandi
    (OAuth2 di un admin, `core/command_permissions.py`) e il link per farlo.
    Mai il token: solo chi l'ha dato e fino a quando vale.
    """
    from core.command_permissions import link_per_admin
    from core.repositories.command_permission_token_repo import command_permission_token_repo

    try:
        link = link_per_admin(guild.id, user_id)
        token = await command_permission_token_repo.get(guild.id) if link else None
    except Exception:  # chiave di cifratura non valida: il pannello resta usabile
        logger.warning("Stato dei permessi dei comandi non leggibile nel server %s.", guild.id, exc_info=True)
        link, token = None, None
    return {
        "link": link,
        "autorizzato": token is not None,
        "da": token.user_id if token else None,
        "scade": token.scade_il.date().isoformat() if token else None,
    }


async def risincronizza_permessi(bot, guild: discord.Guild) -> str:
    """Riscrive i permessi dei gruppi dai ruoli del bot; il codice dell'esito per la pagina."""
    from cogs.utility.config_strumenti import riassumi_esiti
    from core.command_permissions import risincronizza_server

    chiave, _ = riassumi_esiti(await risincronizza_server(bot, guild))
    return {
        "cfg_sync_ok": "permessi_ok",
        "cfg_sync_nessun_ruolo": "permessi_nessun_ruolo",
        "cfg_sync_non_autorizzato": "permessi_non_autorizzato",
        "cfg_sync_token_non_valido": "permessi_non_autorizzato",
    }.get(chiave, "permessi_parziale")


async def revoca_permessi_comandi(guild: discord.Guild, user_id: int) -> None:
    """Cancella l'autorizzazione: il bot non scrive più i permessi (quelli già scritti restano su Discord)."""
    from core.repositories.command_permission_token_repo import command_permission_token_repo

    await command_permission_token_repo.cancella(guild.id)
    logger.info("Autorizzazione dei permessi dei comandi revocata dal pannello nel server %s da %s.", guild.id, user_id)


# ------------------------------------------------ marchio proprio (NF-38, #109)
ESITI_MARCHIO_OK = frozenset({"mar_testo_ok", "mar_testo_azzerato", "mar_avviato", "mar_fermato", "mar_rimosso"})
# I soli testi del marchio che la pagina mostra da un codice nell'URL (nessuno ha segnaposto).
ESITI_MARCHIO = ESITI_MARCHIO_OK | {
    "mar_richiede_premium", "mar_nessun_marchio", "mar_non_avviato", "mar_token_non_valido",
    "mar_discord_non_risponde", "mar_chiave_mancante", "mar_gia_usato",
}


def _gestore_marchio(bot):
    """Il gestore dei client del marchio, dal cog acceso. None se il cog non è caricato."""
    return getattr(bot.get_cog("MarchioCog"), "gestore", None)


async def stato_marchio(bot, guild: discord.Guild) -> dict:
    """Cosa mostra la pagina del marchio. Mai il token: solo nome, stato, testo e link d'invito."""
    from core import whitelabel_bot as wl
    from core.i18n import t
    from core.repositories.whitelabel_repo import whitelabel_repo

    marchio = await whitelabel_repo.get(guild.id)
    return {
        "disponibile": _gestore_marchio(bot) is not None,
        "premium": await wl.ha_premium(bot, guild.id),
        "max_testo": wl.MAX_TESTO_STATO,
        "marchio": None if marchio is None else {
            "nome": marchio.bot_name,
            "stato": t(f"mar_stato_{marchio.last_state}", "it"),
            "acceso": marchio.enabled,
            "testo": marchio.status_text,
            "invito": wl.link_invito(marchio),
        },
    }


async def collega_marchio_web(bot, guild: discord.Guild, token: str, user_id: int) -> str:
    """Collega il token dal pannello (stessa funzione del comando). Il codice dell'esito per la pagina."""
    from core import whitelabel_bot as wl

    gestore = _gestore_marchio(bot)
    if gestore is None:
        return "marchio_non_disponibile"
    try:
        await wl.collega_e_avvia(gestore, bot, guild, token, user_id, config=config)
    except wl.TokenRifiutato as exc:
        return exc.motivo
    logger.info("Marchio collegato dal pannello nel server %s da %s.", guild.id, user_id)
    return "marchio_collegato"


async def applica_marchio(bot, guild: discord.Guild, azione: str, testo: str | None, user_id: int) -> str:
    """Testo di stato, accendi, spegni o scollega dal pannello (stessa funzione del comando)."""
    from core import whitelabel_bot as wl

    gestore = _gestore_marchio(bot)
    if gestore is None:
        return "marchio_non_disponibile"
    try:
        esito = await wl.applica_azione(gestore, bot, guild.id, azione, testo)
    except ValueError:
        return "non_valido"
    logger.info("Marchio del server %s: «%s» dal pannello da %s.", guild.id, azione, user_id)
    return esito


# --------------------------------------------- aspetto del bot per server (CFG-030, #122)
ESITI_ASPETTO = frozenset({
    "asp_ok", "asp_niente", "asp_richiede_premium", "asp_attendi", "asp_errore",
    "asp_immagine_grande", "asp_immagine_non_valida", "asp_testo_lungo", "cfg_nick_permesso",
})
# I testi del bot che la pagina mostra da un codice nell'URL, e quali sono buone notizie.
ESITI_TESTI = ESITI_MARCHIO | ESITI_ASPETTO
ESITI_TESTI_OK = ESITI_MARCHIO_OK | {"asp_ok"}


async def stato_aspetto(bot, guild: discord.Guild) -> dict:
    """Nickname, avatar e banner del bot in questo server, e se il premium c'è."""
    from core import bot_aspetto
    from core.premium import guild_has_premium_access

    return {
        **bot_aspetto.stato_aspetto(guild),
        "premium": await guild_has_premium_access(guild.id, bot_aspetto.MODULO_ASPETTO, bot=bot),
        "max_nick": bot_aspetto.MAX_NICK,
        "max_bio": bot_aspetto.MAX_BIO,
    }


async def applica_aspetto(bot, guild: discord.Guild, user_id: int, **campi) -> str:
    """Cambia l'aspetto dal pannello con la stessa funzione dei comandi. Il codice dell'esito."""
    from core import bot_aspetto

    return await bot_aspetto.applica_aspetto(bot, guild, user_id, **campi)


# ------------------------------------------------ i miei dati (GDPR, #46 parte web)
async def esporta_dati(user_id: int) -> tuple[bytes, list[str], list[str]]:
    """La copia dei dati dell'utente, la stessa di `/utility privacy esporta`: file, tabelle accorciate e troncate."""
    from core import forget_user_service as servizio

    dati = await servizio.esporta_utente(db.pool, user_id)
    contenuto, accorciate = servizio.serializza_esportazione(dati)
    return contenuto, accorciate, list(dati.get("troncate") or [])


async def chiedi_cancellazione(user_id: int, motivo: str | None) -> tuple[int, bool]:
    """La richiesta di cancellazione, come `/utility privacy cancella`: numero e se è nuova."""
    from core.repositories.data_deletion_request_repo import data_deletion_request_repo

    numero, nuova = await data_deletion_request_repo.crea(user_id, motivo)
    if nuova:
        logger.info("Richiesta di cancellazione %s dal pannello.", numero)
    return numero, nuova


async def testo_richiesta(user_id: int, numero: int) -> str | None:
    """Cosa succede e cosa resta (lo stesso testo del comando), solo per una richiesta dell'utente stesso."""
    from cogs.utility.privacy import TESTO_CANCELLA
    from core.repositories.data_deletion_request_repo import data_deletion_request_repo

    richiesta = await data_deletion_request_repo.get(numero)
    if richiesta is None or richiesta["user_id"] != user_id:
        return None
    return TESTO_CANCELLA.format(numero=numero)
