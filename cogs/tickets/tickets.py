"""
cogs/tickets/tickets.py
==========================
Sistema di ticket: pannello con bottone "Apri Ticket" (persistente,
sopravvive a un riavvio del bot — vedi TicketPanelView più sotto),
creazione di un canale privato, comandi di gestione (claim, add,
remove, rename, priority, close, forceclose).

Configurazione per server, via `guild_config.settings` (stesso
pattern già usato in report.py, basic_logs.py):
- `ticket_category_id`: la categoria Discord dove creare i canali
  (usata come fallback quando non è configurata nessuna categoria
  select-menu — SPEC.md §13.2, vedi TicketCategorySelectView)
- `ticket_support_role_id`: (legacy, un solo ruolo) e
  `ticket_support_role_ids` (SPEC.md §13.13, lista JSON di più
  ruoli) — combinati con core.ticket_logic.merge_support_role_ids,
  entrambi vedono automaticamente ogni ticket appena creato, oltre
  all'utente che lo ha aperto

Chi altro può vedere i ticket oltre all'utente e ai ruoli di
supporto configurati: chiunque abbia già visibilità sulla categoria
per permessi propri (impostati direttamente in Discord dall'admin,
non gestiti da iYokai) — il bot non tenta di replicare o sostituire
la gestione dei permessi di categoria di Discord, solo di aggiungere
gli overwrite specifici del singolo ticket.

SPEC.md §13.10/§13.11 (transcript automatico alla chiusura, inviato
nel canale log + in DM all'utente): la lettura dei messaggi avviene
via channel.history() PRIMA di cancellare il canale. Il testo dei
messaggi arriva solo con l'intent Message Content acceso (main.py):
senza, il transcript lo dice in testa. Un transcript grande viene
diviso in più file sotto i 10 MiB. Vedi core/ticket_logic.py per la
costruzione pura del testo.

Limiti di Discord rispettati qui: menu delle categorie (25 voci,
etichetta 100), nome del canale (100), 2 rinomine ogni 10 minuti (il
canale nasce già con il numero giusto; /ticket rename passa da
core/channel_rename.py), ticket aperti per utente (predefinito 1,
fino a 5 con /admin-ticket limite, impostazione `ticket_max_per_utente`;
il controllo è sotto blocco in ticket_repo.create_ticket).

/ticket close: l'eliminazione del canale dopo l'attesa passa dallo
scheduler persistente (core/scheduler.py, azione
`ticket_delete_channel`), così sopravvive a un riavvio del bot o a una
ricarica del cog; gli errori temporanei di Discord vengono riprovati
dallo scheduler. /ticket forceclose elimina subito e funziona anche su
un ticket già chiuso il cui canale è rimasto.
Catalogo #120: le opzioni dei pannelli (core/ticket_opzioni_logic.py, comandi in
opzioni.py) decidono apertura, nome, permessi, avvisi, presa in carico e chiusura;
qui anche `/ticket note` e `/ticket chiedi-chiusura` (azione `ticket_richiesta_chiusura`).
Funzioni coperte: SPEC §13.2–§13.20, §22.9–§22.12 (pannelli, modulo, chiusura
automatica, voto, limite per utente), §8.18 (risposte standard, in risposte.py)
"""

# NF-13 (#84): pannelli multipli con modulo di domande, chiusura automatica
# per inattività (scheduler, azione `ticket_autoclose`) e voto a stelle in DM.
# Le regole pure stanno in core/ticket_form_logic.py, i dati in
# core/repositories/ticket_form_repo.py. I bottoni dei pannelli e del voto sono
# DynamicItem: rispondono anche dopo un riavvio (bot.add_dynamic_items in setup).

from __future__ import annotations

import asyncio
import io
import logging
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.channel_rename import (
    RenameRateLimited,
    rename_channel,
    rename_limit_message,
    rename_tracker,
)
from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, SOTTOGRUPPI, comando_di_gruppo
from core.database import db
from core.i18n import testo_guild, testo_per
from core.repositories.ticket_form_repo import (
    DomandaModulo,
    PannelloGiaEsistente,
    PannelloTicket,
    TroppeDomande,
    TroppiMotivi,
    TroppiPannelli,
    ticket_form_repo,
)
from core import ticket_form_logic as form
from core import ticket_opzioni_logic as opz_logic
from core.repositories.ticket_automazioni_repo import ticket_automazioni_repo
from core.repositories.ticket_opzioni_repo import ticket_opzioni_repo
from core.ticket_opzioni_logic import Opzioni
from core.repositories.ticket_repo import (
    VALID_PRIORITIES,
    PannelloPienoError,
    TicketAlreadyOpenError,
    ticket_repo,
)
from core.ticket_logic import (
    MAX_CATEGORY_LABEL_LENGTH,
    MAX_EMOJI_LENGTH,
    MAX_TICKET_CATEGORIES,
    MESSAGE_CONTENT_WARNING,
    build_transcript_text,
    format_duration_seconds,
    format_transcript_line,
    is_first_response,
    looks_like_emoji,
    LIVELLO_ADDETTO,
    LIVELLO_ADMIN,
    e_admin_ticket,
    merge_support_role_ids,
    ruoli_con_accesso,
    split_text_by_size,
    truncate_label,
)
from core import ticket_gestione_logic as gestione
from core import ticket_thread_logic as thread_logic
from core import ticket_transcript_logic as tr_logic
from core.repositories.ticket_gestione_repo import (
    EtichettaGiaEsistente,
    TroppeEtichette,
    ticket_gestione_repo,
)
from core.immagini_pipeline import analizza_immagine
from core.immagini_byte_logic import PULITA
from core.ticket_transcript_logic import AllegatoT
from core.premium import PremiumModule, registry
from core.role_safety import motivo_ruolo_automatico_non_assegnabile
from core.scheduler import in_seconds, scheduler
from core.ui_base import BaseModal, BaseView, _rispondi_con_errore, _utente_o_server_in_blacklist
from cogs.moderation._shared import ensure_module_enabled
from cogs.logging.basic_logs import SETTING_LOG_CHANNEL
from core import channel_router as router
from core.channel_router import TIPO_EVENTI

logger = logging.getLogger("iyokai.tickets")

MODULE_TICKETS = "tickets"

# Sotto-gruppo dei comandi degli admin.
GESTIONE_TICKET = ("ticket", "Ticket: configurazione, pannello, categorie, ruoli di supporto, statistiche")
# Sotto-gruppo con i ticket avanzati (NF-13, NF-33, #139).
ADMIN_TICKET = ("ticket", "Ticket avanzati: pannelli, modulo, chiusura, DM, risposte")

SETTING_CATEGORY = "ticket_category_id"
SETTING_SUPPORT_ROLE = "ticket_support_role_id"
SETTING_SUPPORT_ROLES = "ticket_support_role_ids"
SETTING_MAX_PER_UTENTE = "ticket_max_per_utente"
LIMITE_PER_UTENTE_MAX = 5

# custom_id fisso: è quello che permette a discord.py di rilegare
# un click su un bottone di un messaggio VECCHIO (creato prima
# dell'ultimo riavvio del bot) alla view registrata come persistente
# in setup() — vedi bot.add_view() in fondo al file.
OPEN_TICKET_CUSTOM_ID = "iyokai_ticket_open"

# Azione dello scheduler che elimina il canale di un ticket chiuso.
TICKET_DELETE_ACTION_TYPE = "ticket_delete_channel"
RITARDO_ELIMINAZIONE_SECONDI = 10
TESTO_CANALE_RESTA = "Il canale resta qui, chiuso: lo staff può riaprirlo o eliminarlo."

PRIORITY_EMOJI = {"normal": "🟢", "high": "🟠", "urgent": "🔴"}

# TKT-056: motivo di chiusura salvato col ticket (compare anche nel transcript).
MAX_MOTIVO_CHIUSURA = 500
# TKT-058: quanti ticket chiude in una volta /admin-ticket chiudi-tutti (ognuno ha il suo transcript).
MAX_CHIUSURA_DI_MASSA = 25

# Il nome di un canale Discord va da 1 a 100 caratteri (LIM-3).
MAX_CHANNEL_NAME_LENGTH = 100

# NF-13: chiusura automatica per inattività (scheduler persistente).
TICKET_AUTOCLOSE_ACTION_TYPE = "ticket_autoclose"
# #139: sollecito se nessuno dello staff risponde entro N minuti (gestito da cogs/tickets/risposte.py).
TICKET_SOLLECITO_ACTION_TYPE = "ticket_sollecito"
# TKT-055: chiusura dopo N ore senza risposta alla richiesta di chiusura.
TICKET_RICHIESTA_CHIUSURA_ACTION_TYPE = "ticket_richiesta_chiusura"
# L'attività si scrive nel database al più una volta al minuto per canale.
_ATTIVITA_MAX_VOCI = 500
_ATTIVITA_OGNI_SECONDI = 60

# Un file allegato deve restare sotto i 10 MiB (LIM-55). Ci fermiamo a
# 8 per lasciare margine al resto della richiesta.
MAX_TRANSCRIPT_FILE_BYTES = 8 * 1024 * 1024
MAX_BYTE_IMMAGINE_TRANSCRIPT = 8 * 1024 * 1024  # un'immagine più grande resta solo nome e peso

# Chi sta aprendo un ticket in questo momento: (id server, id utente).
# Ferma il doppio clic prima che nasca un secondo canale. La garanzia
# vera resta il controllo sotto blocco in ticket_repo.create_ticket.
_aperture_in_corso: set[tuple[int, int]] = set()

MESSAGGIO_TICKET_GIA_APERTO = (
    "Hai già un ticket aperto su questo server. Chiudilo prima di aprirne uno nuovo."
)


def _messaggio_limite(limite: int) -> str:
    if limite <= 1:
        return MESSAGGIO_TICKET_GIA_APERTO
    return (
        f"Hai già {limite} ticket aperti su questo server, il massimo consentito. "
        "Chiudine uno prima di aprirne un altro."
    )


async def _limite_per_utente(guild_id: int) -> int:
    """NF-13: quanti ticket aperti può avere un utente (default 1, /admin-ticket limite)."""
    valore = await db.get_guild_setting(guild_id, SETTING_MAX_PER_UTENTE, default=1)
    try:
        return min(max(int(valore), 1), LIMITE_PER_UTENTE_MAX)
    except (TypeError, ValueError):
        return 1


async def _support_role_ids(guild_id: int) -> list[int]:
    """SPEC.md §13.13 — combina il ruolo legacy con la lista nuova."""
    legacy = await db.get_guild_setting(guild_id, SETTING_SUPPORT_ROLE)
    extra = await db.get_guild_setting(guild_id, SETTING_SUPPORT_ROLES, default=[])
    return merge_support_role_ids(legacy, extra)


async def _opzioni_pannello(panel_id: int | None) -> Opzioni:
    """Le opzioni del pannello (#120); un ticket senza pannello usa i valori predefiniti."""
    if panel_id is None:
        return Opzioni()
    return await ticket_opzioni_repo.opzioni(panel_id)


async def _ruoli_staff(guild_id: int, panel_id: int | None = None) -> list[int]:
    """TKT-044: la squadra del pannello, se ne ha una; altrimenti i ruoli di supporto del server."""
    opzioni = await _opzioni_pannello(panel_id)
    if opzioni.ruoli_staff:
        return list(opzioni.ruoli_staff)
    return await _support_role_ids(guild_id)


async def _membro_staff(member, guild_id: int, panel_id: int | None = None) -> bool:
    if not isinstance(member, discord.Member) or getattr(member, "bot", False) is True:
        return False
    if member.guild_permissions.manage_guild:
        return True
    return bool(set(await _ruoli_staff(guild_id, panel_id)) & {r.id for r in member.roles})


async def _ruoli_admin(guild_id: int) -> set[int]:
    """TKT-045: i ruoli dello staff con livello «admin»."""
    return set(await ticket_repo.ruoli_admin(guild_id))


async def _membro_admin(member, guild_id: int, panel_id: int | None = None) -> bool:
    """TKT-045: admin dei ticket (chiude, forza, usa «Solo admin»). Vedi core.ticket_logic.e_admin_ticket."""
    if not isinstance(member, discord.Member) or getattr(member, "bot", False) is True:
        return False
    return e_admin_ticket(
        member.guild_permissions.manage_guild,
        {r.id for r in member.roles},
        await _ruoli_staff(guild_id, panel_id),
        await _ruoli_admin(guild_id),
    )


async def _is_ticket_admin(interaction: discord.Interaction, ticket=None) -> bool:
    if interaction.guild is None:
        return False
    return await _membro_admin(interaction.user, interaction.guild.id, getattr(ticket, "panel_id", None))


async def _is_ticket_staff(interaction: discord.Interaction, ticket=None) -> bool:
    """
    SPEC.md §13.9: chi fa parte dello staff dei ticket — chi ha il
    permesso Discord Manage Server, oppure chi ha almeno uno dei
    ruoli di supporto configurati (§13.13), o della squadra del pannello
    del ticket (TKT-044). Allo staff sono riservati forceclose, claim,
    priority, add e remove; /ticket close resta aperto a chi ha aperto
    il ticket, se il pannello lo permette (TKT-057).
    """
    if interaction.guild is None:
        return False
    return await _membro_staff(
        interaction.user, interaction.guild.id, getattr(ticket, "panel_id", None)
    )


async def esito_apertura(guild: discord.Guild, member, panel_id: int | None) -> opz_logic.Esito:
    """TKT-017…024: lista nera, sospensione, regole, orari, tetto del pannello e pausa."""
    ruoli = [r.id for r in getattr(member, "roles", [])]
    staff = await _membro_staff(member, guild.id, panel_id)
    situazione = await ticket_opzioni_repo.situazione(guild.id, member.id, ruoli, panel_id)
    return opz_logic.decidi_apertura(
        opz_logic.Richiedente(member.id, frozenset(ruoli), staff), situazione, datetime.now(timezone.utc)
    )


async def _open_ticket_channel(
    interaction: discord.Interaction,
    guild: discord.Guild,
    category: discord.CategoryChannel,
    category_label: str | None,
    *,
    panel: PannelloTicket | None = None,
    campi: list[tuple[str, str]] | None = None,
    utente: discord.Member | None = None,
    motivo: str | None = None,
    citato: discord.Message | None = None,
):
    """
    Logica di apertura di un ticket condivisa dal bottone unico
    (nessuna categoria configurata), dal select menu categorie
    (SPEC.md §13.2), dai pannelli, da `/ticket apri` e dal menu sul
    messaggio — l'interazione arriva già deferred, quindi qui si usa
    sempre .followup. `utente` è per chi si apre il ticket (TKT-008:
    lo staff a nome di un utente). Restituisce il canale, o None.
    """
    utente = utente or interaction.user
    chiave = (guild.id, utente.id)
    if chiave in _aperture_in_corso:
        await interaction.followup.send(
            await testo_per(interaction, "tickets_sto_gia_aprendo_il_tuo"), ephemeral=True
        )
        return None
    _aperture_in_corso.add(chiave)
    try:
        return await _crea_ticket(
            interaction, guild, category, category_label, panel=panel, campi=campi,
            utente=utente, motivo=motivo, citato=citato,
        )
    finally:
        _aperture_in_corso.discard(chiave)


def _categoria_con_posto(
    guild: discord.Guild, category: discord.CategoryChannel, opzioni: Opzioni
) -> discord.CategoryChannel | None:
    """TKT-030: la categoria principale, o la prima di riserva sotto i 50 canali."""
    candidate = [category]
    for categoria_id in opzioni.categorie_riserva:
        riserva = guild.get_channel(categoria_id)
        if isinstance(riserva, discord.CategoryChannel):
            candidate.append(riserva)
    scelta = opz_logic.prima_con_posto([(c.id, len(c.channels)) for c in candidate])
    return next((c for c in candidate if c.id == scelta), None)


def _overwrites_del_ticket(
    guild: discord.Guild, utente, opzioni: Opzioni, ruoli_staff: list[int], reperibili: list
) -> dict:
    """Chi vede il canale: l'utente (con i permessi scelti, TKT-041), lo staff, gli osservatori (TKT-042), i reperibili."""
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        utente: discord.PermissionOverwrite(**opz_logic.permessi_utente(opzioni.permessi_negati)),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True
        ),
    }
    for role_id in opzioni.ruoli_osservatori:
        role = guild.get_role(role_id)
        if role is not None and role_id != guild.id:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, read_message_history=True, send_messages=False, add_reactions=False
            )
    for role_id in ruoli_staff:
        role = guild.get_role(role_id)
        if role is not None and role_id != guild.id:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )
    for membro in reperibili:
        overwrites[membro] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        )
    return overwrites


async def _dai_ruoli_durante(guild: discord.Guild, utente, channel_id: int, opzioni: Opzioni) -> None:
    """TKT-043: ruoli dati all'apertura e salvati col ticket, per toglierli alla chiusura."""
    ruoli = []
    for role_id in opzioni.ruoli_durante:
        # Rivisto a ogni apertura: il ruolo può aver preso permessi forti dopo la configurazione.
        if motivo_ruolo_automatico_non_assegnabile(guild, role_id):
            continue
        ruoli.append(guild.get_role(role_id))
    if not ruoli or not isinstance(utente, discord.Member):
        return
    try:
        await utente.add_roles(*ruoli, reason="Ticket aperto")
    except discord.HTTPException:
        logger.warning("Ruoli del ticket non dati a %s nel server %s.", utente.id, guild.id)
        return
    await ticket_repo.set_ruoli_dati(channel_id, [r.id for r in ruoli])


async def _avvisi_di_apertura(
    channel, guild: discord.Guild, utente, opzioni: Opzioni, reperibili: list, numero: int
) -> None:
    """TKT-037 ping (ruoli, @here, reperibili; poi cancellati se scelto) e TKT-039 DM all'utente."""
    ruoli = [r for r in opzioni.ping_ruoli if r != guild.id and guild.get_role(r) is not None]
    parti = [f"<@&{r}>" for r in ruoli] + [m.mention for m in reperibili]
    if opzioni.ping_here:
        parti.insert(0, "@here")
    if parti:
        try:
            ping = await channel.send(
                " ".join(parti)[:2000],
                allowed_mentions=discord.AllowedMentions(
                    everyone=opzioni.ping_here,
                    roles=[discord.Object(id=r) for r in ruoli],
                    users=[discord.Object(id=m.id) for m in reperibili],
                ),
            )
            if opzioni.ping_cancella:
                await ping.delete()
        except discord.HTTPException:
            logger.warning("Avviso di apertura non inviato nel ticket %s.", channel.id)
    if opzioni.dm_apertura:
        testo = opz_logic.riempi(
            opzioni.dm_apertura, utente=utente.mention, server=guild.name, numero=numero
        )
        try:
            await utente.send(f"{testo}\n{channel.jump_url}"[:2000])
        except discord.HTTPException:
            logger.info("DM di apertura non consegnato a %s (DM chiusi?).", utente.id)


async def _vista_assistente(guild_id: int):
    """Il bottone «Chiedi all'assistente» (§25.65), solo dove l'admin ha acceso l'AI. Non blocca mai l'apertura."""
    try:
        from cogs.ai.ticket_ai import AssistenteTicketView
        from core.repositories.ai_repo import ai_repo

        return AssistenteTicketView() if (await ai_repo.get_config(guild_id)).attivo else None
    except Exception:  # noqa: BLE001
        logger.warning("Bottone dell'assistente non aggiunto al ticket.", exc_info=True)
        return None


async def _vista_benvenuto(interaction, vista_ai, ticket):
    """Il messaggio di benvenuto: bottone dell'assistente (se c'è) e menu «Gestisci» dello staff (una riga in più)."""
    if ticket is None:
        return vista_ai
    vista = vista_ai if vista_ai is not None else BaseView(timeout=None)
    vista.add_item(MenuGestisci(ticket.id, await _etichette_gestisci(interaction)))
    return vista


_COMPITI_AI: set[asyncio.Task] = set()  # riferimenti tenuti finché il compito non finisce


async def _prima_risposta_ai(client, channel, user_id: int, guild_id: int, panel_id, motivo, campi) -> None:
    """Prima risposta automatica (§25.66) se in apertura c'è già un testo della persona. Parte in un compito a parte:
    l'apertura del ticket non aspetta l'AI."""
    cog = client.get_cog("AiTicketCog")
    contenuto = "\n".join([motivo or "", *(v for _, v in (campi or []))]).strip()
    if cog is None or panel_id is None or not contenuto:
        return

    async def lavoro() -> None:
        try:
            await cog.dopo_apertura(channel, user_id, guild_id, panel_id, contenuto)
        except Exception:  # noqa: BLE001
            logger.warning("Prima risposta automatica non riuscita all'apertura.", exc_info=True)

    compito = asyncio.create_task(lavoro())
    _COMPITI_AI.add(compito)
    compito.add_done_callback(_COMPITI_AI.discard)


async def _saluto_vocale(client, channel, utente, guild_id: int) -> None:
    """Saluto vocale di Yokai all'apertura (§14.19), se la voce è accesa nel server. Compito a parte: l'apertura non aspetta."""
    cog = client.get_cog("AiVoceCog")
    if cog is None:
        return
    compito = asyncio.create_task(cog.saluto_ticket(channel, guild_id, utente))
    _COMPITI_AI.add(compito)
    compito.add_done_callback(_COMPITI_AI.discard)


def _dati_errore_thread(guild, opzioni) -> dict:
    padre = guild.get_channel(opzioni.canale_padre_id) if opzioni.canale_padre_id else None
    mancanti = thread_logic.permessi_mancanti(padre.permissions_for(guild.me)) if isinstance(padre, discord.TextChannel) else []
    return {"canale": padre.mention if padre is not None else "", "permessi": ", ".join(mancanti)}


async def _crea_thread_privato(guild, opzioni, nome: str, motivo: str, *, utente=None):
    """
    TKT-031: il ticket nasce come thread privato nel canale padre del pannello. Restituisce (thread, None)
    oppure (None, chiave del testo d'errore). Prima si controllano i permessi del bot, che chi apre veda
    il canale padre (altrimenti non vede il thread) e il tetto di 1.000 thread attivi di Discord.
    """
    padre = guild.get_channel(opzioni.canale_padre_id)
    if not isinstance(padre, discord.TextChannel):
        return None, "tickets_thread_padre_mancante"
    if thread_logic.tetto_raggiunto(len(getattr(guild, "threads", ()))):
        return None, "tickets_thread_troppi"
    if thread_logic.permessi_mancanti(padre.permissions_for(guild.me)):
        return None, "tickets_thread_permessi"
    if utente is not None:
        suoi = padre.permissions_for(utente)
        if not (suoi.view_channel and suoi.send_messages_in_threads):
            return None, "tickets_thread_utente_non_vede"
    thread = await padre.create_thread(
        name=thread_logic.nome_thread(nome), type=discord.ChannelType.private_thread, invitable=False,
        auto_archive_duration=thread_logic.ARCHIVIO_MINUTI, reason=motivo,
    )
    return thread, None


async def _entrano_nel_thread(thread, user_ids: list[int]) -> None:
    """Chi ha aperto il ticket e i reperibili entrano subito; uno che non entra non ferma gli altri."""
    for uid in thread_logic.chi_aggiungere(user_ids[0], user_ids[1:]):
        try:
            await thread.add_user(discord.Object(id=uid))
        except discord.HTTPException:
            logger.warning("Utente %s non aggiunto al thread del ticket %s.", uid, thread.id)


async def _avviso_thread_allo_staff(guild, thread, opzioni, utente, numero: int) -> None:
    """
    TKT-032: avviso con il bottone «Entra» nel canale degli avvisi dello staff. Mai nel canale padre:
    lo vede chiunque possa aprire un ticket. Senza canale degli avvisi lo staff entra dalla menzione del ruolo.
    """
    dove = guild.get_channel(opzioni.canale_avvisi_id or 0)
    if dove is None:
        return
    embed = discord.Embed(
        title=(await testo_guild(guild, "tickets_thread_avviso_titolo", numero=numero))[:256],
        description=(await testo_guild(guild, "tickets_thread_avviso_testo", utente=utente.mention, thread=thread.mention))[:4000],
        color=discord.Color.blurple(),
    )
    try:
        vista = BaseView(timeout=None)
        vista.add_item(BottoneEntra(thread.id, await testo_guild(guild, "tickets_thread_entra")))
        await dove.send(embed=embed, view=vista, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        logger.warning("Avviso del thread %s non inviato allo staff.", thread.id)


async def _elimina_canale_pronto(canale, motivo: str) -> None:
    """Un canale uscito dalla riserva senza diventare un ticket si elimina: non resta vuoto per sempre."""
    try:
        await canale.delete(reason=motivo)
    except discord.HTTPException:
        logger.warning("Canale di riserva %s non eliminato.", canale.id)


async def _svuota_riserva(guild, panel_id: int, motivo: str) -> None:
    """TKT-035: elimina tutti i canali pronti del pannello (riserva spenta o pannello eliminato)."""
    while (canale_id := await ticket_automazioni_repo.prendi_riserva(panel_id)) is not None:
        canale = guild.get_channel(canale_id)
        if canale is not None:
            await _elimina_canale_pronto(canale, motivo)


async def _canale_dalla_riserva(guild, category, panel_id, nome, overwrites, motivo):
    """TKT-035: usa un canale vuoto già pronto del pannello (stessa categoria), se c'è. Una sola modifica."""
    if panel_id is None:
        return None
    for _ in range(3):
        canale_id = await ticket_automazioni_repo.prendi_riserva(panel_id)
        if canale_id is None:
            return None
        canale = guild.get_channel(canale_id)
        if not isinstance(canale, discord.TextChannel):
            continue  # cancellato a mano
        if canale.category_id != category.id:
            await _elimina_canale_pronto(canale, "Riserva: la categoria del pannello è cambiata")
            continue
        try:
            await canale.edit(name=nome, overwrites=overwrites, reason=motivo)
        except discord.HTTPException:
            await _elimina_canale_pronto(canale, "Riserva: canale non modificabile")
            continue
        rename_tracker.record(canale.id)
        return canale
    return None


async def _crea_ticket(
    interaction: discord.Interaction,
    guild: discord.Guild,
    category: discord.CategoryChannel,
    category_label: str | None,
    *,
    panel: PannelloTicket | None = None,
    campi: list[tuple[str, str]] | None = None,
    utente: discord.Member | None = None,
    motivo: str | None = None,
    citato: discord.Message | None = None,
):
    utente = utente or interaction.user
    per_conto = utente.id != interaction.user.id
    panel_id = panel.id if panel is not None else None
    fuori_orario = False
    tetto_pannello = None
    if not per_conto:
        # TKT-017…024 (per lo staff che apre a nome di un utente decide lo staff).
        esito = await esito_apertura(guild, utente, panel_id)
        if not esito.permesso:
            await interaction.followup.send(esito.messaggio[:2000], ephemeral=True)
            return None
        fuori_orario = esito.fuori_orario
        tetto_pannello = esito.tetto_pannello
    opzioni = await _opzioni_pannello(panel_id)

    limite = await _limite_per_utente(guild.id)
    already_open = await ticket_repo.count_open_tickets_for_user(guild.id, utente.id)
    if already_open >= limite:
        await interaction.followup.send(
            _messaggio_limite(limite) if not per_conto else await testo_per(interaction, "tickets_ha_gia_il_massimo_di", mention=utente.mention),
            ephemeral=True,
        )
        return None

    come_thread = opzioni.tipo == "thread" and opzioni.canale_padre_id is not None
    categoria_pannello = category  # i canali pronti (TKT-035) stanno qui e ci sono già: non serve posto
    if not come_thread:
        category = _categoria_con_posto(guild, category, opzioni)
        if category is None and not await ticket_automazioni_repo.ha_riserva(panel_id):
            await interaction.followup.send(
                await testo_per(interaction, "tickets_le_categorie_dei_ticket_sono"), ephemeral=True
            )
            return None
    ruoli_staff = await _ruoli_staff(guild.id, panel_id)
    ruoli_admin = await _ruoli_admin(guild.id)
    # TKT-046: con «solo admin» nel canale entrano solo i ruoli admin (e chi ha «Gestisci server»).
    ruoli_nel_canale = ruoli_con_accesso(ruoli_staff, ruoli_admin, opzioni.solo_admin)
    # Si ricontrolla a ogni apertura: chi ha perso il ruolo dello staff non vede più i ticket nuovi.
    reperibili = [
        m for m in (guild.get_member(uid) for uid in await ticket_opzioni_repo.reperibili(guild.id))
        if m is not None and m.id != utente.id and not m.bot
        and (m.guild_permissions.manage_guild or set(ruoli_nel_canale) & {r.id for r in m.roles})
    ]
    overwrites = _overwrites_del_ticket(guild, utente, opzioni, ruoli_nel_canale, reperibili)

    # Il numero si riserva prima, così il canale nasce già con il nome
    # giusto: rinominarlo dopo spenderebbe una delle 2 rinomine che
    # Discord concede ogni 10 minuti (LIM-3).
    ticket_number = await ticket_repo.reserve_ticket_number(guild.id)
    nome = opz_logic.nome_canale(
        opzioni.nome_modello, ticket_number, str(utente.name), str(getattr(utente, "display_name", "") or "")
    )

    # Il canale si crea PRIMA di registrare il ticket nel DB, così
    # se la creazione fallisce (permessi mancanti, categoria
    # piena — Discord limita 50 canali per categoria) non resta
    # un ticket "fantasma" senza canale reale.
    try:
        motivo_canale = f"Ticket aperto da {interaction.user}"[:512]
        if come_thread:
            channel, errore_thread = await _crea_thread_privato(guild, opzioni, nome, motivo_canale, utente=utente)
            if channel is None:
                await interaction.followup.send(await testo_per(interaction, errore_thread, **_dati_errore_thread(guild, opzioni)), ephemeral=True)
                return None
        else:
            channel = await _canale_dalla_riserva(guild, categoria_pannello, panel_id, nome, overwrites, motivo_canale)
            if channel is None and category is None:
                await interaction.followup.send(
                    await testo_per(interaction, "tickets_le_categorie_dei_ticket_sono"), ephemeral=True
                )
                return None
            if channel is None:
                channel = await category.create_text_channel(name=nome, overwrites=overwrites, reason=motivo_canale)
    except discord.Forbidden:
        await interaction.followup.send(
            await testo_per(interaction, "tickets_non_ho_permessi_per_creare"),
            ephemeral=True,
        )
        return None
    except discord.HTTPException:
        await interaction.followup.send(
            await testo_per(interaction, "tickets_impossibile_creare_il_canale_del"),
            ephemeral=True,
        )
        return None

    try:
        await ticket_repo.create_ticket(
            guild.id,
            utente.id,
            channel.id,
            category_label=category_label,
            ticket_number=ticket_number,
            panel_id=panel_id,
            max_aperti=limite,
            max_nel_pannello=tetto_pannello,
        )
    except TicketAlreadyOpenError as errore:
        # Un altro ticket dello stesso utente è nato nel frattempo: il
        # canale appena creato non deve restare orfano.
        try:
            await channel.delete(reason="Ticket doppio: l'utente ne ha già uno aperto")
        except discord.HTTPException:
            logger.warning("Canale del ticket doppio %s non eliminato.", channel.id)
        pieno = isinstance(errore, PannelloPienoError)
        await interaction.followup.send(
            await testo_per(interaction, "tickets_questo_pannello_ha_gia_il") if pieno else _messaggio_limite(limite),
            ephemeral=True,
        )
        return None

    await _dai_ruoli_durante(guild, utente, channel.id, opzioni)
    if come_thread:
        await ticket_repo.set_e_thread(channel.id, True)
        await _entrano_nel_thread(channel, [utente.id, *(m.id for m in reperibili)])
    elif opzioni.solo_admin:
        await ticket_repo.set_solo_admin(channel.id, True)

    if panel is not None and panel.welcome_text:
        descrizione = panel.welcome_text.replace("{utente}", utente.mention)[:4000]
    else:
        descrizione = (
            f"Ciao {utente.mention}, grazie per averci "
            f"contattato. Descrivi il tuo problema e lo staff ti "
            f"risponderà a breve."
        )
    embed = discord.Embed(
        title=await testo_per(interaction, "tickets_ticket", ticket_number=ticket_number, pubblica=True),
        description=descrizione,
        color=discord.Color.blurple(),
    )
    if category_label is not None:
        embed.add_field(name=await testo_per(interaction, "antinuke_categoria", pubblica=True), value=truncate_label(category_label))
    if per_conto:
        embed.add_field(name=await testo_per(interaction, "tickets_aperto_dallo_staff", pubblica=True), value=interaction.user.mention)
    if motivo:
        embed.add_field(name=await testo_per(interaction, "channelcontr_motivo", pubblica=True), value=motivo[:1024], inline=False)
    if citato is not None:
        testo_citato = (citato.content or "(senza testo)")[:900]
        embed.add_field(
            name=f"Messaggio di {citato.author}"[:256],
            value=f"{testo_citato}\n[Vai al messaggio]({citato.jump_url})"[:1024],
            inline=False,
        )
    if fuori_orario:
        embed.add_field(
            name=await testo_per(interaction, "tickets_fuori_orario", pubblica=True),
            value=(opzioni.fuori_orario_testo or "Lo staff risponde negli orari di apertura: "
                   + opz_logic.orari_come_testo(opzioni.orari, opzioni.fuso))[:1024],
            inline=False,
        )
    for nome_campo, valore_campo in (campi or [])[: 25 - len(embed.fields)]:
        embed.add_field(name=nome_campo, value=valore_campo, inline=False)
    # Discord rifiuta un embed oltre 6000 caratteri: senza benvenuto il ticket nascerebbe vuoto e
    # le risposte del modulo andrebbero perse. Si accorcia il testo di benvenuto, mai le risposte.
    eccesso = len(embed) - 6000
    if eccesso > 0:
        embed.description = descrizione[: max(0, len(descrizione) - eccesso - 1)] + "…"
    try:
        vista_ai = await _vista_assistente(guild.id)
        nuovo = await ticket_repo.get_ticket_by_channel(channel.id)
        vista = await _vista_benvenuto(interaction, vista_ai, nuovo)
        chiamati = [r for r in ruoli_nel_canale if come_thread and r != guild.id and guild.get_role(r) is not None]
        primo = await channel.send(
            content=" ".join([utente.mention, *(f"<@&{r}>" for r in chiamati)])[:2000], embed=embed,
            allowed_mentions=discord.AllowedMentions(users=[utente], roles=[discord.Object(id=r) for r in chiamati]),
            **({"view": vista} if vista else {}),
        )
        if opzioni.fissa_primo:
            await primo.pin(reason="Primo messaggio del ticket")
    except discord.HTTPException:
        logger.warning("Messaggio di benvenuto non inviato (o non fissato) nel ticket %s.", channel.id)

    await _avvisi_di_apertura(channel, guild, utente, opzioni, reperibili, ticket_number)
    if come_thread:
        await _avviso_thread_allo_staff(guild, channel, opzioni, utente, ticket_number)
    await _saluto_vocale(interaction.client, channel, utente, guild.id)
    await _prima_risposta_ai(interaction.client, channel, utente.id, guild.id, panel_id, motivo, campi)
    try:
        await suggerisci_articolo(channel, guild.id, motivo, campi)
    except Exception:  # noqa: BLE001 - il ticket esiste già: il suggerimento non lo blocca
        logger.warning("Articolo suggerito non riuscito nel ticket %s.", channel.id, exc_info=True)

    if panel is not None and panel.autoclose_minutes:
        try:
            await scheduler.schedule(
                guild.id,
                utente.id,
                TICKET_AUTOCLOSE_ACTION_TYPE,
                in_seconds(panel.autoclose_minutes * 60),
                {"channel_id": channel.id},
            )
        except Exception:  # noqa: BLE001 - il ticket esiste già: la chiusura automatica non lo blocca
            logger.exception("Chiusura automatica del ticket %s non pianificata.", channel.id)

    if panel is not None and panel.sollecito_minuti:
        try:
            await scheduler.schedule(
                guild.id,
                utente.id,
                TICKET_SOLLECITO_ACTION_TYPE,
                in_seconds(panel.sollecito_minuti * 60),
                {"channel_id": channel.id},
            )
        except Exception:  # noqa: BLE001 - il ticket esiste già: il sollecito non lo blocca
            logger.exception("Sollecito del ticket %s non pianificato.", channel.id)

    await interaction.followup.send(
        await testo_per(interaction, "tickets_ticket_creato", mention=channel.mention), ephemeral=True
    )
    return channel


def _category_options(categorie, with_emoji: bool = True) -> list[discord.SelectOption]:
    """
    Le opzioni del menu delle categorie, sempre dentro i limiti di
    Discord (LIM-6) anche con dati salvati prima dei controlli di
    /admin-ticket categoria aggiungi: al massimo 25, etichetta tagliata a 100,
    emoji solo se sembra valida, voci senza nome saltate. Il valore è
    l'id della riga (corto e unico), non l'etichetta.
    """
    opzioni: list[discord.SelectOption] = []
    for categoria in categorie:
        if not categoria.label.strip():
            continue
        emoji = None
        if with_emoji and categoria.emoji and looks_like_emoji(categoria.emoji):
            emoji = categoria.emoji
        opzioni.append(
            discord.SelectOption(
                label=truncate_label(categoria.label), value=str(categoria.id), emoji=emoji
            )
        )
    return opzioni[:MAX_TICKET_CATEGORIES]


class TicketCategorySelectView(BaseView):
    """
    SPEC.md §13.2: select menu tra più categorie di ticket, mostrato
    invece del bottone unico quando il server ne ha configurato
    almeno una. NON persistente: vive solo per la durata
    dell'interazione ephemeral che la mostra, non deve sopravvivere
    a un riavvio del bot (a differenza di TicketPanelView, che è il
    pannello pubblico sempre visibile).
    """

    def __init__(self, guild: discord.Guild, categorie, with_emoji: bool = True) -> None:
        super().__init__(timeout=180)
        self._guild = guild
        select = discord.ui.Select(
            placeholder="Scegli una categoria...",
            options=_category_options(categorie, with_emoji),
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        select = self.children[0]
        id_scelto = select.values[0]
        categorie = await ticket_repo.list_categories(self._guild.id)
        scelta = next((c for c in categorie if str(c.id) == id_scelto), None)
        if scelta is None:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_questa_categoria_non_piu_disponibile"), ephemeral=True
            )
            return

        category_channel = self._guild.get_channel(scelta.category_id)
        if not isinstance(category_channel, discord.CategoryChannel):
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_la_categoria_discord_collegata_non"),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        await _open_ticket_channel(interaction, self._guild, category_channel, scelta.label)


class TicketPanelView(BaseView):
    """
    View PERSISTENTE: timeout=None e un custom_id esplicito sul
    bottone sono entrambi obbligatori perché bot.add_view() la
    accetti (discord.py la rifiuta altrimenti con un ValueError
    esplicito — verificato prima di scrivere questo file, non
    assunto). Senza persistenza, il bottone smetterebbe di
    funzionare ad ogni riavvio del bot per tutti i pannelli già
    pubblicati nei server.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Apri Ticket",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id=OPEN_TICKET_CUSTOM_ID,
    )
    async def open_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_TICKETS):
            await interaction.response.send_message(
                await testo_per(interaction, "opzioni_il_sistema_di_ticket_non"),
                ephemeral=True,
            )
            return

        # SPEC.md §13.2: se il server ha configurato almeno una
        # categoria, si mostra il select menu invece del bottone
        # unico storico — retrocompatibile con chi non ne ha ancora
        # configurata nessuna.
        categorie = await ticket_repo.list_categories(guild.id)
        if _category_options(categorie):
            testo = "Scegli la categoria del tuo ticket:"
            try:
                await interaction.response.send_message(
                    testo, view=TicketCategorySelectView(guild, categorie), ephemeral=True
                )
            except discord.HTTPException:
                # Discord ha rifiutato il menu: quasi sempre un'emoji
                # personalizzata cancellata o di un altro server. Lo
                # stesso menu senza emoji, così i ticket si aprono.
                logger.warning(
                    "Menu delle categorie ticket rifiutato nel server %s: riprovo senza emoji.",
                    guild.id,
                )
                await interaction.response.send_message(
                    testo,
                    view=TicketCategorySelectView(guild, categorie, with_emoji=False),
                    ephemeral=True,
                )
            return

        category_id = await db.get_guild_setting(guild.id, SETTING_CATEGORY)
        if category_id is None:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_il_sistema_di_ticket_non"),
                ephemeral=True,
            )
            return

        category = guild.get_channel(category_id)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_la_categoria_configurata_per_ticket"),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        await _open_ticket_channel(interaction, guild, category, category_label=None)


# ====================================================================
# NF-13 — pannelli con modulo, bottoni persistenti
# ====================================================================
class ModuloTicket(BaseModal):
    """Finestra con le domande del pannello (al massimo 5, limite di Discord)."""

    def __init__(
        self, panel: PannelloTicket, domande: list[DomandaModulo], *, comando: dict | None = None
    ) -> None:
        super().__init__(title=form.titolo_modulo(panel.name), timeout=600)
        self._panel = panel
        self._domande = domande
        # TKT-007/009: da /ticket apri arrivano anche motivo e link del messaggio.
        self._comando = comando or {}
        for domanda in domande[: form.MAX_DOMANDE]:
            self.add_item(
                discord.ui.TextInput(
                    label=domanda.label[: form.MAX_ETICHETTA_DOMANDA],
                    placeholder=domanda.placeholder,
                    required=domanda.required,
                    style=discord.TextStyle.paragraph if domanda.long_answer else discord.TextStyle.short,
                    max_length=form.lunghezza_massima_risposta(domanda.long_answer),
                    custom_id=f"d{domanda.position}",
                )
            )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        risposte = [item.value for item in self.children]
        mancanti = form.risposte_mancanti(self._domande, risposte)
        if mancanti:
            await interaction.response.send_message(
                "Rispondi a tutte le domande obbligatorie: " + ", ".join(mancanti), ephemeral=True
            )
            return
        # Il pannello può essere cambiato mentre l'utente scriveva: si rilegge.
        panel = await ticket_form_repo.pannello_per_id(self._panel.id)
        if panel is None:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_questo_pannello_non_esiste_piu"), ephemeral=True
            )
            return
        category = guild.get_channel(panel.category_id)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_la_categoria_discord_del_pannello"),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        campi = form.campi_risposte(self._domande, risposte)
        if self._comando:
            await apri_da_comando(interaction, guild, category, panel, campi=campi, **self._comando)
            return
        await _open_ticket_channel(interaction, guild, category, panel.name, panel=panel, campi=campi)


async def apri_da_pannello(interaction: discord.Interaction, panel_id: int) -> None:
    """Clic sul bottone di un pannello: controlli veloci, poi finestra o apertura diretta."""
    guild = interaction.guild
    if guild is None:
        return
    if not await db.is_module_active_for_guild(guild.id, MODULE_TICKETS):
        await interaction.response.send_message(
            await testo_per(interaction, "opzioni_il_sistema_di_ticket_non"), ephemeral=True
        )
        return
    panel = await ticket_form_repo.pannello_per_id(panel_id)
    if panel is None or panel.guild_id != guild.id:
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_questo_pannello_non_piu_disponibile"), ephemeral=True
        )
        return
    limite = await _limite_per_utente(guild.id)
    if await ticket_repo.count_open_tickets_for_user(guild.id, interaction.user.id) >= limite:
        await interaction.response.send_message(_messaggio_limite(limite), ephemeral=True)
        return
    # Prima della finestra: chi non può aprire non deve riempire il modulo per niente.
    esito = await esito_apertura(guild, interaction.user, panel.id)
    if not esito.permesso:
        await interaction.response.send_message(esito.messaggio[:2000], ephemeral=True)
        return
    category = guild.get_channel(panel.category_id)
    if not isinstance(category, discord.CategoryChannel):
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_la_categoria_discord_del_pannello"),
            ephemeral=True,
        )
        return
    motivi = await ticket_form_repo.elenca_motivi(panel.id)
    if motivi:
        # TKT-006: prima si sceglie il motivo (o «Altro»), poi la finestra del modulo o il ticket.
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_scegli_il_motivo"), view=VistaMotivi(panel, motivi, (
                await testo_per(interaction, "tickets_motivo_segnaposto"), await testo_per(interaction, "tickets_motivo_altro"),
            )),
            ephemeral=True,
        )
        return
    domande = await ticket_form_repo.elenca_domande(panel.id)
    if domande:
        # La finestra deve essere la PRIMA risposta all'interazione.
        await interaction.response.send_modal(ModuloTicket(panel, domande))
        return
    await interaction.response.defer(ephemeral=True)
    await _open_ticket_channel(interaction, guild, category, panel.name, panel=panel)


class ModuloAltroMotivo(BaseModal):
    """TKT-006: «Altro» su un pannello senza modulo: una riga per dire di cosa si ha bisogno."""

    def __init__(self, panel: PannelloTicket, titolo: str, campo: str) -> None:
        super().__init__(title=titolo[:45], timeout=600)
        self._panel = panel
        self.motivo = discord.ui.TextInput(
            label=campo[:45], style=discord.TextStyle.paragraph, required=True,
            max_length=form.MAX_TESTO_MOTIVO, custom_id="motivo",
        )
        self.add_item(self.motivo)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        category = guild.get_channel(self._panel.category_id) if guild else None
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_la_categoria_discord_del_pannello"), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        await _open_ticket_channel(
            interaction, guild, category, self._panel.name, panel=self._panel, motivo=self.motivo.value.strip()
        )


class VistaMotivi(BaseView):
    """TKT-006: menu dei motivi pronti del pannello (al massimo 24 + «Altro»). Vive solo per questa risposta."""

    def __init__(self, panel: PannelloTicket, motivi, testi: tuple[str, str] = ("…", "Altro")) -> None:
        super().__init__(timeout=180)
        self._panel = panel
        self._motivi = {str(m.id): m for m in motivi}
        select = discord.ui.Select(
            placeholder=testi[0][:150],
            options=[
                discord.SelectOption(
                    label=etichetta, value=valore,
                    emoji=emoji if emoji and looks_like_emoji(emoji) else None,
                )
                for valore, etichetta, emoji in form.opzioni_motivi(motivi, testi[1])
            ],
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        scelto = self.children[0].values[0]
        guild = interaction.guild
        panel = await ticket_form_repo.pannello_per_id(self._panel.id)
        if guild is None or panel is None:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_questo_pannello_non_esiste_piu"), ephemeral=True
            )
            return
        category = guild.get_channel(panel.category_id)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_la_categoria_discord_del_pannello"), ephemeral=True
            )
            return
        domande = await ticket_form_repo.elenca_domande(panel.id)
        if scelto == form.VALORE_ALTRO:
            if domande:
                await interaction.response.send_modal(ModuloTicket(panel, domande))
            else:
                await interaction.response.send_modal(ModuloAltroMotivo(
                    panel, await testo_per(interaction, "tickets_altro_motivo_titolo"),
                    await testo_per(interaction, "tickets_altro_motivo_campo"),
                ))
            return
        motivo = self._motivi.get(scelto)
        if motivo is None:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_questa_categoria_non_piu_disponibile"), ephemeral=True
            )
            return
        testo = motivo.testo or motivo.etichetta
        if domande:
            dati = {"motivo": testo, "link": None, "utente": None, "aggiungi_autore": False}
            await interaction.response.send_modal(ModuloTicket(panel, domande, comando=dati))
            return
        await interaction.response.defer(ephemeral=True)
        await _open_ticket_channel(interaction, guild, category, panel.name, panel=panel, motivo=testo)


async def _puo_leggere(canale, membro) -> bool:
    """
    Chi apre e chi riceve il ticket devono poter leggere il messaggio citato, se no il ticket
    lo mostra a chi non lo vedeva. Un thread privato non ha permessi propri (discord.py li
    prende dal canale padre): conta essere membri del thread, o gestire i thread.
    """
    permessi = canale.permissions_for(membro)
    if not (permessi.view_channel and permessi.read_message_history):
        return False
    if getattr(canale, "type", None) != discord.ChannelType.private_thread or permessi.manage_threads:
        return True
    try:
        await canale.fetch_member(membro.id)
    except discord.HTTPException:
        return False
    return True


async def _messaggio_citato(interaction: discord.Interaction, link: str | None, titolare=None):
    """TKT-009: il messaggio del link, se è di questo server e chi apre (e chi riceve il ticket) può leggerlo."""
    if not link:
        return None, None
    parti = opz_logic.leggi_link_messaggio(link)
    if parti is None or parti[0] != interaction.guild.id:
        return None, "Il link non è di un messaggio di questo server (usa «Copia link del messaggio»)."
    canale = interaction.guild.get_channel_or_thread(parti[1])
    lettori = [interaction.user] + ([titolare] if titolare is not None and titolare.id != interaction.user.id else [])
    if canale is None or not all([await _puo_leggere(canale, m) for m in lettori]):
        return None, "Non trovo quel canale, oppure non puoi leggerlo (tu o chi riceve il ticket)."
    try:
        return await canale.fetch_message(parti[2]), None
    except discord.HTTPException:
        return None, "Non trovo quel messaggio: forse è stato cancellato."


async def apri_da_comando(
    interaction: discord.Interaction,
    guild: discord.Guild,
    category: discord.CategoryChannel,
    panel: PannelloTicket | None,
    *,
    motivo: str | None = None,
    link: str | None = None,
    utente: discord.Member | None = None,
    aggiungi_autore: bool = False,
    campi: list[tuple[str, str]] | None = None,
) -> None:
    """TKT-007/008/009: apertura da /ticket apri (interazione già deferred)."""
    citato, errore = await _messaggio_citato(interaction, link, utente)
    if errore:
        await interaction.followup.send(errore, ephemeral=True)
        return
    channel = await _open_ticket_channel(
        interaction, guild, category, panel.name if panel else None,
        panel=panel, campi=campi, utente=utente, motivo=motivo, citato=citato,
    )
    autore = getattr(citato, "author", None)
    titolare = utente or interaction.user
    if channel is None or not aggiungi_autore or not isinstance(autore, discord.Member) or autore.id == titolare.id:
        return
    try:
        if isinstance(channel, discord.Thread):
            await channel.add_user(autore)
        else:
            await channel.set_permissions(autore, view_channel=True, send_messages=True, read_message_history=True)
    except discord.HTTPException:
        logger.warning("Autore del messaggio citato non aggiunto al ticket %s.", channel.id)


class BottonePannello(
    discord.ui.DynamicItem[discord.ui.Button], template=r"tkt:pan:(?P<id>[0-9]+)"
):
    """Bottone di un pannello: l'id del pannello sta nel custom_id, nessuna view da registrare per messaggio."""

    def __init__(self, panel_id: int, etichetta: str = "Apri ticket", emoji: str | None = None) -> None:
        super().__init__(
            discord.ui.Button(
                label=form.etichetta_bottone(etichetta),
                emoji=emoji if emoji and looks_like_emoji(emoji) else None,
                style=discord.ButtonStyle.primary,
                custom_id=form.custom_id_pannello(panel_id),
            )
        )
        self.panel_id = panel_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        # SEC-10: un bottone dinamico non ha una BaseView sopra: la blacklist si controlla qui.
        return not await _utente_o_server_in_blacklist(interaction)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.exception("Errore in un bottone dei ticket: %s", error)
        await _rispondi_con_errore(interaction)

    async def callback(self, interaction: discord.Interaction) -> None:
        await apri_da_pannello(interaction, self.panel_id)


class BottoneVoto(
    discord.ui.DynamicItem[discord.ui.Button], template=r"tkt:voto:(?P<t>[0-9]+):(?P<s>[1-5])"
):
    """Stella di valutazione nel DM di chiusura. Vale una volta sola, solo per chi ha aperto il ticket."""

    def __init__(self, ticket_id: int, stelle: int) -> None:
        super().__init__(
            discord.ui.Button(
                label=str(stelle),
                emoji="⭐",
                style=discord.ButtonStyle.secondary,
                custom_id=form.custom_id_voto(ticket_id, stelle),
            )
        )
        self.ticket_id = ticket_id
        self.stelle = stelle

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["t"]), int(match["s"]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        # SEC-10: un bottone dinamico non ha una BaseView sopra: la blacklist si controlla qui.
        return not await _utente_o_server_in_blacklist(interaction)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.exception("Errore in un bottone dei ticket: %s", error)
        await _rispondi_con_errore(interaction)

    async def callback(self, interaction: discord.Interaction) -> None:
        registrato = await ticket_repo.set_rating(self.ticket_id, interaction.user.id, self.stelle)
        if not registrato:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_hai_gia_votato_questo_ticket"), ephemeral=True
            )
            return
        await interaction.response.edit_message(
            content=f"Grazie per il voto: {form.testo_stelle(self.stelle)}", view=None
        )


def vista_pannelli(pannelli: list[PannelloTicket]) -> discord.ui.View:
    """Un messaggio con i bottoni di più pannelli (al massimo 25: 5 righe da 5)."""
    form.righe_di_bottoni(len(pannelli))  # solleva oltre il limite
    vista = BaseView(timeout=None)
    for p in pannelli:
        vista.add_item(BottonePannello(p.id, p.button_label, p.button_emoji))
    return vista


async def _etichette_gestisci(interaction) -> dict[str, str]:
    return {
        "segnaposto": await testo_per(interaction, "tickets_gestisci_segnaposto", pubblica=True),
        "solo_admin": await testo_per(interaction, "tickets_gestisci_solo_admin", pubblica=True),
        "tutti": await testo_per(interaction, "tickets_gestisci_tutto_lo_staff", pubblica=True),
        "etichette": await testo_per(interaction, "tickets_gestisci_etichette", pubblica=True),
        "sposta": await testo_per(interaction, "tickets_gestisci_sposta", pubblica=True),
    }


async def sposta_ticket(channel, guild: discord.Guild, ticket, nuovo) -> str | None:
    """
    TKT-067: porta il ticket in un altro pannello. Cambia categoria, permessi dello staff e pannello nel database.
    Restituisce None se è andato bene, altrimenti il codice dell'errore («categoria_mancante», «categoria_piena»,
    «permessi» se Discord non lascia spostare il canale); in quel caso non cambia niente. Dopo lo spostamento il
    pannello si salva subito: un ruolo che non si riesce a cambiare finisce nel log e non ferma gli altri.
    """
    categoria = guild.get_channel(nuovo.category_id)
    if not isinstance(categoria, discord.CategoryChannel):
        return "categoria_mancante"
    cambia_categoria = getattr(channel, "category_id", None) != categoria.id
    if cambia_categoria and len(categoria.channels) >= 50:
        return "categoria_piena"
    vecchi = set(await _ruoli_staff(guild.id, ticket.panel_id))
    ruoli_admin = await _ruoli_admin(guild.id)
    nuovi = ruoli_con_accesso(await _ruoli_staff(guild.id, nuovo.id), ruoli_admin, ticket.solo_admin)
    if cambia_categoria:
        try:
            await channel.edit(category=categoria, reason="Ticket spostato in un altro pannello")
        except discord.HTTPException:
            logger.warning("Ticket %s non spostato nella categoria %s.", channel.id, categoria.id)
            return "permessi"
    await ticket_repo.set_panel(channel.id, nuovo.id)
    vista = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    for role_id, overwrite in [(r, None) for r in vecchi - set(nuovi)] + [(r, vista) for r in nuovi]:
        ruolo = guild.get_role(role_id)
        if ruolo is None or role_id == guild.id:
            continue
        try:
            await channel.set_permissions(ruolo, overwrite=overwrite, reason="Ticket spostato in un altro pannello")
        except discord.HTTPException:
            logger.warning("Permessi del ruolo %s non cambiati nel ticket spostato %s.", role_id, channel.id)
    return None


async def _esegui_sposta(interaction: discord.Interaction, ticket, nuovo) -> None:
    errore = await sposta_ticket(interaction.channel, interaction.guild, ticket, nuovo)
    if errore:
        await interaction.followup.send(
            await testo_per(interaction, f"tickets_sposta_{errore}"),
            ephemeral=True,
        )
        return
    await interaction.followup.send(await testo_per(interaction, "tickets_sposta_fatto", name=nuovo.name), ephemeral=True)
    try:
        await interaction.channel.send(
            await testo_per(interaction, "tickets_sposta_avviso", pubblica=True, chi=interaction.user.mention, name=nuovo.name),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException:
        logger.warning("Avviso di spostamento non inviato nel ticket %s.", interaction.channel.id)


class ModuloSposta(BaseModal):
    """TKT-067: con più di 24 pannelli il nome si scrive."""

    def __init__(self, ticket, titolo: str, campo: str) -> None:
        super().__init__(title=titolo[:45], timeout=300)
        self._ticket = ticket
        self.nome = discord.ui.TextInput(label=campo[:45], max_length=form.MAX_NOME_PANNELLO, custom_id="nome")
        self.add_item(self.nome)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        panel = await ticket_form_repo.pannello_per_nome(interaction.guild.id, self.nome.value.strip())
        if panel is None:
            await interaction.response.send_message(
                await testo_per(interaction, "opzioni_nessun_pannello_chiamato", v1=self.nome.value.strip()[:100]), ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        await interaction.response.defer(ephemeral=True)
        await _esegui_sposta(interaction, self._ticket, panel)


class VistaSposta(BaseView):
    """TKT-067: menu dei pannelli (fino a 24 + «Altri…»)."""

    def __init__(self, ticket, pannelli, altri: str = "Altri…") -> None:
        super().__init__(timeout=180)
        self._ticket = ticket
        select = discord.ui.Select(
            placeholder="…",
            options=[
                discord.SelectOption(label=etichetta, value=valore)
                for valore, etichetta in gestione.voci_sposta(pannelli, ticket.panel_id, altri)
            ],
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        scelto = self.children[0].values[0]
        if scelto == gestione.VALORE_ALTRI:
            await interaction.response.send_modal(ModuloSposta(
                self._ticket, await testo_per(interaction, "tickets_sposta_altri_titolo"),
                await testo_per(interaction, "tickets_sposta_altri_campo"),
            ))
            return
        panel = await ticket_form_repo.pannello_per_id(int(scelto))
        if panel is None or panel.guild_id != interaction.guild.id:
            await interaction.response.send_message(await testo_per(interaction, "tickets_questo_pannello_non_esiste_piu"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await _esegui_sposta(interaction, self._ticket, panel)


class VistaEtichette(BaseView):
    """TKT-068: scelta multipla delle etichette del ticket. Colora il benvenuto, mai il nome del canale (LIM-3)."""

    def __init__(self, ticket, messaggio, etichette, nome_campo: str, assegnate=()) -> None:
        super().__init__(timeout=180)
        self._ticket, self._messaggio, self._nome_campo = ticket, messaggio, nome_campo
        select = discord.ui.Select(
            placeholder="…", min_values=0, max_values=max(1, len(etichette)),
            options=[
                discord.SelectOption(
                    label=e.nome[:100], value=str(e.id), default=e.id in assegnate,
                    emoji=e.emoji if e.emoji and looks_like_emoji(e.emoji) else None,
                )
                for e in etichette[:gestione.MAX_ETICHETTE]
            ],
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        ids = [int(v) for v in self.children[0].values]
        assegnate = await ticket_gestione_repo.assegna_etichette(self._ticket.id, interaction.guild.id, ids)
        embed = discord.Embed.from_dict(self._messaggio.embeds[0].to_dict())
        gestione.applica_etichette(embed, [(e.nome, e.colore) for e in assegnate], self._nome_campo)
        await self._messaggio.edit(embeds=[embed])
        await interaction.response.edit_message(content=await testo_per(interaction, "tickets_etichette_salvate"), view=None)


async def suggerisci_articolo(channel, guild_id: int, motivo: str | None, campi) -> None:
    """TKT-079: se la richiesta somiglia a un articolo approvato, lo propone nel ticket (parole chiave, senza AI)."""
    testo = "\n".join([motivo or "", *(v for _, v in (campi or []))]).strip()
    if not testo:
        return
    articoli = await ticket_gestione_repo.tutti_gli_approvati(guild_id)
    scelto = gestione.scegli_articolo(articoli, testo) if articoli else None
    if scelto is None:
        return
    try:
        await channel.send(
            embed=discord.Embed(title=truncate_label(scelto.titolo, 256), description=scelto.testo[:4000], color=discord.Color.green()),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await ticket_gestione_repo.conta_uso(scelto.id)
    except discord.HTTPException:
        logger.warning("Articolo suggerito non inviato nel ticket %s.", channel.id)


async def imposta_solo_admin(channel, guild: discord.Guild, ticket, attivo: bool) -> None:
    """
    TKT-046: toglie (o rimette) nel canale i ruoli degli addetti e, all'attivazione, i permessi personali
    degli addetti. Chi ha «Gestisci server», i ruoli admin e l'autore restano. Una modifica per ruolo o persona.
    """
    ruoli_staff = await _ruoli_staff(guild.id, ticket.panel_id)
    ruoli_admin = await _ruoli_admin(guild.id)
    for role_id in ruoli_staff:
        if role_id in ruoli_admin or role_id == guild.id:
            continue
        ruolo = guild.get_role(role_id)
        if ruolo is None:
            continue
        if attivo:
            await channel.set_permissions(ruolo, overwrite=None, reason="Ticket solo admin")
        else:
            await channel.set_permissions(
                ruolo, overwrite=discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                reason="Ticket di nuovo a tutto lo staff",
            )
    if attivo:
        # Reperibili e chi aveva preso il ticket hanno un permesso personale: agli addetti va tolto
        # (l'autore resta sempre, anche se è un addetto).
        for bersaglio in list(dict(channel.overwrites)):
            if (
                not isinstance(bersaglio, discord.Member) or bersaglio.id == ticket.user_id
                or not await _membro_staff(bersaglio, guild.id, ticket.panel_id)
                or await _membro_admin(bersaglio, guild.id, ticket.panel_id)
            ):
                continue
            await channel.set_permissions(bersaglio, overwrite=None, reason="Ticket solo admin")
    await ticket_repo.set_solo_admin(channel.id, attivo)


class MenuGestisci(
    discord.ui.DynamicItem[discord.ui.Select], template=r"tkt:gst:(?P<id>[0-9]+)"
):
    """Menu «Gestisci» dello staff sul messaggio di benvenuto. Per ora: solo admin. Le azioni nuove vanno qui, non in /ticket."""

    def __init__(self, ticket_id: int, etichette: dict[str, str] | None = None) -> None:
        e = etichette or {
            "segnaposto": "Gestisci", "solo_admin": "Solo admin", "tutti": "Tutto lo staff",
            "etichette": "Etichette", "sposta": "Sposta in un altro pannello",
        }
        super().__init__(
            discord.ui.Select(
                custom_id=f"tkt:gst:{ticket_id}",
                placeholder=e["segnaposto"][:150],
                options=[
                    discord.SelectOption(label=e["solo_admin"][:100], value="solo_admin"),
                    discord.SelectOption(label=e["tutti"][:100], value="tutti"),
                    discord.SelectOption(label=e["etichette"][:100], value="etichette"),
                    discord.SelectOption(label=e["sposta"][:100], value="sposta"),
                ],
            )
        )
        self.ticket_id = ticket_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        return not await _utente_o_server_in_blacklist(interaction)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.exception("Errore nel menu Gestisci dei ticket: %s", error)
        await _rispondi_con_errore(interaction)

    async def _etichette(self, interaction: discord.Interaction, ticket) -> None:
        """TKT-068: le etichette le assegna ogni membro dello staff dei ticket."""
        if not await _is_ticket_staff(interaction, ticket):
            await interaction.response.send_message(await testo_per(interaction, "tickets_solo_lo_staff_permesso_manage_2"), ephemeral=True)
            return
        etichette = await ticket_gestione_repo.elenca_etichette(interaction.guild.id)
        if not etichette or interaction.message is None or not interaction.message.embeds:
            await interaction.response.send_message(await testo_per(interaction, "tickets_etichette_nessuna_definita"), ephemeral=True)
            return
        gia = [e.id for e in await ticket_gestione_repo.etichette_del_ticket(ticket.id)]
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_etichette_scegli"),
            view=VistaEtichette(ticket, interaction.message, etichette, await testo_per(interaction, "tickets_etichette_campo", pubblica=True), gia),
            ephemeral=True,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id) if interaction.channel else None
        if ticket is None or ticket.id != self.ticket_id or ticket.status != "open":
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_questo_comando_funziona_solo_dentro"), ephemeral=True
            )
            return
        scelta = self.item.values[0]
        if scelta == "etichette":
            await self._etichette(interaction, ticket)
            return
        if isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(await testo_per(interaction, "tickets_thread_non_disponibile"), ephemeral=True)
            return
        if not await _is_ticket_admin(interaction, ticket):
            await interaction.response.send_message(await testo_per(interaction, "tickets_solo_admin_dei_ticket"), ephemeral=True)
            return
        if scelta == "sposta":
            pannelli = await ticket_form_repo.elenca_pannelli(interaction.guild.id)
            if not gestione.voci_sposta(pannelli, ticket.panel_id):
                await interaction.response.send_message(await testo_per(interaction, "tickets_sposta_nessun_altro_pannello"), ephemeral=True)
                return
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_sposta_scegli"), view=VistaSposta(ticket, pannelli, await testo_per(interaction, "tickets_sposta_altri")),
                ephemeral=True,
            )
            return
        attivo = scelta == "solo_admin"
        if attivo and not await _ruoli_admin(interaction.guild.id):
            await interaction.response.send_message(await testo_per(interaction, "tickets_solo_admin_nessun_ruolo"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await imposta_solo_admin(interaction.channel, interaction.guild, ticket, attivo)
        await interaction.followup.send(
            await testo_per(interaction, "tickets_solo_admin_attivato" if attivo else "tickets_solo_admin_disattivato"),
            ephemeral=True,
        )


class BottoneEntra(
    discord.ui.DynamicItem[discord.ui.Button], template=r"tkt:ent:(?P<id>[0-9]+)"
):
    """TKT-032: lo staff che non vede i thread privati entra in un ticket a thread da questo bottone."""

    def __init__(self, thread_id: int, etichetta: str = "Entra") -> None:
        super().__init__(
            discord.ui.Button(label=etichetta[:45], style=discord.ButtonStyle.primary, custom_id=f"tkt:ent:{thread_id}")
        )
        self.thread_id = thread_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        return not await _utente_o_server_in_blacklist(interaction)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.exception("Errore nel bottone Entra dei ticket: %s", error)
        await _rispondi_con_errore(interaction)

    async def callback(self, interaction: discord.Interaction) -> None:
        ticket = await ticket_repo.get_ticket_by_channel(self.thread_id)
        guild = interaction.guild
        if ticket is None or guild is None:
            await interaction.response.send_message(await testo_per(interaction, "tickets_thread_non_trovato"), ephemeral=True)
            return
        if not await _is_ticket_staff(interaction, ticket):
            await interaction.response.send_message(await testo_per(interaction, "tickets_solo_lo_staff_permesso_manage_2"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            thread = guild.get_thread(self.thread_id) or await guild.fetch_channel(self.thread_id)
            await thread.add_user(interaction.user)
        except discord.NotFound:
            await interaction.followup.send(await testo_per(interaction, "tickets_thread_non_trovato"), ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "tickets_thread_entra_fallito"), ephemeral=True)
            return
        await interaction.followup.send(await testo_per(interaction, "tickets_thread_entrato", thread=thread.mention), ephemeral=True)


class BottoneChiuso(
    discord.ui.DynamicItem[discord.ui.Button], template=r"tkt:cls:(?P<t>[0-9]+):(?P<a>[rets])"
):
    """TKT-051: Riapri, Elimina e Transcript di un ticket chiuso il cui canale è rimasto. Solo staff."""

    _ETICHETTE = {
        "r": ("Riapri", discord.ButtonStyle.success),
        "e": ("Elimina", discord.ButtonStyle.danger),
        "t": ("Transcript", discord.ButtonStyle.secondary),
    }

    def __init__(self, ticket_id: int, azione: str) -> None:
        etichetta, stile = self._ETICHETTE.get(azione, ("Riapri", discord.ButtonStyle.success))
        super().__init__(
            discord.ui.Button(label=etichetta, style=stile, custom_id=f"tkt:cls:{ticket_id}:{azione}")
        )
        self.ticket_id = ticket_id
        self.azione = azione

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["t"]), match["a"])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        return not await _utente_o_server_in_blacklist(interaction)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.exception("Errore in un bottone del ticket chiuso: %s", error)
        await _rispondi_con_errore(interaction)

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("TicketsCog")
        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id)
        if cog is None or ticket is None or ticket.id != self.ticket_id:
            await interaction.response.send_message(await testo_per(interaction, "tickets_questo_ticket_non_piu"), ephemeral=True)
            return
        if not await _is_ticket_staff(interaction, ticket):
            await interaction.response.send_message(await testo_per(interaction, "tickets_solo_lo_staff_dei_ticket"), ephemeral=True)
            return
        if self.azione == "e" and ticket.status != "closed":
            # Bottone rimasto dopo /ticket riapri: un ticket aperto si chiude prima.
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_il_ticket_stato_riaperto_chiudilo"), ephemeral=True
            )
            return
        await cog.azione_ticket_chiuso(interaction, ticket, self.azione)


def vista_ticket_chiuso(ticket_id: int) -> discord.ui.View:
    vista = BaseView(timeout=None)
    for azione in ("r", "t", "e"):
        vista.add_item(BottoneChiuso(ticket_id, azione))
    return vista


class BottoneRichiestaChiusura(
    discord.ui.DynamicItem[discord.ui.Button], template=r"tkt:chc:(?P<t>[0-9]+):(?P<s>[ar])"
):
    """TKT-055: Accetta (chiude) o Rifiuta (resta aperto). Solo chi ha aperto il ticket."""

    def __init__(self, ticket_id: int, scelta: str) -> None:
        accetta = scelta == "a"
        super().__init__(
            discord.ui.Button(
                label="Sì, chiudi" if accetta else "No, ho ancora bisogno",
                style=discord.ButtonStyle.success if accetta else discord.ButtonStyle.secondary,
                custom_id=f"tkt:chc:{ticket_id}:{scelta}",
            )
        )
        self.ticket_id = ticket_id
        self.scelta = scelta

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["t"]), match["s"])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
        # SEC-10: un bottone dinamico non ha una BaseView sopra: la blacklist si controlla qui.
        return not await _utente_o_server_in_blacklist(interaction)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.exception("Errore in un bottone dei ticket: %s", error)
        await _rispondi_con_errore(interaction)

    async def callback(self, interaction: discord.Interaction) -> None:
        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id)
        if ticket is None or ticket.id != self.ticket_id or ticket.status != "open" or ticket.chiusura_richiesta_at is None:
            await interaction.response.send_message(await testo_per(interaction, "tickets_questa_richiesta_non_vale_piu"), ephemeral=True)
            return
        if interaction.user.id != ticket.user_id:
            await interaction.response.send_message(await testo_per(interaction, "tickets_risponde_solo_chi_ha_aperto"), ephemeral=True)
            return
        if self.scelta == "r":
            await ticket_repo.annulla_richiesta_chiusura(interaction.channel.id)
            await interaction.response.edit_message(
                content=await testo_per(interaction, "tickets_utente_ha_ancora_bisogno_di", pubblica=True), view=None
            )
            return
        cog = interaction.client.get_cog("TicketsCog")
        if cog is None:
            await interaction.response.send_message(await testo_per(interaction, "tickets_ticket_non_sono_disponibili_ora"), ephemeral=True)
            return
        await cog.esegui_close(interaction, ticket, "Chiusura accettata dall'utente")


class ConfermaChiusura(BaseView):
    """TKT-054: conferma prima di chiudere (solo chi ha lanciato /ticket close, un minuto)."""

    def __init__(self, cog, user_id: int, motivo: str | None) -> None:
        super().__init__(timeout=60)
        self._cog = cog
        self._user_id = user_id
        self._motivo = motivo

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await super().interaction_check(interaction) and interaction.user.id == self._user_id

    @discord.ui.button(label="Chiudi il ticket", style=discord.ButtonStyle.danger)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id)
        if ticket is None or ticket.status != "open":
            await interaction.response.edit_message(content=await testo_per(interaction, "tickets_questo_ticket_gia_stato_chiuso", pubblica=True), view=None)
            return
        self.stop()
        await self._cog.esegui_close(interaction, ticket, self._motivo)


def _puo_scavalcare(member) -> bool:
    """TKT-050: con la presa esclusiva solo chi ha Manage Server prende o passa il ticket di un altro."""
    permessi = getattr(member, "guild_permissions", None)
    return bool(permessi and permessi.manage_guild)


def link_inizio(channel) -> str:
    """TKT-040: un link a un id pari a quello del canale porta Discord al primo messaggio."""
    return f"https://discord.com/channels/{channel.guild.id}/{channel.id}/{channel.id}"


def vista_inizio(channel, vista: discord.ui.View | None = None) -> discord.ui.View:
    """TKT-040: aggiunge il bottone «Torna all'inizio» (link, nessun clic da gestire)."""
    vista = vista or BaseView(timeout=None)
    vista.add_item(discord.ui.Button(label="Torna all'inizio", style=discord.ButtonStyle.link, url=link_inizio(channel)))
    return vista


def vista_voto(ticket_id: int) -> discord.ui.View:
    vista = BaseView(timeout=None)
    for stelle in range(form.STELLE_MIN, form.STELLE_MAX + 1):
        vista.add_item(BottoneVoto(ticket_id, stelle))
    return vista


class TicketsCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Canali di cui si sta ancora leggendo la history per il
        # transcript: lo scheduler non li elimina finché non ha finito.
        self._transcript_in_corso: set[int] = set()
        # canale -> ultimo istante (monotonic) in cui l'attività è finita nel database
        self._attivita_scritta: dict[int, float] = {}
        # (canale, scritto dall'utente?) -> istante dell'ultima scrittura in database
        self._chi_scrive: dict[tuple[int, bool], float] = {}

    @comando_di_gruppo(
        "admin-ticket",
        nome="setup",
        descrizione="Configura la categoria (e opzionalmente il ruolo di supporto) per i ticket.",
    )
    @app_commands.describe(
        category="La categoria dove verranno creati i canali dei ticket",
        support_role="Ruolo che vedrà automaticamente ogni ticket (facoltativo)",
    )
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        support_role: discord.Role | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"),
                ephemeral=True,
            )
            return

        await db.set_guild_setting(interaction.guild.id, SETTING_CATEGORY, category.id)
        if support_role is not None:
            await db.set_guild_setting(
                interaction.guild.id, SETTING_SUPPORT_ROLE, support_role.id
            )

        messaggio = f"Categoria dei ticket impostata su **{category.name}**."
        if support_role is not None:
            messaggio += f" Ruolo di supporto: {support_role.mention}."
        await interaction.response.send_message(messaggio, ephemeral=True)

    @comando_di_gruppo(
        "admin-ticket",
        nome="limite",
        descrizione="Quanti ticket aperti alla volta può avere ogni utente (predefinito 1).",
    )
    @app_commands.describe(massimo="Da 1 a 5 ticket aperti per utente")
    async def ticket_limite(
        self,
        interaction: discord.Interaction,
        massimo: app_commands.Range[int, 1, LIMITE_PER_UTENTE_MAX],
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return
        await db.set_guild_setting(interaction.guild.id, SETTING_MAX_PER_UTENTE, int(massimo))
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_ogni_utente_potra_avere_al", massimo=massimo),
            ephemeral=True,
        )

    @comando_di_gruppo(
        "admin-ticket",
        nome="panel",
        descrizione="Pubblica il pannello per l'apertura dei ticket in questo canale.",
    )
    async def ticket_panel(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_TICKETS):
            return

        embed = discord.Embed(
            title=await testo_per(interaction, "tickets_supporto", pubblica=True),
            description=await testo_per(interaction, "tickets_premi_il_bottone_qui_sotto", pubblica=True),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, view=TicketPanelView())

    # ================================================================
    # NF-13 — pannelli, modulo, chiusura automatica, voto
    # ================================================================
    @autocomplete_protetto(Livello.ADMIN)
    async def _completa_pannelli(self, interaction: discord.Interaction, corrente: str):
        """Nomi dei pannelli; in un elenco separato da virgole completa l'ultimo nome."""
        if interaction.guild is None:
            return []
        pannelli = await ticket_form_repo.elenca_pannelli(interaction.guild.id)
        prefisso, _, ultimo = corrente.rpartition(",")
        gia = {n.casefold() for n in form.nomi_da_elenco(prefisso)}
        risultati = []
        for p in pannelli:
            if p.name.casefold() in gia or ultimo.strip().casefold() not in p.name.casefold():
                continue
            valore = (prefisso + ", " if prefisso else "") + p.name
            risultati.append(app_commands.Choice(name=p.name[:100], value=valore[:100]))
        return risultati[:25]

    async def _pannello_o_risposta(self, interaction: discord.Interaction, nome: str):
        if interaction.guild is None:
            return None
        panel = await ticket_form_repo.pannello_per_nome(interaction.guild.id, nome.strip())
        if panel is None:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_nessun_pannello_chiamato_vedi_admin", v1=nome.strip()[:100]),
                ephemeral=True,
            )
        return panel

    @comando_di_gruppo(
        "admin-ticket",
        nome="crea",
        descrizione="Crea un pannello di ticket.",
        sottogruppo=SOTTOGRUPPI["admin-ticket pannelli"],
    )
    @app_commands.describe(
        nome="Nome del pannello",
        categoria="Categoria dei canali",
        etichetta="Testo del bottone",
        emoji="Emoji del bottone",
        benvenuto="Benvenuto ({utente} = menzione)",
    )
    async def pannello_crea(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, form.MAX_NOME_PANNELLO],
        categoria: discord.CategoryChannel,
        etichetta: app_commands.Range[str, 1, form.MAX_ETICHETTA_BOTTONE] | None = None,
        emoji: app_commands.Range[str, 1, MAX_EMOJI_LENGTH] | None = None,
        benvenuto: app_commands.Range[str, 1, form.MAX_TESTO_BENVENUTO] | None = None,
    ) -> None:
        if interaction.guild is None:
            return
        try:
            nome_pulito = form.nome_pannello_valido(nome)
        except form.ErroreConfigurazione as errore:
            await interaction.response.send_message(str(errore), ephemeral=True)
            return
        if emoji is not None and not looks_like_emoji(emoji):
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_quella_non_sembra_un_emoji"),
                ephemeral=True,
            )
            return
        try:
            panel = await ticket_form_repo.crea_pannello(
                interaction.guild.id,
                nome_pulito,
                categoria.id,
                form.etichetta_bottone(etichetta or nome_pulito),
                emoji,
                benvenuto,
            )
        except PannelloGiaEsistente:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_esiste_gia_un_pannello_chiamato", nome_pulito=nome_pulito), ephemeral=True
            )
            return
        except TroppiPannelli:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_un_server_puo_avere_al", v1=form.MAX_PANNELLI_PER_SERVER),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_pannello_creato_aggiungi_le_domande", name=panel.name),
            ephemeral=True,
        )

    @comando_di_gruppo(
        "admin-ticket",
        nome="rimuovi",
        descrizione="Elimina un pannello e il suo modulo.",
        sottogruppo=SOTTOGRUPPI["admin-ticket pannelli"],
    )
    @app_commands.describe(nome="Il pannello da eliminare")
    @app_commands.autocomplete(nome=_completa_pannelli)
    async def pannello_rimuovi(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, form.MAX_NOME_PANNELLO]
    ) -> None:
        panel = await self._pannello_o_risposta(interaction, nome)
        if panel is None:
            return
        await _svuota_riserva(interaction.guild, panel.id, "Pannello dei ticket eliminato")
        await ticket_form_repo.rimuovi_pannello(interaction.guild.id, panel.name)
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_pannello_eliminato_con_il_suo", name=panel.name),
            ephemeral=True,
        )

    @comando_di_gruppo(
        "admin-ticket",
        nome="elenco",
        descrizione="Elenca i pannelli di ticket del server.",
        sottogruppo=SOTTOGRUPPI["admin-ticket pannelli"],
    )
    async def pannello_lista(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        pannelli = await ticket_form_repo.elenca_pannelli(interaction.guild.id)
        if not pannelli:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_nessun_pannello_creane_uno_con"), ephemeral=True
            )
            return
        righe = []
        for p in pannelli:
            domande = await ticket_form_repo.elenca_domande(p.id)
            righe.append(
                f"**{p.name[:60]}** · {len(domande)} domande · "
                f"chiusura auto: {str(p.autoclose_minutes) + ' min' if p.autoclose_minutes else 'no'} · "
                f"voto: {'sì' if p.rating_enabled else 'no'}"
            )
        testo = "\n".join(righe)
        await interaction.response.send_message(testo[:1900], ephemeral=True)

    @comando_di_gruppo(
        "admin-ticket",
        nome="pubblica",
        descrizione="Pubblica qui i bottoni di uno o più pannelli.",
        sottogruppo=SOTTOGRUPPI["admin-ticket pannelli"],
    )
    @app_commands.describe(
        pannelli="Nomi separati da virgola",
        titolo="Titolo del messaggio",
        testo="Testo del messaggio",
    )
    @app_commands.autocomplete(pannelli=_completa_pannelli)
    async def pannello_pubblica(
        self,
        interaction: discord.Interaction,
        pannelli: app_commands.Range[str, 1, 500],
        titolo: app_commands.Range[str, 1, 256] = "🎫 Supporto",
        testo: app_commands.Range[str, 1, 2000] = "Premi un bottone per aprire un ticket privato con lo staff.",
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_TICKETS):
            return
        trovati: list[PannelloTicket] = []
        for nome in form.nomi_da_elenco(pannelli):
            panel = await ticket_form_repo.pannello_per_nome(interaction.guild.id, nome)
            if panel is None:
                await interaction.response.send_message(await testo_per(interaction, "opzioni_nessun_pannello_chiamato", v1=nome[:100]), ephemeral=True)
                return
            trovati.append(panel)
        if not trovati:
            await interaction.response.send_message(await testo_per(interaction, "tickets_indica_almeno_un_pannello"), ephemeral=True)
            return
        try:
            vista = vista_pannelli(trovati)
        except form.ErroreConfigurazione as errore:
            await interaction.response.send_message(str(errore), ephemeral=True)
            return
        embed = discord.Embed(title=titolo, description=testo, color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, view=vista)

    @comando_di_gruppo(
        "admin-ticket",
        nome="modulo-aggiungi",
        descrizione="Aggiungi una domanda al modulo (max 5).",
        sottogruppo=SOTTOGRUPPI["admin-ticket pannelli"],
    )
    @app_commands.describe(
        pannello="Il pannello",
        domanda="La domanda (max 45 caratteri)",
        suggerimento="Testo grigio nel campo",
        obbligatoria="Risposta obbligatoria",
        lunga="Risposta su più righe",
    )
    @app_commands.autocomplete(pannello=_completa_pannelli)
    async def modulo_aggiungi(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, form.MAX_NOME_PANNELLO],
        domanda: app_commands.Range[str, 1, form.MAX_ETICHETTA_DOMANDA],
        suggerimento: app_commands.Range[str, 1, form.MAX_SEGNAPOSTO] | None = None,
        obbligatoria: bool = True,
        lunga: bool = False,
    ) -> None:
        panel = await self._pannello_o_risposta(interaction, pannello)
        if panel is None:
            return
        try:
            etichetta, segnaposto = form.domanda_valida(domanda, suggerimento)
        except form.ErroreConfigurazione as errore:
            await interaction.response.send_message(str(errore), ephemeral=True)
            return
        try:
            nuova = await ticket_form_repo.aggiungi_domanda(panel.id, etichetta, segnaposto, obbligatoria, lunga)
        except TroppeDomande:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_il_modulo_ha_gia_domande", v1=form.MAX_DOMANDE),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_domanda_aggiunta_al_pannello", position=nuova.position, name=panel.name), ephemeral=True
        )

    @comando_di_gruppo(
        "admin-ticket",
        nome="modulo-togli",
        descrizione="Togli una domanda dal modulo.",
        sottogruppo=SOTTOGRUPPI["admin-ticket pannelli"],
    )
    @app_commands.describe(pannello="Il pannello", numero="Numero della domanda")
    @app_commands.autocomplete(pannello=_completa_pannelli)
    async def modulo_rimuovi(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, form.MAX_NOME_PANNELLO],
        numero: app_commands.Range[int, 1, form.MAX_DOMANDE],
    ) -> None:
        panel = await self._pannello_o_risposta(interaction, pannello)
        if panel is None:
            return
        if await ticket_form_repo.rimuovi_domanda(panel.id, numero):
            await interaction.response.send_message(await testo_per(interaction, "tickets_domanda_tolta", numero=numero), ephemeral=True)
        else:
            await interaction.response.send_message(await testo_per(interaction, "tickets_non_una_domanda", numero=numero), ephemeral=True)

    @comando_di_gruppo(
        "admin-ticket",
        nome="modulo-mostra",
        descrizione="Mostra le domande del modulo di un pannello.",
        sottogruppo=SOTTOGRUPPI["admin-ticket pannelli"],
    )
    @app_commands.describe(pannello="Il pannello")
    @app_commands.autocomplete(pannello=_completa_pannelli)
    async def modulo_mostra(
        self, interaction: discord.Interaction, pannello: app_commands.Range[str, 1, form.MAX_NOME_PANNELLO]
    ) -> None:
        panel = await self._pannello_o_risposta(interaction, pannello)
        if panel is None:
            return
        domande = await ticket_form_repo.elenca_domande(panel.id)
        if not domande:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_il_pannello_non_ha_domande", name=panel.name), ephemeral=True
            )
            return
        righe = [
            f"{d.position}. {d.label} ({'obbligatoria' if d.required else 'facoltativa'}"
            f"{', lunga' if d.long_answer else ''})"
            for d in domande
        ]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    @comando_di_gruppo(
        "admin-ticket",
        nome="motivo-aggiungi",
        descrizione="Aggiungi un motivo pronto al pannello (max 24).",
        sottogruppo=SOTTOGRUPPI["admin-ticket pannelli"],
    )
    @app_commands.describe(
        pannello="Il pannello",
        etichetta="Nome del motivo nel menu (max 80 caratteri)",
        testo="Testo scritto nel ticket (se vuoto: l'etichetta)",
        emoji="Emoji accanto al nome",
    )
    @app_commands.autocomplete(pannello=_completa_pannelli)
    async def motivo_aggiungi(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, form.MAX_NOME_PANNELLO],
        etichetta: app_commands.Range[str, 1, form.MAX_ETICHETTA_MOTIVO],
        testo: app_commands.Range[str, 1, form.MAX_TESTO_MOTIVO] | None = None,
        emoji: app_commands.Range[str, 1, MAX_EMOJI_LENGTH] | None = None,
    ) -> None:
        panel = await self._pannello_o_risposta(interaction, pannello)
        if panel is None:
            return
        try:
            etichetta, testo = form.motivo_valido(etichetta, testo)
        except form.ErroreConfigurazione as errore:
            await interaction.response.send_message(str(errore), ephemeral=True)
            return
        if emoji is not None and not looks_like_emoji(emoji):
            emoji = None
        try:
            nuovo = await ticket_form_repo.aggiungi_motivo(panel.id, etichetta, emoji, testo)
        except TroppiMotivi:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_troppi_motivi", massimo=form.MAX_MOTIVI), ephemeral=True
            )
            return
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_motivo_aggiunto", etichetta=etichetta, name=panel.name, posizione=nuovo.posizione),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo(
        "admin-ticket",
        nome="motivo-togli",
        descrizione="Togli un motivo pronto dal pannello (senza numero: li elenca).",
        sottogruppo=SOTTOGRUPPI["admin-ticket pannelli"],
    )
    @app_commands.describe(pannello="Il pannello", numero="Numero del motivo (vuoto = elenco)")
    @app_commands.autocomplete(pannello=_completa_pannelli)
    async def motivo_togli(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, form.MAX_NOME_PANNELLO],
        numero: app_commands.Range[int, 1, form.MAX_MOTIVI] | None = None,
    ) -> None:
        panel = await self._pannello_o_risposta(interaction, pannello)
        if panel is None:
            return
        if numero is None:
            motivi = await ticket_form_repo.elenca_motivi(panel.id)
            if not motivi:
                await interaction.response.send_message(
                    await testo_per(interaction, "tickets_pannello_senza_motivi", name=panel.name), ephemeral=True
                )
                return
            righe = [f"{m.posizione}. {m.etichetta}" for m in motivi]
            await interaction.response.send_message(
                "\n".join(righe)[:2000], ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
            )
            return
        if await ticket_form_repo.rimuovi_motivo(panel.id, numero):
            await interaction.response.send_message(await testo_per(interaction, "tickets_motivo_tolto", numero=numero), ephemeral=True)
        else:
            await interaction.response.send_message(await testo_per(interaction, "tickets_non_un_motivo", numero=numero), ephemeral=True)

    @comando_di_gruppo(
        "admin-ticket",
        nome="aggiungi",
        descrizione="Crea un'etichetta colorata per i ticket (max 25).",
        sottogruppo=SOTTOGRUPPI["admin-ticket etichette"],
    )
    @app_commands.describe(
        nome="Nome dell'etichetta (max 32 caratteri)", colore="Colore come #RRGGBB (di base blu)", emoji="Emoji accanto al nome"
    )
    async def etichetta_aggiungi(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, gestione.MAX_NOME_ETICHETTA],
        colore: app_commands.Range[str, 1, 7] | None = None,
        emoji: app_commands.Range[str, 1, MAX_EMOJI_LENGTH] | None = None,
    ) -> None:
        if interaction.guild is None:
            return
        try:
            nome = gestione.etichetta_valida(nome)
            valore = gestione.colore_valido(colore)
        except form.ErroreConfigurazione as errore:
            await interaction.response.send_message(str(errore), ephemeral=True)
            return
        try:
            await ticket_gestione_repo.aggiungi_etichetta(
                interaction.guild.id, nome, valore, emoji if emoji and looks_like_emoji(emoji) else None
            )
        except TroppeEtichette:
            await interaction.response.send_message(await testo_per(interaction, "tickets_troppe_etichette", massimo=gestione.MAX_ETICHETTE), ephemeral=True)
            return
        except EtichettaGiaEsistente:
            await interaction.response.send_message(await testo_per(interaction, "tickets_etichetta_esiste", nome=nome), ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            return
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_etichetta_aggiunta", nome=nome), ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo(
        "admin-ticket",
        nome="togli",
        descrizione="Togli un'etichetta (sparisce dai ticket che la hanno).",
        sottogruppo=SOTTOGRUPPI["admin-ticket etichette"],
    )
    @app_commands.describe(nome="Il nome dell'etichetta")
    async def etichetta_togli(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, gestione.MAX_NOME_ETICHETTA]
    ) -> None:
        if interaction.guild is None:
            return
        chiave = "tickets_etichetta_tolta" if await ticket_gestione_repo.togli_etichetta(interaction.guild.id, nome) else "tickets_etichetta_non_trovata"
        await interaction.response.send_message(
            await testo_per(interaction, chiave, nome=nome.strip()[:40]), ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo(
        "admin-ticket",
        nome="elenco",
        descrizione="Elenca le etichette dei ticket.",
        sottogruppo=SOTTOGRUPPI["admin-ticket etichette"],
    )
    async def etichetta_elenco(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        etichette = await ticket_gestione_repo.elenca_etichette(interaction.guild.id)
        if not etichette:
            await interaction.response.send_message(await testo_per(interaction, "tickets_nessuna_etichetta"), ephemeral=True)
            return
        righe = [f"{e.emoji + ' ' if e.emoji else ''}{e.nome} · #{e.colore:06X}" for e in etichette]
        await interaction.response.send_message("\n".join(righe)[:2000], ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @comando_di_gruppo(
        "admin-ticket",
        nome="chiusura-auto",
        descrizione="Chiudi i ticket fermi da N minuti (0 = spenta).",
    )
    @app_commands.describe(pannello="Il pannello", minuti="Minuti senza messaggi (5-43200)")
    @app_commands.autocomplete(pannello=_completa_pannelli)
    async def chiusura_auto(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, form.MAX_NOME_PANNELLO],
        minuti: app_commands.Range[int, 0, form.MAX_MINUTI_CHIUSURA],
    ) -> None:
        panel = await self._pannello_o_risposta(interaction, pannello)
        if panel is None:
            return
        try:
            valore = form.minuti_chiusura_validi(minuti)
        except form.ErroreConfigurazione as errore:
            await interaction.response.send_message(str(errore), ephemeral=True)
            return
        await ticket_form_repo.imposta_chiusura_automatica(panel.id, valore)
        if valore is None:
            testo = f"Chiusura automatica spenta per **{panel.name}**."
        else:
            testo = (
                f"I ticket di **{panel.name}** senza messaggi da {valore} minuti si chiudono da soli "
                "(vale per i ticket aperti da ora in poi)."
            )
        await interaction.response.send_message(testo, ephemeral=True)

    @comando_di_gruppo(
        "admin-ticket",
        nome="voto",
        descrizione="Voto a stelle in DM alla chiusura.",
    )
    @app_commands.describe(pannello="Il pannello", attivo="Chiedi il voto")
    @app_commands.autocomplete(pannello=_completa_pannelli)
    async def voto(
        self,
        interaction: discord.Interaction,
        pannello: app_commands.Range[str, 1, form.MAX_NOME_PANNELLO],
        attivo: bool,
    ) -> None:
        panel = await self._pannello_o_risposta(interaction, pannello)
        if panel is None:
            return
        await ticket_form_repo.imposta_voto(panel.id, attivo)
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_voto_per", v1=(await testo_per(interaction, "opzioni_acceso")) if attivo else (await testo_per(interaction, "opzioni_spento")), name=panel.name), ephemeral=True
        )

    # ================================================================
    # SPEC.md §13.2 — categorie ticket configurabili
    # ================================================================
    @comando_di_gruppo(
        "admin-ticket",
        nome="aggiungi",
        descrizione="Aggiungi (o aggiorna) una categoria di ticket.",
        sottogruppo=SOTTOGRUPPI["admin-ticket categoria"],
    )
    @app_commands.describe(
        label="Nome mostrato nel select menu (es. 'Supporto tecnico')",
        category="La categoria Discord dove creare i canali di questa categoria",
        emoji="Emoji da mostrare accanto al nome (facoltativo)",
    )
    async def ticket_category_add(
        self,
        interaction: discord.Interaction,
        label: app_commands.Range[str, 1, MAX_CATEGORY_LABEL_LENGTH],
        category: discord.CategoryChannel,
        emoji: app_commands.Range[str, 1, MAX_EMOJI_LENGTH] | None = None,
    ) -> None:
        if interaction.guild is None:
            return

        label = label.strip()
        if not label:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_il_nome_della_categoria_non"), ephemeral=True
            )
            return
        if emoji is not None and not looks_like_emoji(emoji.strip()):
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_quella_non_sembra_un_emoji_2"),
                ephemeral=True,
            )
            return

        # Un menu a tendina tiene 25 opzioni (LIM-6). Aggiornare una
        # categoria che esiste già non ne aggiunge una.
        esistenti = await ticket_repo.list_categories(interaction.guild.id)
        if len(esistenti) >= MAX_TICKET_CATEGORIES and label not in {c.label for c in esistenti}:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_hai_gia_categorie_il_massimo", v1=MAX_TICKET_CATEGORIES),
                ephemeral=True,
            )
            return

        emoji = emoji.strip() if emoji is not None else None
        await ticket_repo.add_category(interaction.guild.id, label, category.id, emoji)
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_categoria_impostata_su", label=label, name=category.name), ephemeral=True
        )

    @comando_di_gruppo(
        "admin-ticket",
        nome="togli",
        descrizione="Rimuovi una categoria di ticket.",
        sottogruppo=SOTTOGRUPPI["admin-ticket categoria"],
    )
    @app_commands.describe(label="Il nome esatto della categoria da rimuovere")
    async def ticket_category_remove(
        self,
        interaction: discord.Interaction,
        label: app_commands.Range[str, 1, MAX_CATEGORY_LABEL_LENGTH],
    ) -> None:
        if interaction.guild is None:
            return
        rimossa = await ticket_repo.remove_category(interaction.guild.id, label.strip())
        if rimossa:
            await interaction.response.send_message(await testo_per(interaction, "tickets_categoria_rimossa", label=label), ephemeral=True)
        else:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_nessuna_categoria_chiamata", label=label), ephemeral=True
            )

    @comando_di_gruppo(
        "admin-ticket",
        nome="elenco",
        descrizione="Elenca le categorie di ticket configurate.",
        sottogruppo=SOTTOGRUPPI["admin-ticket categoria"],
    )
    async def ticket_category_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        categorie = await ticket_repo.list_categories(interaction.guild.id)
        if not categorie:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_nessuna_categoria_configurata_il_pannell"),
                ephemeral=True,
            )
            return
        # In un embed: 25 categorie con nomi lunghi superano i 2000
        # caratteri di un messaggio, ma stanno nei 4096 della descrizione.
        righe = [
            f"- {c.emoji or ''} **{truncate_label(c.label)}** -> <#{c.category_id}>"
            for c in categorie[:MAX_TICKET_CATEGORIES]
        ]
        mostrate: list[str] = []
        lunghezza = 0
        for riga in righe:
            lunghezza += len(riga) + 1
            if lunghezza > 4000:
                break
            mostrate.append(riga)
        if len(mostrate) < len(categorie):
            mostrate.append(f"…e altre {len(categorie) - len(mostrate)}.")
        embed = discord.Embed(
            title=await testo_per(interaction, "tickets_categorie_dei_ticket"),
            description="\n".join(mostrate),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ================================================================
    # SPEC.md §13.13 — ruoli di supporto multipli
    # ================================================================
    @comando_di_gruppo(
        "admin-ticket",
        nome="aggiungi",
        descrizione="Aggiungi un ruolo di supporto.",
        sottogruppo=SOTTOGRUPPI["admin-ticket ruolo"],
    )
    @app_commands.describe(
        role="Il ruolo da aggiungere",
        livello="Addetto: vede e risponde. Admin: chiude, forza la chiusura, «solo admin»",
    )
    @app_commands.choices(
        livello=[app_commands.Choice(name=n, value=n) for n in (LIVELLO_ADDETTO, LIVELLO_ADMIN)]
    )
    async def ticket_support_role_add(
        self, interaction: discord.Interaction, role: discord.Role, livello: app_commands.Choice[str] | None = None
    ) -> None:
        if interaction.guild is None:
            return
        attuali = await db.get_guild_setting(interaction.guild.id, SETTING_SUPPORT_ROLES, default=[])
        if role.id not in attuali:
            attuali.append(role.id)
            await db.set_guild_setting(interaction.guild.id, SETTING_SUPPORT_ROLES, attuali)
        if livello is not None:
            await ticket_repo.imposta_livello_ruolo(interaction.guild.id, role.id, livello.value)
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_ruolo_livello_impostato", mention=role.mention, livello=livello.value),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_aggiunto_ai_ruoli_di_supporto", mention=role.mention), ephemeral=True
        )

    @comando_di_gruppo(
        "admin-ticket",
        nome="togli",
        descrizione="Rimuovi un ruolo di supporto.",
        sottogruppo=SOTTOGRUPPI["admin-ticket ruolo"],
    )
    @app_commands.describe(role="Il ruolo da rimuovere")
    async def ticket_support_role_remove(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if interaction.guild is None:
            return
        guild_id = interaction.guild.id
        rimosso = False

        attuali = await db.get_guild_setting(guild_id, SETTING_SUPPORT_ROLES, default=[])
        if role.id in attuali:
            attuali.remove(role.id)
            await db.set_guild_setting(guild_id, SETTING_SUPPORT_ROLES, attuali, interaction.user.id)
            rimosso = True

        await ticket_repo.togli_livello_ruolo(guild_id, role.id)
        # Il ruolo può essere anche quello "storico" impostato con
        # /admin-ticket setup: va tolto pure da lì, altrimenti continua a
        # vedere i ticket. La chiave si toglie del tutto (un `null`
        # verrebbe poi rifiutato da /admin-bot config import).
        if await db.get_guild_setting(guild_id, SETTING_SUPPORT_ROLE) == role.id:
            await db.remove_guild_setting(guild_id, SETTING_SUPPORT_ROLE, interaction.user.id)
            rimosso = True

        if not rimosso:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_non_tra_ruoli_di_supporto", mention=role.mention), ephemeral=True
            )
            return
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_rimosso_dai_ruoli_di_supporto", mention=role.mention),
            ephemeral=True,
        )

    @comando_di_gruppo(
        "admin-ticket",
        nome="elenco",
        descrizione="Elenca i ruoli di supporto configurati.",
        sottogruppo=SOTTOGRUPPI["admin-ticket ruolo"],
    )
    async def ticket_support_role_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        ruoli_id = await _support_role_ids(interaction.guild.id)
        if not ruoli_id:
            await interaction.response.send_message(await testo_per(interaction, "tickets_nessun_ruolo_di_supporto_configurato"), ephemeral=True)
            return
        livelli = await ticket_repo.livelli_ruoli(interaction.guild.id)
        righe = [f"<@&{rid}> ({livelli.get(rid, LIVELLO_ADDETTO)})" for rid in ruoli_id]
        await interaction.response.send_message(", ".join(righe), ephemeral=True)

    # ================================================================
    # SPEC.md §13.12 — statistiche
    # ================================================================
    @comando_di_gruppo(
        "admin-ticket",
        nome="stats",
        descrizione="Statistiche del sistema di ticket.",
    )
    @app_commands.describe(operator="Mostra le statistiche di questo operatore invece di quelle del server")
    async def ticket_stats(
        self, interaction: discord.Interaction, operator: discord.Member | None = None
    ) -> None:
        if interaction.guild is None:
            return

        if operator is not None:
            stats = await ticket_repo.get_operator_stats(interaction.guild.id, operator.id)
            embed = discord.Embed(
                title=await testo_per(interaction, "tickets_statistiche_ticket", display_name=operator.display_name),
                color=discord.Color.blurple(),
            )
            embed.add_field(name=await testo_per(interaction, "tickets_presi_in_carico"), value=str(stats.claimed_count))
            embed.add_field(name=await testo_per(interaction, "tickets_chiusi"), value=str(stats.closed_count))
            embed.add_field(
                name=await testo_per(interaction, "tickets_tempo_medio_di_prima_risposta"),
                value=format_duration_seconds(stats.avg_response_seconds),
            )
        else:
            stats = await ticket_repo.get_guild_stats(interaction.guild.id)
            embed = discord.Embed(title=await testo_per(interaction, "tickets_statistiche_ticket_del_server"), color=discord.Color.blurple())
            embed.add_field(name=await testo_per(interaction, "tickets_totali"), value=str(stats.total_count))
            embed.add_field(name=await testo_per(interaction, "tickets_aperti"), value=str(stats.open_count))
            embed.add_field(name=await testo_per(interaction, "tickets_chiusi"), value=str(stats.closed_count))
            embed.add_field(
                name=await testo_per(interaction, "tickets_tempo_medio_di_prima_risposta"),
                value=format_duration_seconds(stats.avg_response_seconds),
            )
            media, voti = await ticket_repo.get_rating_summary(interaction.guild.id)
            embed.add_field(name=await testo_per(interaction, "tickets_voto_medio"), value=form.Media(media, voti).testo())

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _get_ticket_or_reply(self, interaction: discord.Interaction):
        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id)
        if ticket is None or ticket.status != "open":
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_questo_comando_funziona_solo_dentro"),
                ephemeral=True,
            )
            return None
        return ticket

    async def _get_ticket_for_staff_or_reply(self, interaction: discord.Interaction):
        """Come _get_ticket_or_reply, ma solo per lo staff dei ticket (anche la squadra del pannello, TKT-044)."""
        if not await _is_ticket_staff(interaction, await ticket_repo.get_ticket_by_channel(interaction.channel.id)):
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_solo_lo_staff_permesso_manage"),
                ephemeral=True,
            )
            return None
        return await self._get_ticket_or_reply(interaction)

    @comando_di_gruppo("ticket", nome="claim", descrizione="Prendi in carico questo ticket.")
    async def claim(self, interaction: discord.Interaction) -> None:
        ticket = await self._get_ticket_for_staff_or_reply(interaction)
        if ticket is None:
            return

        opzioni = await _opzioni_pannello(ticket.panel_id)
        esclusiva = opzioni.claim_esclusivo != "no"
        if esclusiva and ticket.claimed_by not in (None, interaction.user.id) and not _puo_scavalcare(interaction.user):
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_il_ticket_gia_di_deve", claimed_by=ticket.claimed_by),
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        await interaction.response.defer()
        # Con l'esclusiva vince uno solo anche se due lo prendono insieme (chi scavalca no).
        solo_se_libero = esclusiva and ticket.claimed_by is None
        if not await ticket_repo.claim_ticket(interaction.channel.id, interaction.user.id, solo_se_libero=solo_se_libero):
            await interaction.followup.send(await testo_per(interaction, "tickets_un_altro_dello_staff_ha"), ephemeral=True)
            return
        testo = await self._dopo_presa(
            interaction.guild, interaction.channel, ticket, interaction.user, precedente=ticket.claimed_by
        )
        await interaction.followup.send(testo, view=vista_inizio(interaction.channel))

    async def _dopo_presa(self, guild: discord.Guild, channel, ticket, staff, *, precedente: int | None = None) -> str:
        """
        TKT-028 categoria dei presi, TKT-050 esclusiva, TKT-053 testo. Restituisce il messaggio da
        mostrare. `precedente` è chi aveva il ticket prima: con l'esclusiva perde i suoi permessi.
        """
        opzioni = await _opzioni_pannello(ticket.panel_id)
        e_thread = isinstance(channel, discord.Thread)
        if opzioni.categoria_presi and not e_thread:
            categoria = guild.get_channel(opzioni.categoria_presi)
            if isinstance(categoria, discord.CategoryChannel) and len(categoria.channels) < opz_logic.MAX_CANALI_PER_CATEGORIA:
                try:
                    await channel.edit(category=categoria, sync_permissions=False, reason="Ticket preso in carico")
                except discord.HTTPException:
                    logger.warning("Ticket %s non spostato nella categoria dei presi.", channel.id)
        if opzioni.prefisso_preso:
            await self._rinomina_con_prefisso(
                channel, opzioni.prefisso_preso, (opzioni.prefisso_preso, opzioni.prefisso_chiuso), "Ticket preso in carico"
            )
        if opzioni.claim_esclusivo != "no" and not e_thread:
            await self._permessi_staff(
                guild, channel, ticket.panel_id, esclusiva=opzioni.claim_esclusivo, titolare=staff,
                solo_admin=ticket.solo_admin,
            )
            if precedente is not None and precedente not in (staff.id, ticket.user_id):
                await self._togli_permessi_personali(guild, channel, precedente)
        if opzioni.testo_presa:
            return opz_logic.riempi(
                opzioni.testo_presa, utente=f"<@{ticket.user_id}>", server=guild.name,
                numero=ticket.ticket_number or 0, staff=staff.mention,
            )
        return f"Ticket preso in carico da {staff.mention}."

    @staticmethod
    async def _togli_permessi_personali(guild: discord.Guild, channel, user_id: int) -> None:
        """TKT-050: chi lascia (o perde) il ticket esclusivo torna ai permessi del suo ruolo."""
        membro = guild.get_member(user_id) or discord.Object(id=user_id)
        try:
            await channel.set_permissions(membro, overwrite=None, reason="Presa in carico passata ad altri")
        except discord.HTTPException:
            logger.warning("Permessi di %s non tolti dal ticket %s.", user_id, channel.id)

    async def _permessi_staff(
        self, guild: discord.Guild, channel, panel_id, *, esclusiva: str, titolare=None, solo_admin: bool = False
    ) -> None:
        """
        TKT-050: con la presa esclusiva i ruoli dello staff non scrivono ("scrivere") o non vedono
        ("vedere"); chi ha il ticket scrive sempre. esclusiva="no" rimette i ruoli come all'apertura.
        Si cambia un permesso solo: overwrites_for + update + overwrite=.
        TKT-046: in un ticket «solo admin» i ruoli degli addetti non si toccano (restano fuori).
        """
        ruoli = ruoli_con_accesso(await _ruoli_staff(guild.id, panel_id), await _ruoli_admin(guild.id), solo_admin)
        for role_id in ruoli:
            role = guild.get_role(role_id)
            if role is None or role_id == guild.id:
                continue
            ow = channel.overwrites_for(role)
            if esclusiva == "vedere":
                ow.update(view_channel=False)
            elif esclusiva == "scrivere":
                ow.update(view_channel=True, send_messages=False)
            else:
                ow.update(view_channel=True, send_messages=True, read_message_history=True)
            try:
                await channel.set_permissions(role, overwrite=ow, reason="Presa in carico del ticket"[:512])
            except discord.HTTPException:
                logger.warning("Permessi dello staff non cambiati nel ticket %s.", channel.id)
        if titolare is not None:
            ow = channel.overwrites_for(titolare)
            ow.update(view_channel=True, send_messages=True, read_message_history=True)
            try:
                await channel.set_permissions(titolare, overwrite=ow)
            except discord.HTTPException:
                logger.warning("Permessi di chi ha il ticket %s non dati.", channel.id)

    @staticmethod
    async def _bersaglio_o_risposta(interaction: discord.Interaction, member, ruolo):
        """TKT-047: un utente oppure un ruolo intero (mai @everyone). None dopo aver risposto."""
        if (member is None) == (ruolo is None):
            await interaction.response.send_message(await testo_per(interaction, "tickets_scegli_un_utente_oppure_un"), ephemeral=True)
            return None
        bersaglio = member or ruolo
        if ruolo is not None and ruolo.id == interaction.guild.id:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_everyone_non_si_puo_aggiungere"), ephemeral=True
            )
            return None
        return bersaglio

    @comando_di_gruppo("ticket", nome="add", descrizione="Aggiungi un utente o un ruolo a questo ticket.")
    @app_commands.describe(member="L'utente da aggiungere", ruolo="Oppure un ruolo intero")
    async def add(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        ruolo: discord.Role | None = None,
    ) -> None:
        ticket = await self._get_ticket_for_staff_or_reply(interaction)
        if ticket is None:
            return
        bersaglio = await self._bersaglio_o_risposta(interaction, member, ruolo)
        if bersaglio is None:
            return

        try:
            if isinstance(interaction.channel, discord.Thread):
                if not isinstance(bersaglio, discord.Member):
                    await interaction.response.send_message(await testo_per(interaction, "tickets_thread_non_disponibile"), ephemeral=True)
                    return
                await interaction.channel.add_user(bersaglio)
            else:
                await interaction.channel.set_permissions(
                    bersaglio, view_channel=True, send_messages=True, read_message_history=True
                )
        except discord.HTTPException:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_non_sono_riuscito_ad_aggiungere"),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_aggiunto_al_ticket", pubblica=True, mention=bersaglio.mention), allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo("ticket", nome="remove", descrizione="Rimuovi un utente o un ruolo da questo ticket.")
    @app_commands.describe(member="L'utente da rimuovere", ruolo="Oppure un ruolo intero")
    async def remove(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        ruolo: discord.Role | None = None,
    ) -> None:
        ticket = await self._get_ticket_for_staff_or_reply(interaction)
        if ticket is None:
            return
        bersaglio = await self._bersaglio_o_risposta(interaction, member, ruolo)
        if bersaglio is None:
            return
        if ruolo is not None and (
            ruolo.managed
            or ruolo in getattr(interaction.guild.me, "roles", [])
            or ruolo.id in await _support_role_ids(interaction.guild.id)
        ):
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_questo_ruolo_dello_staff_dei"),
                ephemeral=True,
            )
            return

        try:
            if isinstance(interaction.channel, discord.Thread):
                if not isinstance(bersaglio, discord.Member):
                    await interaction.response.send_message(await testo_per(interaction, "tickets_thread_non_disponibile"), ephemeral=True)
                    return
                await interaction.channel.remove_user(bersaglio)
            else:
                await interaction.channel.set_permissions(bersaglio, overwrite=None)
        except discord.HTTPException:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_non_sono_riuscito_rimuovere_il"),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_rimosso_dal_ticket", pubblica=True, mention=bersaglio.mention), allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo("ticket", nome="rilascia", descrizione="Lascia la presa in carico di questo ticket.")
    async def rilascia(self, interaction: discord.Interaction) -> None:
        ticket = await self._get_ticket_for_staff_or_reply(interaction)
        if ticket is None:
            return
        if ticket.claimed_by is None:
            await interaction.response.send_message(await testo_per(interaction, "tickets_nessuno_ha_preso_in_carico"), ephemeral=True)
            return
        if ticket.claimed_by != interaction.user.id and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_solo_chi_lo_ha_preso"), ephemeral=True
            )
            return
        await interaction.response.defer()
        await ticket_repo.release_ticket(interaction.channel.id)
        opzioni = await _opzioni_pannello(ticket.panel_id)
        if opzioni.claim_esclusivo != "no":
            await self._permessi_staff(
                interaction.guild, interaction.channel, ticket.panel_id, esclusiva="no", solo_admin=ticket.solo_admin
            )
            if ticket.claimed_by != ticket.user_id:
                await self._togli_permessi_personali(interaction.guild, interaction.channel, ticket.claimed_by)
        testo = (
            opz_logic.riempi(
                opzioni.testo_rilascio, utente=f"<@{ticket.user_id}>", server=interaction.guild.name,
                numero=ticket.ticket_number or 0, staff=interaction.user.mention,
            )
            if opzioni.testo_rilascio
            else f"{interaction.user.mention} ha lasciato il ticket: può prenderlo un altro con `/ticket claim`."
        )
        await interaction.followup.send(testo, allowed_mentions=discord.AllowedMentions.none())

    @comando_di_gruppo("ticket", nome="passa", descrizione="Passa la presa in carico a un collega.")
    @app_commands.describe(collega="Il collega dello staff")
    async def passa(self, interaction: discord.Interaction, collega: discord.Member) -> None:
        ticket = await self._get_ticket_for_staff_or_reply(interaction)
        if ticket is None:
            return
        if collega.bot or not await _membro_staff(collega, interaction.guild.id, ticket.panel_id):
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_non_fa_parte_dello_staff", mention=collega.mention),
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        opzioni = await _opzioni_pannello(ticket.panel_id)
        if (
            opzioni.claim_esclusivo != "no" and ticket.claimed_by not in (None, interaction.user.id)
            and not _puo_scavalcare(interaction.user)
        ):
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_il_ticket_di_lo_passa", claimed_by=ticket.claimed_by),
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        await interaction.response.defer()
        await ticket_repo.claim_ticket(interaction.channel.id, collega.id)
        testo = await self._dopo_presa(
            interaction.guild, interaction.channel, ticket, collega, precedente=ticket.claimed_by
        )
        await interaction.followup.send(f"Ticket passato a {collega.mention}.\n{testo}"[:2000])

    @comando_di_gruppo("ticket", nome="note", descrizione="Thread privato dello staff per parlare del ticket.")
    async def note(self, interaction: discord.Interaction) -> None:
        """TKT-034: un thread privato attaccato al ticket; l'utente non lo vede."""
        ticket = await self._get_ticket_for_staff_or_reply(interaction)
        if ticket is None:
            return
        await interaction.response.defer(ephemeral=True)
        thread = await self._thread_delle_note(interaction.guild, ticket.note_thread_id)
        if thread is None:
            try:
                thread = await interaction.channel.create_thread(
                    name=f"note-{ticket.ticket_number or 0:04d}",
                    type=discord.ChannelType.private_thread,
                    invitable=False,
                    reason=f"Note dello staff, ticket {ticket.ticket_number or 0}"[:512],
                )
            except discord.HTTPException:
                await interaction.followup.send(
                    await testo_per(interaction, "tickets_non_riesco_creare_il_thread"), ephemeral=True
                )
                return
            await ticket_repo.imposta_note_thread(interaction.channel.id, thread.id)
        try:
            await thread.add_user(interaction.user)
        except discord.HTTPException:
            logger.warning("Staff %s non aggiunto al thread delle note %s.", interaction.user.id, thread.id)
        await interaction.followup.send(await testo_per(interaction, "tickets_note_dello_staff", mention=thread.mention), ephemeral=True)

    async def _thread_delle_note(self, guild: discord.Guild, thread_id: int | None):
        """
        TKT-034: il thread delle note già creato. Uno archiviato non sta nella cache
        (`get_thread`): si chiede a Discord e lo si riapre, invece di crearne un altro.
        """
        if not thread_id:
            return None
        thread = guild.get_thread(thread_id)
        if thread is None:
            try:
                thread = await guild.fetch_channel(thread_id)
            except discord.HTTPException:
                return None  # cancellato (o non più leggibile): se ne crea uno nuovo
        if not isinstance(thread, discord.Thread):
            return None
        if thread.archived:
            try:
                await thread.edit(archived=False)
            except discord.HTTPException:
                logger.warning("Thread delle note %s non riaperto.", thread_id)
        return thread

    @comando_di_gruppo("ticket", nome="chiedi-chiusura", descrizione="Chiedi all'utente se il ticket si può chiudere.")
    @app_commands.describe(ore="Senza risposta il ticket si chiude dopo queste ore")
    async def chiedi_chiusura(
        self,
        interaction: discord.Interaction,
        ore: app_commands.Range[int, 1, opz_logic.MAX_ORE_RICHIESTA_CHIUSURA] = 24,
    ) -> None:
        """TKT-055: Accetta chiude, Rifiuta annulla; senza risposta lo scheduler chiude."""
        ticket = await self._get_ticket_for_staff_or_reply(interaction)
        if ticket is None:
            return
        await interaction.response.defer()
        richiesta = await ticket_repo.richiedi_chiusura(interaction.channel.id)
        if richiesta is None:
            await interaction.followup.send(await testo_per(interaction, "tickets_questo_ticket_non_piu_aperto"), ephemeral=True)
            return
        await scheduler.schedule(
            interaction.guild.id, ticket.user_id, TICKET_RICHIESTA_CHIUSURA_ACTION_TYPE, in_seconds(ore * 3600),
            {"channel_id": interaction.channel.id, "richiesta": richiesta.isoformat()},
        )
        vista = BaseView(timeout=None)
        vista.add_item(BottoneRichiestaChiusura(ticket.id, "a"))
        vista.add_item(BottoneRichiestaChiusura(ticket.id, "r"))
        await interaction.followup.send(
            await testo_per(interaction, "tickets_chiede_se_il_tuo_problema", pubblica=True, user_id=ticket.user_id, mention=interaction.user.mention, ore=ore),
            view=vista_inizio(interaction.channel, vista),
            allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=ticket.user_id)]),
        )

    async def handle_richiesta_chiusura(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Handler dello scheduler: chiude se la stessa richiesta è ancora senza risposta."""
        channel_id = payload["channel_id"]
        ticket = await ticket_repo.get_ticket_by_channel(channel_id)
        if ticket is None or ticket.status != "open" or ticket.chiusura_richiesta_at is None:
            return
        if ticket.chiusura_richiesta_at.isoformat() != payload.get("richiesta"):
            return  # c'è stata una richiesta più nuova: decide il suo timer
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.NotFound:
                await ticket_repo.close_ticket_of_deleted_channel(channel_id)
                return
        await self._chiudi_da_sistema(
            channel.guild, channel, ticket,
            motivo="Nessuna risposta alla richiesta di chiusura",
            avviso="Nessuna risposta alla richiesta di chiusura: ticket chiuso. Il canale verrà eliminato a breve.",
            chiedi_voto=True,
            ragione="Nessuna risposta alla richiesta di chiusura",
        )

    @comando_di_gruppo("ticket", nome="transcript", descrizione="Ricevi il transcript senza chiudere il ticket.")
    async def transcript(self, interaction: discord.Interaction) -> None:
        ticket = await self._get_ticket_for_staff_or_reply(interaction)
        if ticket is None:
            return
        await interaction.response.defer(ephemeral=True)
        try:
            file_pronti = await self._file_transcript(interaction.guild, interaction.channel, ticket)
        except discord.HTTPException:
            await interaction.followup.send(
                await testo_per(interaction, "tickets_non_riesco_leggere_messaggi_del"), ephemeral=True
            )
            return
        for nome_file, contenuto in file_pronti:
            await interaction.followup.send(
                file=discord.File(io.BytesIO(contenuto), filename=nome_file), ephemeral=True
            )

    @comando_di_gruppo("ticket", nome="rename", descrizione="Rinomina questo ticket.")
    @app_commands.describe(name="Il nuovo nome del canale")
    async def rename(
        self,
        interaction: discord.Interaction,
        name: app_commands.Range[str, 1, MAX_CHANNEL_NAME_LENGTH],
    ) -> None:
        ticket = await self._get_ticket_or_reply(interaction)
        if ticket is None:
            return

        # Discord permette 2 rinomine ogni 10 minuti per canale (LIM-3):
        # alla terza si risponde subito, senza restare in attesa.
        attesa = rename_tracker.seconds_until_allowed(interaction.channel.id)
        if attesa > 0:
            await interaction.response.send_message(
                rename_limit_message(attesa), ephemeral=True
            )
            return

        await interaction.response.defer()
        try:
            await rename_channel(
                interaction.channel, name, reason=f"Ticket rinominato da {interaction.user}"
            )
        except RenameRateLimited as limite:
            await interaction.followup.send(
                rename_limit_message(limite.retry_after), ephemeral=True
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                await testo_per(interaction, "tickets_non_sono_riuscito_rinominare_il"),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            await testo_per(interaction, "tickets_ticket_rinominato_in", pubblica=True, name=name),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo("ticket", nome="priority", descrizione="Imposta la priorità di questo ticket.")
    @app_commands.describe(level="Livello di priorità")
    @app_commands.choices(
        level=[app_commands.Choice(name=p, value=p) for p in VALID_PRIORITIES]
    )
    async def priority(
        self, interaction: discord.Interaction, level: app_commands.Choice[str]
    ) -> None:
        ticket = await self._get_ticket_for_staff_or_reply(interaction)
        if ticket is None:
            return

        await ticket_repo.set_priority(interaction.channel.id, level.value)
        emoji = PRIORITY_EMOJI.get(level.value, "")
        await interaction.response.send_message(
            f"Priorità impostata su {emoji} **{level.value}**."
        )

    async def _build_transcript_text(self, channel: discord.TextChannel, ticket) -> str:
        """
        SPEC.md §13.10: legge la history del canale e la trasforma in
        testo semplice tramite le funzioni pure di core/ticket_logic.py.
        Senza l'intent Message Content Discord consegna i messaggi
        vuoti (BUG-5): in quel caso l'intestazione lo dice.
        """
        messaggi = [m async for m in channel.history(limit=None, oldest_first=True)]
        return self._testo_da_messaggi(ticket, messaggi)

    def _testo_da_messaggi(self, ticket, messaggi) -> str:
        header = [
            f"Transcript ticket #{ticket.ticket_number:04d}",
            f"Aperto da: {ticket.user_id} il {ticket.created_at.isoformat()}",
            f"Categoria: {ticket.category_label or 'n/d'}",
            f"Priorità: {ticket.priority}",
            f"Preso in carico da: {ticket.claimed_by or 'nessuno'}",
        ]
        if ticket.close_reason:
            header.append(f"Motivo di chiusura: {ticket.close_reason}")
        if not self.bot.intents.message_content:
            header.append(MESSAGE_CONTENT_WARNING)
        righe = []
        for messaggio in messaggi:
            righe.append(
                format_transcript_line(
                    messaggio.created_at.strftime("%Y-%m-%d %H:%M"),
                    str(messaggio.author),
                    messaggio.content,
                    [allegato.filename for allegato in messaggio.attachments],
                )
            )
        return build_transcript_text(header, righe)

    @staticmethod
    def _transcript_files(testo: str, ticket_number: int) -> list[tuple[str, bytes]]:
        """
        (nome, contenuto) dei file del transcript: uno solo di norma,
        più d'uno se il testo supera il limite di peso (LIM-55).
        """
        base = f"ticket-{ticket_number:04d}-transcript"
        parti = split_text_by_size(testo, MAX_TRANSCRIPT_FILE_BYTES)
        if len(parti) == 1:
            return [(f"{base}.txt", parti[0].encode("utf-8"))]
        return [
            (f"{base}-parte-{numero}-di-{len(parti)}.txt", parte.encode("utf-8"))
            for numero, parte in enumerate(parti, start=1)
        ]

    async def _allegati_trascritti(self, guild: discord.Guild, messaggio, conteggio: list[int]) -> tuple[AllegatoT, ...]:
        """
        TKT-070/074: nome, peso e impronta di ogni allegato. Le immagini passano dalla pipeline (D62):
        si tiene solo la copia ricodificata di quelle pulite, mai l'originale.
        """
        risultato = []
        for allegato in messaggio.attachments:
            png, sha = b"", ""
            tipo = (getattr(allegato, "content_type", None) or "").lower()
            e_immagine = tipo.startswith("image/") or allegato.filename.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp")
            )
            if e_immagine and conteggio[0] < tr_logic.MAX_IMMAGINI and (allegato.size or 0) <= MAX_BYTE_IMMAGINE_TRANSCRIPT:
                conteggio[0] += 1
                try:
                    esito = await analizza_immagine(await allegato.read(), allegato.filename, tipo or None, guild.id)
                    sha = esito.sha256
                    if esito.verdetto == PULITA and esito.non_analizzata is None and esito.png:
                        png = esito.png
                except Exception:  # noqa: BLE001 - un allegato che non si legge non ferma il transcript
                    logger.warning("Allegato del transcript non analizzato nel ticket %s.", messaggio.channel.id, exc_info=True)
            risultato.append(AllegatoT(allegato.filename, allegato.size or 0, sha, png))
        return tuple(risultato)

    async def _file_transcript(self, guild: discord.Guild, channel, ticket) -> list[tuple[str, bytes]]:
        """
        I file del transcript secondo il pannello (TKT-071): testo, HTML o entrambi, più lo ZIP delle immagini
        controllate (TKT-074). Con le opzioni di base è identico al transcript testuale di sempre.
        """
        opzioni = await _opzioni_pannello(ticket.panel_id)
        formato = tr_logic.formato_valido(opzioni.transcript_formato)
        if formato == "testo" and not opzioni.allegati_zip:
            return self._transcript_files(await self._build_transcript_text(channel, ticket), ticket.ticket_number)
        messaggi = [m async for m in channel.history(limit=None, oldest_first=True)]
        base = f"ticket-{ticket.ticket_number:04d}"
        file_pronti: list[tuple[str, bytes]] = []
        if formato in ("testo", "entrambi"):
            file_pronti += self._transcript_files(self._testo_da_messaggi(ticket, messaggi), ticket.ticket_number)
        conteggio = [0]
        convertiti = []
        tutti: list[AllegatoT] = []
        for m in messaggi:
            allegati = await self._allegati_trascritti(guild, m, conteggio)
            tutti += allegati
            testo = m.content or ""
            for e in getattr(m, "embeds", None) or []:
                testo += "\n" + "\n".join(x for x in (getattr(e, "title", None), getattr(e, "description", None)) if x)
            convertiti.append(tr_logic.MessaggioT(
                m.created_at.strftime("%Y-%m-%d %H:%M"), str(m.author), testo.strip(), allegati,
                bool(getattr(m.author, "bot", False)),
            ))
        if formato in ("html", "entrambi"):
            riga = lambda k, v: (k, str(v))  # noqa: E731
            testata = tr_logic.IntestazioneT(
                ticket.ticket_number,
                tuple(riga(k, v) for k, v in (
                    ("Aperto da", ticket.user_id), ("Aperto il", ticket.created_at.isoformat()),
                    ("Categoria", ticket.category_label or "n/d"), ("Priorità", ticket.priority),
                    ("Preso in carico da", ticket.claimed_by or "nessuno"),
                ) + ((("Motivo di chiusura", ticket.close_reason),) if ticket.close_reason else ())),
                None if self.bot.intents.message_content else MESSAGE_CONTENT_WARNING,
            )
            parti = tr_logic.html_in_parti(testata, convertiti)
            for numero, pagina in enumerate(parti, start=1):
                nome = f"{base}-transcript.html" if len(parti) == 1 else f"{base}-transcript-parte-{numero}-di-{len(parti)}.html"
                file_pronti.append((nome, pagina.encode("utf-8")))
        if opzioni.allegati_zip:
            archivio = tr_logic.zip_allegati(tutti)
            if archivio:
                file_pronti.append((f"{base}-allegati.zip", archivio))
        return file_pronti

    async def _deliver_transcript(
        self, guild: discord.Guild, channel: discord.TextChannel, ticket, *, dm: bool = True
    ) -> None:
        """SPEC.md §13.11: invio nel canale log configurato + DM all'utente (se il pannello lo vuole, TKT-075)."""
        try:
            file_del_transcript = await self._file_transcript(guild, channel, ticket)
        except discord.HTTPException:
            logger.warning("Impossibile leggere la history del ticket %s per il transcript", channel.id)
            return

        # Il canale dei log può essere un forum: il router lo gestisce (post nel forum).
        predefinito = await db.get_guild_setting(guild.id, SETTING_LOG_CHANNEL)
        destinazione = await router.destinazione(guild, TIPO_EVENTI, predefinito)
        if destinazione is not None:
            for nome_file, contenuto in file_del_transcript:
                await router.invia_a(
                    destinazione,
                    guild,
                    TIPO_EVENTI,
                    content=f"Transcript ticket #{ticket.ticket_number:04d}",
                    file=discord.File(io.BytesIO(contenuto), filename=nome_file),
                )

        if not dm:
            return
        try:
            utente = guild.get_member(ticket.user_id) or await self.bot.fetch_user(ticket.user_id)
            for nome_file, contenuto in file_del_transcript:
                await utente.send(
                    content=f"Ecco il transcript del tuo ticket #{ticket.ticket_number:04d}.",
                    file=discord.File(io.BytesIO(contenuto), filename=nome_file),
                )
        except discord.HTTPException:
            logger.info("Impossibile inviare il transcript in DM all'utente %s (DM chiusi?)", ticket.user_id)

    async def _transcript_senza_bloccare(
        self, guild: discord.Guild, channel: discord.TextChannel, ticket
    ) -> None:
        """Un transcript che fallisce non deve mai impedire l'eliminazione del canale."""
        self._transcript_in_corso.add(channel.id)
        opzioni = Opzioni()
        try:
            opzioni = await _opzioni_pannello(ticket.panel_id)
            await self._deliver_transcript(guild, channel, ticket, dm=opzioni.transcript_dm)
        except Exception:
            logger.exception("Transcript del ticket %s non riuscito", channel.id)
        try:
            await self._fine_ticket(guild, ticket, opzioni)
        except Exception:
            logger.exception("Ruoli o DM di chiusura del ticket %s non riusciti", channel.id)
        try:
            # #139: dopo la chiusura il bot propone allo staff di salvare la risposta come standard.
            risposte = self._cog_risposte()
            if risposte is not None:
                await risposte.proponi_da_ticket(guild, channel, ticket)
        except Exception:
            logger.exception("Proposta di risposta standard del ticket %s non riuscita", channel.id)
        finally:
            self._transcript_in_corso.discard(channel.id)

    async def _fine_ticket(self, guild: discord.Guild, ticket, opzioni: Opzioni) -> None:
        """TKT-043: toglie i ruoli dati all'apertura; TKT-039: DM di chiusura scelto dal server."""
        membro = guild.get_member(ticket.user_id)
        if membro is None:
            return
        ruoli = [r for r in (guild.get_role(i) for i in ticket.ruoli_dati) if r is not None and r in membro.roles]
        if ruoli:
            try:
                await membro.remove_roles(*ruoli, reason="Ticket chiuso")
            except discord.HTTPException:
                logger.warning("Ruoli del ticket non tolti a %s nel server %s.", membro.id, guild.id)
        if opzioni.dm_chiusura:
            testo = opz_logic.riempi(
                opzioni.dm_chiusura, utente=membro.mention, server=guild.name, numero=ticket.ticket_number or 0
            )
            try:
                await membro.send(testo[:2000])
            except discord.HTTPException:
                logger.info("DM di chiusura non consegnato a %s (DM chiusi?).", membro.id)

    async def _elimina_canale(self, channel_id: int, motivo: str | None) -> None:
        """
        Elimina il canale del ticket. 404 = già eliminato, 403 = solo
        registrato (riprovare non serve). Gli altri errori di Discord
        (5xx) escono: chi chiama riprova più tardi.
        """
        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
            await channel.delete(reason=motivo)
        except discord.NotFound:
            return
        except discord.Forbidden:
            logger.warning("Permessi mancanti per eliminare il canale ticket %s", channel_id)

    async def _pianifica_eliminazione(
        self, interaction: discord.Interaction, motivo: str, ritardo: int
    ) -> None:
        """BUG-30: nello scheduler persistente, non in un task in memoria."""
        await self._pianifica_eliminazione_canale(
            interaction.guild.id, interaction.user.id, interaction.channel.id, motivo, ritardo
        )

    async def _pianifica_eliminazione_canale(
        self, guild_id: int, user_id: int, channel_id: int, motivo: str, ritardo: int
    ) -> None:
        await scheduler.schedule(
            guild_id,
            user_id,
            TICKET_DELETE_ACTION_TYPE,
            in_seconds(ritardo),
            {"channel_id": channel_id, "reason": motivo},
        )

    # ================================================================
    # NF-13 — voto alla chiusura e chiusura automatica
    # ================================================================
    async def _richiedi_voto(self, guild: discord.Guild, ticket) -> None:
        """Se il pannello del ticket ha il voto acceso, manda le 5 stelle in DM a chi lo ha aperto."""
        if ticket.panel_id is None:
            return
        try:
            panel = await ticket_form_repo.pannello_per_id(ticket.panel_id)
            if panel is None or not panel.rating_enabled:
                return
            utente = guild.get_member(ticket.user_id) or await self.bot.fetch_user(ticket.user_id)
            await utente.send(
                f"Com'è andato il tuo ticket #{ticket.ticket_number:04d} su **{guild.name}**? "
                "Dai un voto da 1 a 5 stelle.",
                view=vista_voto(ticket.id),
            )
        except discord.HTTPException:
            logger.info("Richiesta di voto non consegnata all'utente %s (DM chiusi?)", ticket.user_id)
        except Exception:  # noqa: BLE001 - il voto non deve mai bloccare una chiusura
            logger.exception("Richiesta di voto del ticket %s non riuscita", ticket.id)

    async def handle_ticket_autoclose(self, guild_id: int, user_id: int, payload: dict) -> None:
        """
        Handler dello scheduler: chiude il ticket se è fermo da almeno N minuti, altrimenti
        riprogramma il controllo per il momento in cui scadrebbe. Se solleva, lo scheduler riprova.
        """
        channel_id = payload["channel_id"]
        ticket = await ticket_repo.get_ticket_by_channel(channel_id)
        if ticket is None or ticket.status != "open" or ticket.panel_id is None:
            return
        panel = await ticket_form_repo.pannello_per_id(ticket.panel_id)
        if panel is None or not panel.autoclose_minutes:
            return
        ultima = ticket.last_activity_at or ticket.created_at
        prossimo = form.prossimo_controllo(ultima, datetime.now(timezone.utc), panel.autoclose_minutes)
        if prossimo is not None:
            await scheduler.schedule(guild_id, user_id, TICKET_AUTOCLOSE_ACTION_TYPE, prossimo, payload)
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.NotFound:
                await ticket_repo.close_ticket_of_deleted_channel(channel_id)
                return
        await self._chiudi_da_sistema(
            channel.guild,
            channel,
            ticket,
            motivo="Ticket chiuso per inattività",
            avviso=(
                f"Ticket chiuso automaticamente: nessun messaggio da {panel.autoclose_minutes} minuti. "
                "Questo canale verrà eliminato a breve."
            ),
            chiedi_voto=True,
            ragione="Chiuso per inattività",
        )

    async def _chiudi_e_pianifica(
        self, guild_id: int, channel_id: int, chiuso_da: int, ragione: str | None, user_id: int, motivo_log: str
    ) -> bool:
        """
        Chiude il ticket e pianifica l'eliminazione del canale come un passo solo: se la
        pianificazione fallisce, il ticket torna aperto e chi riprova (scheduler, utente) trova
        tutto com'era. False se era già chiuso (due chiusure insieme: ne vince una).
        """
        prima = await ticket_repo.get_ticket_by_channel(channel_id)
        opzioni = await _opzioni_pannello(prima.panel_id) if prima is not None else Opzioni()
        if not await ticket_repo.close_ticket(channel_id, chiuso_da, reason=ragione):
            return False
        try:
            # TKT-051/063: con la chiusura in due passi il canale resta; si elimina dopo N ore, se scelto.
            ritardo = RITARDO_ELIMINAZIONE_SECONDI
            if opzioni.chiusura_due_passi:
                ritardo = opzioni.elimina_dopo_ore * 3600 if opzioni.elimina_dopo_ore else None
            if ritardo is not None:
                await self._pianifica_eliminazione_canale(guild_id, user_id, channel_id, motivo_log, ritardo)
        except Exception:
            await ticket_repo.riapri_dopo_errore(channel_id)
            raise
        return True

    async def _chiudi_da_sistema(
        self,
        guild: discord.Guild,
        channel,
        ticket,
        *,
        motivo: str,
        avviso: str,
        chiedi_voto: bool,
        chiuso_da: int | None = None,
        ragione: str | None = None,
        avviso_pronto: bool = False,
    ) -> bool:
        """
        Chiusura fatta dal bot (inattività, utente uscito) o per conto dello staff (chiusura di
        massa): stesso ordine di /ticket close. `ragione` è il motivo salvato col ticket.
        `avviso_pronto`: il testo dice già se il canale resta (lingua del server), non si cambia.
        """
        if not await self._chiudi_e_pianifica(
            guild.id, channel.id, chiuso_da or guild.me.id, ragione, ticket.user_id, motivo
        ):
            return False
        ticket = await ticket_repo.get_ticket_by_channel(channel.id) or ticket
        due_passi = (await _opzioni_pannello(ticket.panel_id)).chiusura_due_passi
        if due_passi and not avviso_pronto:
            avviso = avviso.replace("Questo canale verrà eliminato a breve.", TESTO_CANALE_RESTA)
        try:
            await channel.send(avviso, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            logger.warning("Avviso di chiusura non inviato nel ticket %s.", channel.id)
        await self._transcript_senza_bloccare(guild, channel, ticket)
        await self._stato_chiuso(guild, channel, ticket)
        if chiedi_voto:
            await self._richiedi_voto(guild, ticket)
        return True

    @comando_di_gruppo(
        "admin-ticket",
        nome="chiudi-tutti",
        descrizione="Chiudi i ticket aperti (fino a 25 alla volta).",
    )
    @app_commands.describe(motivo="Il motivo, salvato in ogni ticket")
    async def chiudi_tutti(
        self,
        interaction: discord.Interaction,
        motivo: app_commands.Range[str, 1, MAX_MOTIVO_CHIUSURA] | None = None,
    ) -> None:
        if interaction.guild is None:
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        chiusi = 0
        falliti = 0
        for ticket in await ticket_repo.list_open_tickets(guild.id, MAX_CHIUSURA_DI_MASSA):
            channel = guild.get_channel_or_thread(ticket.channel_id)
            if channel is None:
                await ticket_repo.close_ticket_of_deleted_channel(ticket.channel_id)
                continue
            try:
                fatto = await self._chiudi_da_sistema(
                    guild,
                    channel,
                    ticket,
                    motivo=f"Chiusura di massa di {interaction.user}",
                    avviso=f"Ticket chiuso da {interaction.user.mention} (chiusura di tutti i ticket)."
                    + (f"\nMotivo: {motivo}" if motivo else "")
                    + " Questo canale verrà eliminato a breve.",
                    chiedi_voto=True,
                    chiuso_da=interaction.user.id,
                    ragione=motivo or "Chiusura di massa",
                )
            except Exception:
                # Un ticket che non si chiude (scheduler giù, transcript) non ferma gli altri.
                logger.exception("Chiusura di massa: il ticket %s non si è chiuso.", ticket.channel_id)
                falliti += 1
                continue
            if fatto:
                chiusi += 1
                if chiusi % 5 == 0:
                    # Ogni transcript richiede tempo: un messaggio ogni 5 tiene informato chi ha lanciato il comando.
                    await interaction.followup.send(await testo_per(interaction, "tickets_chiusi_finora_ticket", chiusi=chiusi), ephemeral=True)
        restanti = await ticket_repo.count_open_tickets(guild.id)
        testo = f"Chiusi {chiusi} ticket."
        if falliti:
            testo += f" {falliti} non si sono chiusi (errore nei log): restano aperti."
        if restanti:
            testo += f" Ne restano {restanti} aperti: rilancia il comando."
        await interaction.followup.send(testo, ephemeral=True)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """NF-13: chi esce dal server non può più rispondere: il suo ticket aperto si chiude."""
        for ticket in await ticket_repo.list_open_tickets_for_user(member.guild.id, member.id):
            channel = member.guild.get_channel_or_thread(ticket.channel_id)
            if channel is None:
                continue
            await self._chiudi_da_sistema(
                member.guild,
                channel,
                ticket,
                motivo="Ticket chiuso: l'utente ha lasciato il server",
                avviso=f"{member} ha lasciato il server: ticket chiuso. Questo canale verrà eliminato a breve.",
                chiedi_voto=False,
                ragione="L'utente ha lasciato il server",
            )

    # ================================================================
    # TKT-051/063/027/026 — chiusura in due passi
    # ================================================================
    @staticmethod
    async def _rinomina_con_prefisso(channel, prefisso: str | None, noti: tuple, motivo: str) -> None:
        """Prefisso davanti al nome (TKT-026). Il limite delle rinomine (2 ogni 10 minuti) non blocca nulla."""
        nuovo = opz_logic.nome_con_prefisso(channel.name, prefisso, noti)
        if nuovo == channel.name:
            return
        try:
            await rename_channel(channel, nuovo, reason=motivo)
        except RenameRateLimited:
            logger.info("Nome del ticket %s non cambiato: limite delle rinomine.", channel.id)
        except discord.HTTPException:
            logger.warning("Nome del ticket %s non cambiato.", channel.id)

    async def _stato_chiuso(self, guild: discord.Guild, channel, ticket) -> bool:
        """
        TKT-051: con la chiusura in due passi il canale resta. L'utente non lo vede più, il canale
        va nella categoria dei chiusi (TKT-027), cambia nome (TKT-026) e porta Riapri, Transcript
        ed Elimina. False se il pannello non usa i due passi. Un errore qui non rompe la chiusura.
        """
        opzioni = await _opzioni_pannello(ticket.panel_id)
        if not opzioni.chiusura_due_passi:
            return False
        aggiunti = await self._nascondi_ai_non_staff(guild, channel, ticket, opzioni)
        if opzioni.categoria_chiusi and not isinstance(channel, discord.Thread):
            categoria = guild.get_channel(opzioni.categoria_chiusi)
            if isinstance(categoria, discord.CategoryChannel) and len(categoria.channels) < opz_logic.MAX_CANALI_PER_CATEGORIA:
                try:
                    await channel.edit(category=categoria, sync_permissions=False, reason="Ticket chiuso")
                except discord.HTTPException:
                    logger.warning("Ticket %s non spostato nella categoria dei chiusi.", channel.id)
        if opzioni.prefisso_chiuso:
            await self._rinomina_con_prefisso(
                channel, opzioni.prefisso_chiuso, (opzioni.prefisso_preso, opzioni.prefisso_chiuso), "Ticket chiuso"
            )
        scadenza = (
            f" Il canale sparirà da solo tra {opzioni.elimina_dopo_ore} ore." if opzioni.elimina_dopo_ore else ""
        )
        if aggiunti:
            scadenza += " Chi era stato aggiunto non lo vede più: se riapri, aggiungilo di nuovo con /ticket add."
        try:
            await channel.send(
                f"Ticket chiuso: il canale resta, ma chi lo ha aperto non lo vede più.{scadenza}\n"
                "Lo staff può riaprirlo, avere il transcript o eliminare il canale.",
                view=vista_ticket_chiuso(ticket.id),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            logger.warning("Bottoni del ticket chiuso non inviati nel canale %s.", channel.id)
        return True

    async def _nascondi_ai_non_staff(self, guild: discord.Guild, channel, ticket, opzioni: Opzioni) -> int:
        """
        TKT-051: il ticket chiuso lo vede solo lo staff. Perdono la vista chi lo ha aperto e chi
        era stato aggiunto (utenti e ruoli fuori dallo staff). Restituisce quanti aggiunti.
        """
        if isinstance(channel, discord.Thread):
            # Thread privato: chi l'ha aperto esce dal thread (lo staff resta); il thread resta aperto per i bottoni.
            try:
                await channel.remove_user(discord.Object(id=ticket.user_id))
            except discord.HTTPException:
                logger.warning("Utente %s non tolto dal thread chiuso %s.", ticket.user_id, channel.id)
            return 0
        restano = set(await _ruoli_staff(guild.id, ticket.panel_id)) | set(opzioni.ruoli_osservatori)
        restano |= {guild.id, guild.me.id} | {r.id for r in getattr(guild.me, "roles", [])}
        aggiunti = []
        for bersaglio, ow in dict(channel.overwrites).items():
            if bersaglio.id in restano or bersaglio.id == ticket.user_id or ow.view_channel is not True:
                continue
            if isinstance(bersaglio, discord.Member) and await _membro_staff(bersaglio, guild.id, ticket.panel_id):
                continue
            aggiunti.append(bersaglio)
        utente = guild.get_member(ticket.user_id) or discord.Object(id=ticket.user_id, type=discord.Member)
        for bersaglio in (*aggiunti, utente):
            try:
                ow = channel.overwrites_for(bersaglio)
                ow.update(view_channel=False, send_messages=False)
                await channel.set_permissions(bersaglio, overwrite=ow, reason="Ticket chiuso")
            except discord.HTTPException:
                logger.warning("Accesso di %s al ticket chiuso %s non tolto.", bersaglio.id, channel.id)
        return len(aggiunti)

    async def _riapri(self, guild: discord.Guild, channel, ticket, da) -> str:
        """TKT-051: riapre un ticket chiuso. Restituisce il messaggio per chi lo ha chiesto."""
        if ticket.status != "closed":
            return "Questo ticket è già aperto."
        limite = await _limite_per_utente(guild.id)
        if await ticket_repo.count_open_tickets_for_user(guild.id, ticket.user_id) >= limite:
            return "Chi lo aveva aperto ha già il massimo di ticket aperti: riaprire questo li supererebbe."
        if not await ticket_repo.riapri(channel.id):
            return "Questo ticket è già stato riaperto."
        # Un'eliminazione già pianificata resterebbe e, a una nuova chiusura, cancellerebbe prima del tempo.
        await scheduler.cancel_for_channel(guild.id, TICKET_DELETE_ACTION_TYPE, channel.id)
        opzioni = await _opzioni_pannello(ticket.panel_id)
        utente = guild.get_member(ticket.user_id) or discord.Object(id=ticket.user_id, type=discord.Member)
        try:
            if isinstance(channel, discord.Thread):
                await channel.add_user(utente)
            else:
                ow = channel.overwrites_for(utente)
                ow.update(**opz_logic.permessi_utente(opzioni.permessi_negati))
                await channel.set_permissions(utente, overwrite=ow, reason=f"Ticket riaperto da {da}"[:512])
        except discord.HTTPException:
            logger.warning("Accesso dell'utente %s al ticket %s non ridato.", ticket.user_id, channel.id)
        if opzioni.categoria_chiusi and not isinstance(channel, discord.Thread) and channel.category_id == opzioni.categoria_chiusi:
            pannello = await ticket_form_repo.pannello_per_id(ticket.panel_id) if ticket.panel_id else None
            categoria = guild.get_channel(pannello.category_id) if pannello is not None else None
            if isinstance(categoria, discord.CategoryChannel) and len(categoria.channels) < opz_logic.MAX_CANALI_PER_CATEGORIA:
                try:
                    await channel.edit(category=categoria, sync_permissions=False, reason="Ticket riaperto")
                except discord.HTTPException:
                    logger.warning("Ticket %s non riportato nella sua categoria.", channel.id)
        if opzioni.prefisso_chiuso or opzioni.prefisso_preso:
            await self._rinomina_con_prefisso(
                channel,
                opzioni.prefisso_preso if ticket.claimed_by else None,
                (opzioni.prefisso_preso, opzioni.prefisso_chiuso),
                "Ticket riaperto",
            )
        try:
            await channel.send(f"Ticket riaperto da {da.mention}. <@{ticket.user_id}>, puoi scrivere di nuovo.")
        except discord.HTTPException:
            logger.warning("Avviso di riapertura non inviato nel ticket %s.", channel.id)
        return "Ticket riaperto."

    async def azione_ticket_chiuso(self, interaction: discord.Interaction, ticket, azione: str) -> None:
        """I tre bottoni del ticket chiuso (solo staff, già controllato da chi chiama)."""
        if azione == "t":
            await interaction.response.defer(ephemeral=True)
            try:
                file_pronti = await self._file_transcript(interaction.guild, interaction.channel, ticket)
            except discord.HTTPException:
                await interaction.followup.send(await testo_per(interaction, "tickets_non_riesco_leggere_messaggi_del_2"), ephemeral=True)
                return
            for nome_file, contenuto in file_pronti:
                await interaction.followup.send(
                    file=discord.File(io.BytesIO(contenuto), filename=nome_file), ephemeral=True
                )
        elif azione == "r":
            await interaction.response.defer(ephemeral=True)
            esito = await self._riapri(interaction.guild, interaction.channel, ticket, interaction.user)
            await interaction.followup.send(esito, ephemeral=True)
            if esito == "Ticket riaperto." and interaction.message is not None:
                try:
                    await interaction.message.edit(view=None)
                except discord.HTTPException:
                    pass
        else:
            await interaction.response.send_message(await testo_per(interaction, "tickets_elimino_il_canale"), ephemeral=True)
            try:
                await self._elimina_canale(interaction.channel.id, f"Ticket eliminato da {interaction.user}")
            except discord.HTTPException:
                logger.warning("Eliminazione del ticket chiuso %s non riuscita.", interaction.channel.id)
                await self._pianifica_eliminazione(
                    interaction, f"Ticket eliminato da {interaction.user}", RITARDO_ELIMINAZIONE_SECONDI
                )

    @comando_di_gruppo("ticket", nome="riapri", descrizione="Riapri questo ticket chiuso (se il pannello tiene il canale).")
    async def riapri(self, interaction: discord.Interaction) -> None:
        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id)
        if ticket is None or ticket.status != "closed":
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_questo_comando_funziona_solo_in"), ephemeral=True
            )
            return
        if not await _is_ticket_staff(interaction, ticket):
            await interaction.response.send_message(await testo_per(interaction, "tickets_solo_lo_staff_dei_ticket_2"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
            await self._riapri(interaction.guild, interaction.channel, ticket, interaction.user), ephemeral=True
        )

    async def handle_ticket_delete_channel(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Handler dello scheduler. Se solleva, lo scheduler riprova più tardi."""
        channel_id = payload["channel_id"]
        ticket = await ticket_repo.get_ticket_by_channel(channel_id)
        if ticket is not None and ticket.status == "open":
            return  # riaperto dopo la chiusura (TKT-051): il canale resta
        if channel_id in self._transcript_in_corso:
            # Il transcript sta ancora leggendo i messaggi: si ripassa dopo.
            await scheduler.schedule(
                guild_id,
                user_id,
                TICKET_DELETE_ACTION_TYPE,
                in_seconds(RITARDO_ELIMINAZIONE_SECONDI),
                payload,
            )
            return
        await self._elimina_canale(channel_id, payload.get("reason"))

    @comando_di_gruppo("ticket", nome="close", descrizione="Chiudi questo ticket.")
    @app_commands.describe(motivo="Perché lo chiudi (si salva col ticket)")
    async def close(
        self,
        interaction: discord.Interaction,
        motivo: app_commands.Range[str, 1, MAX_MOTIVO_CHIUSURA] | None = None,
    ) -> None:
        # Una sola lettura: con due letture il ticket poteva chiudersi in mezzo e il secondo
        # /ticket close rispondeva «non è un ticket» invece di «già chiuso».
        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id)
        if ticket is not None and ticket.status != "open":
            # Due /ticket close quasi insieme: il secondo trova il ticket già chiuso.
            await interaction.response.send_message(await testo_per(interaction, "tickets_questo_ticket_gia_stato_chiuso"), ephemeral=True)
            return
        if ticket is None:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_questo_comando_funziona_solo_dentro"), ephemeral=True
            )
            return
        opzioni = await _opzioni_pannello(ticket.panel_id)
        osservatore = bool(set(opzioni.ruoli_osservatori) & {r.id for r in getattr(interaction.user, "roles", [])})
        if (
            osservatore and interaction.user.id != ticket.user_id
            and not await _is_ticket_staff(interaction, ticket)
        ):
            # TKT-042: gli osservatori vedono e non scrivono; non chiudono il ticket degli altri.
            await interaction.response.send_message(await testo_per(interaction, "tickets_chi_osserva_il_ticket_non"), ephemeral=True)
            return
        if not opzioni.utente_chiude and interaction.user.id == ticket.user_id and not await _is_ticket_staff(interaction, ticket):
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_in_questo_pannello_ticket_li"), ephemeral=True
            )
            return
        if opzioni.conferma_chiusura:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_vuoi_davvero_chiudere_questo_ticket"), view=ConfermaChiusura(self, interaction.user.id, motivo),
                ephemeral=True,
            )
            return
        await self.esegui_close(interaction, ticket, motivo)

    async def esegui_close(self, interaction: discord.Interaction, ticket, motivo: str | None) -> None:
        """La chiusura vera di /ticket close (dopo l'eventuale conferma, TKT-054, o la richiesta accettata, TKT-055)."""
        if not await self._chiudi_e_pianifica(
            interaction.guild.id, interaction.channel.id, interaction.user.id, motivo, ticket.user_id,
            f"Ticket chiuso da {interaction.user}",
        ):
            await interaction.response.send_message(await testo_per(interaction, "tickets_questo_ticket_gia_stato_chiuso"), ephemeral=True)
            return
        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id) or ticket
        due_passi = (await _opzioni_pannello(ticket.panel_id)).chiusura_due_passi
        await interaction.response.send_message(
            "Ticket chiuso. " + (TESTO_CANALE_RESTA if due_passi else "Questo canale verrà eliminato entro un minuto.")
            + (f"\nMotivo: {motivo}" if motivo else ""),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await self._transcript_senza_bloccare(interaction.guild, interaction.channel, ticket)
        await self._stato_chiuso(interaction.guild, interaction.channel, ticket)
        await self._richiedi_voto(interaction.guild, ticket)

    @comando_di_gruppo(
        "ticket", nome="forceclose", descrizione="Chiudi immediatamente questo ticket, senza attesa."
    )
    @app_commands.describe(motivo="Perché lo chiudi (si salva col ticket)")
    async def forceclose(
        self,
        interaction: discord.Interaction,
        motivo: app_commands.Range[str, 1, MAX_MOTIVO_CHIUSURA] | None = None,
    ) -> None:
        """
        SPEC.md §13.9: a differenza di /ticket close (aperto a
        chiunque abbia accesso al canale, incluso chi ha aperto il
        ticket), questo è riservato allo staff ed elimina il canale
        SUBITO, senza attesa — pensato per i ticket da chiudere
        immediatamente (es. abuso, spam). Funziona anche su un ticket
        già chiuso il cui canale è rimasto (BUG-30).
        """
        if not await _is_ticket_staff(interaction):
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_solo_lo_staff_permesso_manage_2"),
                ephemeral=True,
            )
            return

        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id)
        if ticket is None:
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_questo_comando_funziona_solo_dentro_2"), ephemeral=True
            )
            return
        if not await _is_ticket_admin(interaction, ticket):
            # TKT-045: con dei ruoli admin, gli addetti non forzano la chiusura.
            await interaction.response.send_message(
                await testo_per(interaction, "tickets_solo_admin_dei_ticket"), ephemeral=True
            )
            return

        # Su un ticket già chiuso non cambia nulla nel database.
        appena_chiuso = await ticket_repo.close_ticket(
            interaction.channel.id, interaction.user.id, force=True, reason=motivo
        )
        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id) or ticket
        await interaction.response.send_message(
            await testo_per(interaction, "tickets_ticket_chiuso_forzatamente_da_elimino", pubblica=True, mention=interaction.user.mention),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        if appena_chiuso:
            # Su un ticket già chiuso (BUG-30) transcript e voto li ha già fatti chi lo ha chiuso.
            await self._transcript_senza_bloccare(interaction.guild, interaction.channel, ticket)
            await self._richiedi_voto(interaction.guild, ticket)

        motivo = f"Ticket forzatamente chiuso da {interaction.user}"
        try:
            await self._elimina_canale(interaction.channel.id, motivo)
        except discord.HTTPException:
            logger.warning(
                "Eliminazione del canale ticket %s non riuscita: riprovo dallo scheduler.",
                interaction.channel.id,
            )
            await self._pianifica_eliminazione(interaction, motivo, RITARDO_ELIMINAZIONE_SECONDI)

    # ================================================================
    # Canale di un ticket cancellato a mano
    # ================================================================
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """
        Se qualcuno cancella a mano il canale di un ticket aperto, il
        ticket va chiuso: altrimenti l'utente resta con "hai già un
        ticket aperto" per sempre. Dopo /ticket close o forceclose il
        ticket è già chiuso e qui non cambia nulla.
        """
        self._attivita_scritta.pop(channel.id, None)
        await ticket_automazioni_repo.togli_riserva(channel.id)  # TKT-035: un canale pronto cancellato a mano
        if await ticket_repo.close_ticket_of_deleted_channel(channel.id):
            logger.info(
                "Ticket chiuso perché il suo canale %s è stato cancellato a mano.", channel.id
            )

    @commands.Cog.listener()
    async def on_raw_thread_delete(self, payload: discord.RawThreadDeleteEvent) -> None:
        """TKT-031: per i thread Discord non manda on_guild_channel_delete; un ticket a thread cancellato si chiude."""
        self._attivita_scritta.pop(payload.thread_id, None)
        if await ticket_repo.close_ticket_of_deleted_channel(payload.thread_id):
            logger.info("Ticket chiuso perché il suo thread %s è stato cancellato.", payload.thread_id)

    # ================================================================
    # SPEC.md §13.12 — traccia la prima risposta nel canale ticket
    # ================================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return

        ticket = await ticket_repo.get_ticket_by_channel(message.channel.id)
        if ticket is None or ticket.status != "open":
            return

        # NF-13: l'ultimo messaggio di una persona tiene vivo il ticket (chiusura automatica).
        if not message.author.bot and ticket.panel_id is not None:
            await self._segna_attivita(message.channel.id)
            await self._segna_chi_scrive(message.channel.id, message.author.id == ticket.user_id)

        # TKT-055: l'utente che scrive ha risposto alla richiesta di chiusura: il timer non chiude più.
        if ticket.chiusura_richiesta_at is not None and message.author.id == ticket.user_id and not message.author.bot:
            await ticket_repo.annulla_richiesta_chiusura(message.channel.id)

        # #139: risposta standard e sollecito (cog a parte, senza AI).
        if message.author.id == ticket.user_id and not message.author.bot:
            risposte = self._cog_risposte()
            if risposte is not None:
                await risposte.su_messaggio_dell_utente(message, ticket)

        if (
            ticket.claimed_by is None and ticket.panel_id is not None
            and not message.author.bot and message.author.id != ticket.user_id
        ):
            await self._assegna_al_primo(message, ticket)

        if ticket.first_response_at is not None:
            return

        if not is_first_response(message.author.id, ticket.user_id, message.author.bot):
            return

        await ticket_repo.record_first_response(message.channel.id, datetime.now(timezone.utc))

    @commands.Cog.listener()
    async def on_thread_update(self, prima: discord.Thread, dopo: discord.Thread) -> None:
        """TKT-031: Discord archivia da solo un thread fermo; se il ticket è aperto il thread si riapre."""
        if not dopo.archived or prima.archived or dopo.locked:
            return
        ticket = await ticket_repo.get_ticket_by_channel(dopo.id)
        if ticket is None or ticket.status != "open" or not ticket.e_thread:
            return
        try:
            await dopo.edit(archived=False, reason="Ticket ancora aperto")
        except discord.HTTPException:
            logger.warning("Thread del ticket %s non riaperto dopo l'archiviazione.", dopo.id)

    async def _assegna_al_primo(self, message: discord.Message, ticket) -> None:
        """TKT-052: il primo dello staff che scrive prende in carico il ticket (vince uno solo)."""
        opzioni = await _opzioni_pannello(ticket.panel_id)
        if not opzioni.assegna_auto or not await _membro_staff(message.author, message.guild.id, ticket.panel_id):
            return
        if not await ticket_repo.claim_ticket(message.channel.id, message.author.id, solo_se_libero=True):
            return
        testo = await self._dopo_presa(message.guild, message.channel, ticket, message.author)
        try:
            await message.channel.send(testo, view=vista_inizio(message.channel))
        except discord.HTTPException:
            logger.warning("Avviso di presa automatica non inviato nel ticket %s.", message.channel.id)

    def _cog_risposte(self):
        """Il cog delle risposte standard (#139), se caricato."""
        return self.bot.get_cog("RisposteStandardCog") if self.bot is not None else None

    async def _segna_chi_scrive(self, channel_id: int, da_utente: bool) -> None:
        """TKT-029 / TKT-064: ultimo messaggio dell'utente o dello staff, al più una scrittura al minuto."""
        adesso = time.monotonic()
        chiave = (channel_id, da_utente)
        ultima = self._chi_scrive.get(chiave)
        if ultima is not None and adesso - ultima < _ATTIVITA_OGNI_SECONDI:
            return
        if len(self._chi_scrive) >= _ATTIVITA_MAX_VOCI:
            self._chi_scrive = {c: t for c, t in self._chi_scrive.items() if adesso - t < _ATTIVITA_OGNI_SECONDI}
        self._chi_scrive[chiave] = adesso
        await ticket_automazioni_repo.segna_scritto(channel_id, da_utente, datetime.now(timezone.utc))

    async def _segna_attivita(self, channel_id: int) -> None:
        """Scrive l'attività nel database al più una volta al minuto per canale."""
        adesso = time.monotonic()
        ultima = self._attivita_scritta.get(channel_id)
        if ultima is not None and adesso - ultima < _ATTIVITA_OGNI_SECONDI:
            return
        if len(self._attivita_scritta) >= _ATTIVITA_MAX_VOCI:
            # Tiene solo i canali scritti da meno di un minuto: gli altri verrebbero riscritti comunque.
            self._attivita_scritta = {
                c: t for c, t in self._attivita_scritta.items() if adesso - t < _ATTIVITA_OGNI_SECONDI
            }
        self._attivita_scritta[channel_id] = adesso
        await ticket_repo.touch_activity(channel_id, datetime.now(timezone.utc))


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_TICKETS,
            display_name="Ticket System",
            category="tickets",
            description="Pannello di apertura ticket, claim, gestione, priorità.",
            premium_capable=False,
        )
    )
    cog = TicketsCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(TICKET_DELETE_ACTION_TYPE, cog.handle_ticket_delete_channel)
    scheduler.register_handler(TICKET_AUTOCLOSE_ACTION_TYPE, cog.handle_ticket_autoclose)
    scheduler.register_handler(TICKET_RICHIESTA_CHIUSURA_ACTION_TYPE, cog.handle_richiesta_chiusura)

    # Registrazione della view persistente: DEVE avvenire ad ogni
    # avvio del bot, non solo quando il pannello viene pubblicato per
    # la prima volta — è quello che permette ai bottoni dei pannelli
    # già esistenti nei server (pubblicati prima di un riavvio) di
    # continuare a funzionare.
    bot.add_view(TicketPanelView())
    bot.add_dynamic_items(BottonePannello, BottoneVoto, BottoneRichiestaChiusura, BottoneChiuso, MenuGestisci, BottoneEntra)
