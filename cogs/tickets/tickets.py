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
fino a 5 con /gestione ticket limite, impostazione `ticket_max_per_utente`;
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
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.repositories.ticket_form_repo import (
    DomandaModulo,
    PannelloGiaEsistente,
    PannelloTicket,
    TroppeDomande,
    TroppiPannelli,
    ticket_form_repo,
)
from core import ticket_form_logic as form
from core import ticket_opzioni_logic as opz_logic
from core.repositories.ticket_opzioni_repo import ticket_opzioni_repo
from core.ticket_opzioni_logic import Opzioni
from core.repositories.ticket_repo import (
    VALID_PRIORITIES,
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
    merge_support_role_ids,
    split_text_by_size,
    truncate_label,
)
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

# Sotto-gruppo di /gestione con i comandi degli admin.
GESTIONE_TICKET = ("ticket", "Ticket: configurazione, pannello, categorie, ruoli di supporto, statistiche")
# Sotto-gruppo di /admin con i ticket avanzati (NF-13, NF-33, #139): /gestione ha poco spazio (8000 caratteri per gruppo).
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

PRIORITY_EMOJI = {"normal": "🟢", "high": "🟠", "urgent": "🔴"}

# TKT-056: motivo di chiusura salvato col ticket (compare anche nel transcript).
MAX_MOTIVO_CHIUSURA = 500
# TKT-058: quanti ticket chiude in una volta /admin ticket chiudi-tutti (ognuno ha il suo transcript).
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
    """NF-13: quanti ticket aperti può avere un utente (default 1, /gestione ticket limite)."""
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
            "Sto già aprendo il tuo ticket, un attimo.", ephemeral=True
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
    if not per_conto:
        # TKT-017…024 (per lo staff che apre a nome di un utente decide lo staff).
        esito = await esito_apertura(guild, utente, panel_id)
        if not esito.permesso:
            await interaction.followup.send(esito.messaggio[:2000], ephemeral=True)
            return None
        fuori_orario = esito.fuori_orario
    opzioni = await _opzioni_pannello(panel_id)

    limite = await _limite_per_utente(guild.id)
    already_open = await ticket_repo.count_open_tickets_for_user(guild.id, utente.id)
    if already_open >= limite:
        await interaction.followup.send(
            _messaggio_limite(limite) if not per_conto else f"{utente.mention} ha già il massimo di ticket aperti.",
            ephemeral=True,
        )
        return None

    category = _categoria_con_posto(guild, category, opzioni)
    if category is None:
        await interaction.followup.send(
            "Le categorie dei ticket sono piene (50 canali ciascuna): avvisa lo staff.", ephemeral=True
        )
        return None
    reperibili = [
        m for m in (guild.get_member(uid) for uid in await ticket_opzioni_repo.reperibili(guild.id))
        if m is not None and m.id != utente.id
    ]
    overwrites = _overwrites_del_ticket(
        guild, utente, opzioni, await _ruoli_staff(guild.id, panel_id), reperibili
    )

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
        channel = await category.create_text_channel(
            name=nome,
            overwrites=overwrites,
            reason=f"Ticket aperto da {interaction.user}"[:512],
        )
    except discord.Forbidden:
        await interaction.followup.send(
            "Non ho i permessi per creare un canale in quella categoria.",
            ephemeral=True,
        )
        return None
    except discord.HTTPException:
        await interaction.followup.send(
            "Impossibile creare il canale del ticket (la categoria "
            "potrebbe aver raggiunto il limite di 50 canali).",
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
        )
    except TicketAlreadyOpenError:
        # Un altro ticket dello stesso utente è nato nel frattempo: il
        # canale appena creato non deve restare orfano.
        try:
            await channel.delete(reason="Ticket doppio: l'utente ne ha già uno aperto")
        except discord.HTTPException:
            logger.warning("Canale del ticket doppio %s non eliminato.", channel.id)
        await interaction.followup.send(_messaggio_limite(limite), ephemeral=True)
        return None

    await _dai_ruoli_durante(guild, utente, channel.id, opzioni)

    if panel is not None and panel.welcome_text:
        descrizione = panel.welcome_text.replace("{utente}", utente.mention)[:4000]
    else:
        descrizione = (
            f"Ciao {utente.mention}, grazie per averci "
            f"contattato. Descrivi il tuo problema e lo staff ti "
            f"risponderà a breve."
        )
    embed = discord.Embed(
        title=f"Ticket #{ticket_number:04d}",
        description=descrizione,
        color=discord.Color.blurple(),
    )
    if category_label is not None:
        embed.add_field(name="Categoria", value=truncate_label(category_label))
    if per_conto:
        embed.add_field(name="Aperto dallo staff", value=interaction.user.mention)
    if motivo:
        embed.add_field(name="Motivo", value=motivo[:1024], inline=False)
    if citato is not None:
        testo_citato = (citato.content or "(senza testo)")[:900]
        embed.add_field(
            name=f"Messaggio di {citato.author}"[:256],
            value=f"{testo_citato}\n[Vai al messaggio]({citato.jump_url})"[:1024],
            inline=False,
        )
    if fuori_orario:
        embed.add_field(
            name="Fuori orario",
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
        primo = await channel.send(content=utente.mention, embed=embed)
        if opzioni.fissa_primo:
            await primo.pin(reason="Primo messaggio del ticket")
    except discord.HTTPException:
        logger.warning("Messaggio di benvenuto non inviato (o non fissato) nel ticket %s.", channel.id)

    await _avvisi_di_apertura(channel, guild, utente, opzioni, reperibili, ticket_number)

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
        f"Ticket creato: {channel.mention}", ephemeral=True
    )
    return channel


def _category_options(categorie, with_emoji: bool = True) -> list[discord.SelectOption]:
    """
    Le opzioni del menu delle categorie, sempre dentro i limiti di
    Discord (LIM-6) anche con dati salvati prima dei controlli di
    /gestione ticket categoria-add: al massimo 25, etichetta tagliata a 100,
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
                "Questa categoria non è più disponibile.", ephemeral=True
            )
            return

        category_channel = self._guild.get_channel(scelta.category_id)
        if not isinstance(category_channel, discord.CategoryChannel):
            await interaction.response.send_message(
                "La categoria Discord collegata non esiste più. "
                "Un amministratore deve riconfigurarla.",
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
                "Il sistema di ticket non è attivo su questo server.",
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
                "Il sistema di ticket non è ancora stato configurato "
                "(manca la categoria). Un amministratore deve usare "
                "/gestione ticket setup.",
                ephemeral=True,
            )
            return

        category = guild.get_channel(category_id)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "La categoria configurata per i ticket non esiste più. "
                "Un amministratore deve riconfigurarla con /gestione ticket setup.",
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
                "Questo pannello non esiste più.", ephemeral=True
            )
            return
        category = guild.get_channel(panel.category_id)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "La categoria Discord del pannello non esiste più. Un amministratore deve riconfigurarla.",
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
            "Il sistema di ticket non è attivo su questo server.", ephemeral=True
        )
        return
    panel = await ticket_form_repo.pannello_per_id(panel_id)
    if panel is None or panel.guild_id != guild.id:
        await interaction.response.send_message(
            "Questo pannello non è più disponibile.", ephemeral=True
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
            "La categoria Discord del pannello non esiste più. Un amministratore deve riconfigurarla.",
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
                "Hai già votato questo ticket, oppure non è tuo.", ephemeral=True
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
            await interaction.response.send_message("Questa richiesta non vale più.", ephemeral=True)
            return
        if interaction.user.id != ticket.user_id:
            await interaction.response.send_message("Risponde solo chi ha aperto il ticket.", ephemeral=True)
            return
        if self.scelta == "r":
            await ticket_repo.annulla_richiesta_chiusura(interaction.channel.id)
            await interaction.response.edit_message(
                content="L'utente ha ancora bisogno di aiuto: il ticket resta aperto.", view=None
            )
            return
        cog = interaction.client.get_cog("TicketsCog")
        if cog is None:
            await interaction.response.send_message("I ticket non sono disponibili ora: riprova tra poco.", ephemeral=True)
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
            await interaction.response.edit_message(content="Questo ticket è già stato chiuso.", view=None)
            return
        self.stop()
        await self._cog.esegui_close(interaction, ticket, self._motivo)


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

    @comando_di_gruppo(
        "gestione",
        nome="setup",
        descrizione="Configura la categoria (e opzionalmente il ruolo di supporto) per i ticket.",
        sottogruppo=GESTIONE_TICKET,
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
                "Questo comando è disponibile solo dentro un server.",
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
        "gestione",
        nome="limite",
        descrizione="Quanti ticket aperti alla volta può avere ogni utente (predefinito 1).",
        sottogruppo=GESTIONE_TICKET,
    )
    @app_commands.describe(massimo="Da 1 a 5 ticket aperti per utente")
    async def ticket_limite(
        self,
        interaction: discord.Interaction,
        massimo: app_commands.Range[int, 1, LIMITE_PER_UTENTE_MAX],
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        await db.set_guild_setting(interaction.guild.id, SETTING_MAX_PER_UTENTE, int(massimo))
        await interaction.response.send_message(
            f"Ogni utente potrà avere al massimo **{massimo}** ticket aperti alla volta.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "gestione",
        nome="panel",
        descrizione="Pubblica il pannello per l'apertura dei ticket in questo canale.",
        sottogruppo=GESTIONE_TICKET,
    )
    async def ticket_panel(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_TICKETS):
            return

        embed = discord.Embed(
            title="🎫 Supporto",
            description="Premi il bottone qui sotto per aprire un ticket privato con lo staff.",
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
                f"Nessun pannello chiamato **{nome.strip()[:100]}**. Vedi `/admin ticket pannello-lista`.",
                ephemeral=True,
            )
        return panel

    @comando_di_gruppo(
        "admin",
        nome="pannello-crea",
        descrizione="Crea un pannello di ticket.",
        sottogruppo=ADMIN_TICKET,
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
                "Quella non sembra un'emoji valida: usa un'emoji normale o una personalizzata del server.",
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
                f"Esiste già un pannello chiamato **{nome_pulito}**.", ephemeral=True
            )
            return
        except TroppiPannelli:
            await interaction.response.send_message(
                f"Un server può avere al massimo {form.MAX_PANNELLI_PER_SERVER} pannelli.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"Pannello **{panel.name}** creato. Aggiungi le domande con `/admin ticket modulo-aggiungi` "
            "e pubblicalo con `/admin ticket pannello-pubblica`.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "admin",
        nome="pannello-rimuovi",
        descrizione="Elimina un pannello e il suo modulo.",
        sottogruppo=ADMIN_TICKET,
    )
    @app_commands.describe(nome="Il pannello da eliminare")
    @app_commands.autocomplete(nome=_completa_pannelli)
    async def pannello_rimuovi(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, form.MAX_NOME_PANNELLO]
    ) -> None:
        panel = await self._pannello_o_risposta(interaction, nome)
        if panel is None:
            return
        await ticket_form_repo.rimuovi_pannello(interaction.guild.id, panel.name)
        await interaction.response.send_message(
            f"Pannello **{panel.name}** eliminato, con il suo modulo e le risposte standard "
            "imparate da questo pannello. I messaggi già pubblicati mostreranno "
            "«pannello non più disponibile».",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "admin",
        nome="pannello-lista",
        descrizione="Elenca i pannelli di ticket del server.",
        sottogruppo=ADMIN_TICKET,
    )
    async def pannello_lista(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        pannelli = await ticket_form_repo.elenca_pannelli(interaction.guild.id)
        if not pannelli:
            await interaction.response.send_message(
                "Nessun pannello. Creane uno con `/admin ticket pannello-crea`.", ephemeral=True
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
        "admin",
        nome="pannello-pubblica",
        descrizione="Pubblica qui i bottoni di uno o più pannelli.",
        sottogruppo=ADMIN_TICKET,
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
                await interaction.response.send_message(f"Nessun pannello chiamato **{nome[:100]}**.", ephemeral=True)
                return
            trovati.append(panel)
        if not trovati:
            await interaction.response.send_message("Indica almeno un pannello.", ephemeral=True)
            return
        try:
            vista = vista_pannelli(trovati)
        except form.ErroreConfigurazione as errore:
            await interaction.response.send_message(str(errore), ephemeral=True)
            return
        embed = discord.Embed(title=titolo, description=testo, color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, view=vista)

    @comando_di_gruppo(
        "admin",
        nome="modulo-aggiungi",
        descrizione="Aggiungi una domanda al modulo (max 5).",
        sottogruppo=ADMIN_TICKET,
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
                f"Il modulo ha già {form.MAX_DOMANDE} domande: è il massimo di Discord. "
                "Togline una con `/admin ticket modulo-rimuovi`.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"Domanda {nuova.position} aggiunta al pannello **{panel.name}**.", ephemeral=True
        )

    @comando_di_gruppo(
        "admin",
        nome="modulo-rimuovi",
        descrizione="Togli una domanda dal modulo.",
        sottogruppo=ADMIN_TICKET,
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
            await interaction.response.send_message(f"Domanda {numero} tolta.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Non c'è una domanda {numero}.", ephemeral=True)

    @comando_di_gruppo(
        "admin",
        nome="modulo-mostra",
        descrizione="Mostra le domande del modulo di un pannello.",
        sottogruppo=ADMIN_TICKET,
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
                f"Il pannello **{panel.name}** non ha domande: il ticket si apre subito.", ephemeral=True
            )
            return
        righe = [
            f"{d.position}. {d.label} ({'obbligatoria' if d.required else 'facoltativa'}"
            f"{', lunga' if d.long_answer else ''})"
            for d in domande
        ]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    @comando_di_gruppo(
        "admin",
        nome="chiusura-auto",
        descrizione="Chiudi i ticket fermi da N minuti (0 = spenta).",
        sottogruppo=ADMIN_TICKET,
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
        "admin",
        nome="voto",
        descrizione="Voto a stelle in DM alla chiusura.",
        sottogruppo=ADMIN_TICKET,
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
            f"Voto {'acceso' if attivo else 'spento'} per **{panel.name}**.", ephemeral=True
        )

    # ================================================================
    # SPEC.md §13.2 — categorie ticket configurabili
    # ================================================================
    @comando_di_gruppo(
        "gestione",
        nome="categoria-add",
        descrizione="Aggiungi (o aggiorna) una categoria di ticket.",
        sottogruppo=GESTIONE_TICKET,
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
                "Il nome della categoria non può essere vuoto.", ephemeral=True
            )
            return
        if emoji is not None and not looks_like_emoji(emoji.strip()):
            await interaction.response.send_message(
                "Quella non sembra un'emoji. Usa un'emoji standard (es. 🎫) "
                "oppure un'emoji personalizzata di questo server.",
                ephemeral=True,
            )
            return

        # Un menu a tendina tiene 25 opzioni (LIM-6). Aggiornare una
        # categoria che esiste già non ne aggiunge una.
        esistenti = await ticket_repo.list_categories(interaction.guild.id)
        if len(esistenti) >= MAX_TICKET_CATEGORIES and label not in {c.label for c in esistenti}:
            await interaction.response.send_message(
                f"Hai già {MAX_TICKET_CATEGORIES} categorie, il massimo che un menu di "
                "Discord può mostrare. Rimuovine una con /gestione ticket categoria-remove.",
                ephemeral=True,
            )
            return

        emoji = emoji.strip() if emoji is not None else None
        await ticket_repo.add_category(interaction.guild.id, label, category.id, emoji)
        await interaction.response.send_message(
            f"Categoria **{label}** impostata su **{category.name}**.", ephemeral=True
        )

    @comando_di_gruppo(
        "gestione",
        nome="categoria-remove",
        descrizione="Rimuovi una categoria di ticket.",
        sottogruppo=GESTIONE_TICKET,
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
            await interaction.response.send_message(f"Categoria **{label}** rimossa.", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"Nessuna categoria chiamata **{label}**.", ephemeral=True
            )

    @comando_di_gruppo(
        "gestione",
        nome="categoria-list",
        descrizione="Elenca le categorie di ticket configurate.",
        sottogruppo=GESTIONE_TICKET,
    )
    async def ticket_category_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        categorie = await ticket_repo.list_categories(interaction.guild.id)
        if not categorie:
            await interaction.response.send_message(
                "Nessuna categoria configurata: il pannello mostra il bottone unico.",
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
            title="Categorie dei ticket",
            description="\n".join(mostrate),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ================================================================
    # SPEC.md §13.13 — ruoli di supporto multipli
    # ================================================================
    @comando_di_gruppo(
        "gestione",
        nome="ruolo-add",
        descrizione="Aggiungi un ruolo di supporto.",
        sottogruppo=GESTIONE_TICKET,
    )
    @app_commands.describe(role="Il ruolo da aggiungere")
    async def ticket_support_role_add(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if interaction.guild is None:
            return
        attuali = await db.get_guild_setting(interaction.guild.id, SETTING_SUPPORT_ROLES, default=[])
        if role.id not in attuali:
            attuali.append(role.id)
            await db.set_guild_setting(interaction.guild.id, SETTING_SUPPORT_ROLES, attuali)
        await interaction.response.send_message(
            f"{role.mention} aggiunto ai ruoli di supporto.", ephemeral=True
        )

    @comando_di_gruppo(
        "gestione",
        nome="ruolo-remove",
        descrizione="Rimuovi un ruolo di supporto.",
        sottogruppo=GESTIONE_TICKET,
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

        # Il ruolo può essere anche quello "storico" impostato con
        # /gestione ticket setup: va tolto pure da lì, altrimenti continua a
        # vedere i ticket. La chiave si toglie del tutto (un `null`
        # verrebbe poi rifiutato da /admin config import).
        if await db.get_guild_setting(guild_id, SETTING_SUPPORT_ROLE) == role.id:
            await db.remove_guild_setting(guild_id, SETTING_SUPPORT_ROLE, interaction.user.id)
            rimosso = True

        if not rimosso:
            await interaction.response.send_message(
                f"{role.mention} non è tra i ruoli di supporto.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"{role.mention} rimosso dai ruoli di supporto. I ticket già aperti "
            "restano visibili al ruolo finché non vengono chiusi.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "gestione",
        nome="ruolo-list",
        descrizione="Elenca i ruoli di supporto configurati.",
        sottogruppo=GESTIONE_TICKET,
    )
    async def ticket_support_role_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        ruoli_id = await _support_role_ids(interaction.guild.id)
        if not ruoli_id:
            await interaction.response.send_message("Nessun ruolo di supporto configurato.", ephemeral=True)
            return
        righe = [f"<@&{rid}>" for rid in ruoli_id]
        await interaction.response.send_message(", ".join(righe), ephemeral=True)

    # ================================================================
    # SPEC.md §13.12 — statistiche
    # ================================================================
    @comando_di_gruppo(
        "gestione",
        nome="stats",
        descrizione="Statistiche del sistema di ticket.",
        sottogruppo=GESTIONE_TICKET,
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
                title=f"Statistiche ticket — {operator.display_name}",
                color=discord.Color.blurple(),
            )
            embed.add_field(name="Presi in carico", value=str(stats.claimed_count))
            embed.add_field(name="Chiusi", value=str(stats.closed_count))
            embed.add_field(
                name="Tempo medio di prima risposta",
                value=format_duration_seconds(stats.avg_response_seconds),
            )
        else:
            stats = await ticket_repo.get_guild_stats(interaction.guild.id)
            embed = discord.Embed(title="Statistiche ticket del server", color=discord.Color.blurple())
            embed.add_field(name="Totali", value=str(stats.total_count))
            embed.add_field(name="Aperti", value=str(stats.open_count))
            embed.add_field(name="Chiusi", value=str(stats.closed_count))
            embed.add_field(
                name="Tempo medio di prima risposta",
                value=format_duration_seconds(stats.avg_response_seconds),
            )
            media, voti = await ticket_repo.get_rating_summary(interaction.guild.id)
            embed.add_field(name="Voto medio", value=form.Media(media, voti).testo())

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _get_ticket_or_reply(self, interaction: discord.Interaction):
        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id)
        if ticket is None or ticket.status != "open":
            await interaction.response.send_message(
                "Questo comando funziona solo dentro un canale ticket aperto.",
                ephemeral=True,
            )
            return None
        return ticket

    async def _get_ticket_for_staff_or_reply(self, interaction: discord.Interaction):
        """Come _get_ticket_or_reply, ma solo per lo staff dei ticket (anche la squadra del pannello, TKT-044)."""
        if not await _is_ticket_staff(interaction, await ticket_repo.get_ticket_by_channel(interaction.channel.id)):
            await interaction.response.send_message(
                "Solo lo staff (permesso Manage Server o un ruolo di "
                "supporto configurato) può usare questo comando.",
                ephemeral=True,
            )
            return None
        return await self._get_ticket_or_reply(interaction)

    @comando_di_gruppo("ticket", nome="claim", descrizione="Prendi in carico questo ticket.")
    async def claim(self, interaction: discord.Interaction) -> None:
        ticket = await self._get_ticket_for_staff_or_reply(interaction)
        if ticket is None:
            return

        await interaction.response.defer()
        await ticket_repo.claim_ticket(interaction.channel.id, interaction.user.id)
        testo = await self._dopo_presa(interaction.guild, interaction.channel, ticket, interaction.user)
        await interaction.followup.send(testo, view=vista_inizio(interaction.channel))

    async def _dopo_presa(self, guild: discord.Guild, channel, ticket, staff) -> str:
        """TKT-028 categoria dei presi, TKT-050 esclusiva, TKT-053 testo. Restituisce il messaggio da mostrare."""
        opzioni = await _opzioni_pannello(ticket.panel_id)
        if opzioni.categoria_presi:
            categoria = guild.get_channel(opzioni.categoria_presi)
            if isinstance(categoria, discord.CategoryChannel) and len(categoria.channels) < opz_logic.MAX_CANALI_PER_CATEGORIA:
                try:
                    await channel.edit(category=categoria, sync_permissions=False, reason="Ticket preso in carico")
                except discord.HTTPException:
                    logger.warning("Ticket %s non spostato nella categoria dei presi.", channel.id)
        if opzioni.claim_esclusivo != "no":
            await self._permessi_staff(guild, channel, ticket.panel_id, esclusiva=opzioni.claim_esclusivo, titolare=staff)
        if opzioni.testo_presa:
            return opz_logic.riempi(
                opzioni.testo_presa, utente=f"<@{ticket.user_id}>", server=guild.name,
                numero=ticket.ticket_number or 0, staff=staff.mention,
            )
        return f"Ticket preso in carico da {staff.mention}."

    async def _permessi_staff(self, guild: discord.Guild, channel, panel_id, *, esclusiva: str, titolare=None) -> None:
        """
        TKT-050: con la presa esclusiva i ruoli dello staff non scrivono ("scrivere") o non vedono
        ("vedere"); chi ha il ticket scrive sempre. esclusiva="no" rimette i ruoli come all'apertura.
        Si cambia un permesso solo: overwrites_for + update + overwrite=.
        """
        for role_id in await _ruoli_staff(guild.id, panel_id):
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
            await interaction.response.send_message("Scegli un utente oppure un ruolo.", ephemeral=True)
            return None
        bersaglio = member or ruolo
        if ruolo is not None and ruolo.id == interaction.guild.id:
            await interaction.response.send_message(
                "@everyone non si può aggiungere o togliere: aprirebbe il ticket a tutti.", ephemeral=True
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
            await interaction.channel.set_permissions(
                bersaglio, view_channel=True, send_messages=True, read_message_history=True
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "Non sono riuscito ad aggiungere il destinatario: controlla i miei permessi sul canale.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"{bersaglio.mention} aggiunto al ticket.", allowed_mentions=discord.AllowedMentions.none()
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
                "Questo ruolo è dello staff dei ticket o del bot: toglierlo bloccherebbe chi deve rispondere.",
                ephemeral=True,
            )
            return

        try:
            await interaction.channel.set_permissions(bersaglio, overwrite=None)
        except discord.HTTPException:
            await interaction.response.send_message(
                "Non sono riuscito a rimuovere il destinatario: controlla i miei permessi sul canale.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"{bersaglio.mention} rimosso dal ticket.", allowed_mentions=discord.AllowedMentions.none()
        )

    @comando_di_gruppo("ticket", nome="rilascia", descrizione="Lascia la presa in carico di questo ticket.")
    async def rilascia(self, interaction: discord.Interaction) -> None:
        ticket = await self._get_ticket_for_staff_or_reply(interaction)
        if ticket is None:
            return
        if ticket.claimed_by is None:
            await interaction.response.send_message("Nessuno ha preso in carico questo ticket.", ephemeral=True)
            return
        if ticket.claimed_by != interaction.user.id and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Solo chi lo ha preso in carico (o chi ha Manage Server) può rilasciarlo.", ephemeral=True
            )
            return
        await interaction.response.defer()
        await ticket_repo.release_ticket(interaction.channel.id)
        opzioni = await _opzioni_pannello(ticket.panel_id)
        if opzioni.claim_esclusivo != "no":
            await self._permessi_staff(interaction.guild, interaction.channel, ticket.panel_id, esclusiva="no")
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
                f"{collega.mention} non fa parte dello staff dei ticket.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        await interaction.response.defer()
        await ticket_repo.claim_ticket(interaction.channel.id, collega.id)
        testo = await self._dopo_presa(interaction.guild, interaction.channel, ticket, collega)
        await interaction.followup.send(f"Ticket passato a {collega.mention}.\n{testo}"[:2000])

    @comando_di_gruppo("ticket", nome="note", descrizione="Thread privato dello staff per parlare del ticket.")
    async def note(self, interaction: discord.Interaction) -> None:
        """TKT-034: un thread privato attaccato al ticket; l'utente non lo vede."""
        ticket = await self._get_ticket_for_staff_or_reply(interaction)
        if ticket is None:
            return
        await interaction.response.defer(ephemeral=True)
        thread = interaction.guild.get_thread(ticket.note_thread_id) if ticket.note_thread_id else None
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
                    "Non riesco a creare il thread: mi serve il permesso «Crea thread privati».", ephemeral=True
                )
                return
            await ticket_repo.imposta_note_thread(interaction.channel.id, thread.id)
        try:
            await thread.add_user(interaction.user)
        except discord.HTTPException:
            logger.warning("Staff %s non aggiunto al thread delle note %s.", interaction.user.id, thread.id)
        await interaction.followup.send(f"Note dello staff: {thread.mention}", ephemeral=True)

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
            await interaction.followup.send("Questo ticket non è più aperto.", ephemeral=True)
            return
        await scheduler.schedule(
            interaction.guild.id, ticket.user_id, TICKET_RICHIESTA_CHIUSURA_ACTION_TYPE, in_seconds(ore * 3600),
            {"channel_id": interaction.channel.id, "richiesta": richiesta.isoformat()},
        )
        vista = BaseView(timeout=None)
        vista.add_item(BottoneRichiestaChiusura(ticket.id, "a"))
        vista.add_item(BottoneRichiestaChiusura(ticket.id, "r"))
        await interaction.followup.send(
            f"<@{ticket.user_id}>, {interaction.user.mention} chiede se il tuo problema è risolto. "
            f"Se non rispondi entro {ore} ore il ticket si chiude da solo.",
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
            testo = await self._build_transcript_text(interaction.channel, ticket)
        except discord.HTTPException:
            await interaction.followup.send(
                "Non riesco a leggere i messaggi del canale: controlla i miei permessi.", ephemeral=True
            )
            return
        for nome_file, contenuto in self._transcript_files(testo, ticket.ticket_number):
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
                "Non sono riuscito a rinominare il canale: controlla i miei "
                "permessi e che il nome sia valido.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Ticket rinominato in **{name}**.",
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
        async for messaggio in channel.history(limit=None, oldest_first=True):
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

    async def _deliver_transcript(
        self, guild: discord.Guild, channel: discord.TextChannel, ticket, *, dm: bool = True
    ) -> None:
        """SPEC.md §13.11: invio nel canale log configurato + DM all'utente (se il pannello lo vuole, TKT-075)."""
        try:
            testo = await self._build_transcript_text(channel, ticket)
        except discord.HTTPException:
            logger.warning("Impossibile leggere la history del ticket %s per il transcript", channel.id)
            return

        file_del_transcript = self._transcript_files(testo, ticket.ticket_number)

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
        if not await ticket_repo.close_ticket(channel_id, chiuso_da, reason=ragione):
            return False
        try:
            await self._pianifica_eliminazione_canale(
                guild_id, user_id, channel_id, motivo_log, RITARDO_ELIMINAZIONE_SECONDI
            )
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
    ) -> bool:
        """
        Chiusura fatta dal bot (inattività, utente uscito) o per conto dello staff (chiusura di
        massa): stesso ordine di /ticket close. `ragione` è il motivo salvato col ticket.
        """
        if not await self._chiudi_e_pianifica(
            guild.id, channel.id, chiuso_da or guild.me.id, ragione, ticket.user_id, motivo
        ):
            return False
        ticket = await ticket_repo.get_ticket_by_channel(channel.id) or ticket
        try:
            await channel.send(avviso, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            logger.warning("Avviso di chiusura non inviato nel ticket %s.", channel.id)
        await self._transcript_senza_bloccare(guild, channel, ticket)
        if chiedi_voto:
            await self._richiedi_voto(guild, ticket)
        return True

    @comando_di_gruppo(
        "admin",
        nome="chiudi-tutti",
        descrizione="Chiudi i ticket aperti (fino a 25 alla volta).",
        sottogruppo=ADMIN_TICKET,
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
            channel = guild.get_channel(ticket.channel_id)
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
                    await interaction.followup.send(f"Chiusi finora {chiusi} ticket...", ephemeral=True)
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
            channel = member.guild.get_channel(ticket.channel_id)
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

    async def handle_ticket_delete_channel(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Handler dello scheduler. Se solleva, lo scheduler riprova più tardi."""
        channel_id = payload["channel_id"]
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
        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id)
        if ticket is not None and ticket.status != "open":
            # Due /ticket close quasi insieme: il secondo trova il ticket già chiuso.
            await interaction.response.send_message("Questo ticket è già stato chiuso.", ephemeral=True)
            return
        ticket = await self._get_ticket_or_reply(interaction)
        if ticket is None:
            return
        opzioni = await _opzioni_pannello(ticket.panel_id)
        if not opzioni.utente_chiude and interaction.user.id == ticket.user_id and not await _is_ticket_staff(interaction, ticket):
            await interaction.response.send_message(
                "In questo pannello i ticket li chiude lo staff: scrivi qui se hai finito.", ephemeral=True
            )
            return
        if opzioni.conferma_chiusura:
            await interaction.response.send_message(
                "Vuoi davvero chiudere questo ticket?", view=ConfermaChiusura(self, interaction.user.id, motivo),
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
            await interaction.response.send_message("Questo ticket è già stato chiuso.", ephemeral=True)
            return
        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id) or ticket
        await interaction.response.send_message(
            "Ticket chiuso. Questo canale verrà eliminato entro un minuto."
            + (f"\nMotivo: {motivo}" if motivo else ""),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await self._transcript_senza_bloccare(interaction.guild, interaction.channel, ticket)
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
                "Solo lo staff (permesso Manage Server o un ruolo di "
                "supporto configurato) può forzare la chiusura.",
                ephemeral=True,
            )
            return

        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id)
        if ticket is None:
            await interaction.response.send_message(
                "Questo comando funziona solo dentro un canale ticket.", ephemeral=True
            )
            return

        # Su un ticket già chiuso non cambia nulla nel database.
        appena_chiuso = await ticket_repo.close_ticket(
            interaction.channel.id, interaction.user.id, force=True, reason=motivo
        )
        ticket = await ticket_repo.get_ticket_by_channel(interaction.channel.id) or ticket
        await interaction.response.send_message(
            f"Ticket chiuso forzatamente da {interaction.user.mention}. Elimino il canale.",
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
        if await ticket_repo.close_ticket_of_deleted_channel(channel.id):
            logger.info(
                "Ticket chiuso perché il suo canale %s è stato cancellato a mano.", channel.id
            )

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
    bot.add_dynamic_items(BottonePannello, BottoneVoto, BottoneRichiestaChiusura)
