"""
cogs/utility/role_menus.py
=============================
Role Menu (SPEC.md §14.1-14.3: Reaction Roles, Button Roles, Select
Menu Roles). Modulo gratuito — assunzione dichiarata: lo schema
originale non specifica esplicitamente Free/Premium per questa voce
di §14, e una funzionalità così comune e leggera è ragionevolmente
gratuita per coerenza con gli altri moduli "utility" di base.

Tre modalità, un solo modello dati (core/repositories/role_menu_repo.py):
- reaction: l'utente reagisce con un'emoji sul messaggio del menu.
  Nessun captcha/interazione strutturata possibile qui — solo
  on_raw_reaction_add/remove.
- button: bottoni dinamici, uno per opzione. View PERSISTENTE
  PER-MESSAGGIO (bot.add_view(view, message_id=...)) — diversa dal
  pattern "un solo bottone fisso" già usato per ticket/verify/vocali:
  qui il numero di bottoni varia da menu a menu, quindi la view va
  ricostruita e registrata per OGNI messaggio esistente ad ogni
  avvio del bot (vedi setup() in fondo al file).
- select: una tendina con multi-selezione. Stessa necessità di View
  dinamica per-messaggio del bottone.

Validazione emoji: NON tentata lato client. discord.PartialEmoji.
from_str() non solleva mai (accetta anche una stringa qualunque come
se fosse un nome emoji valido, verificato prima di scrivere questo
file) — è l'API REALE di Discord, quando l'emoji viene davvero usata
(aggiunta come reazione, passata a un bottone), a dire se non è
valida. Gli errori vengono intercettati lì, non con una validazione
finta a monte.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import weakref

import discord
from discord import app_commands
from discord.ext import commands

from core.i18n import testo_per
from core.command_groups import CogConGruppi, SOTTOGRUPPI, comando_di_gruppo
from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.blacklist_repo import blacklist_repo
from core.repositories.role_menu_repo import RoleMenu, RoleMenuOption, role_menu_repo
from core.lista_limiti_logic import dividi_in_blocchi, righe_entro_limite
from core.leveling_logic import colore_valido
from core.role_menu_logic import (
    COMPORTAMENTI,
    COMPORTAMENTO_DI_BASE,
    MAX_RUOLI_ACCESSO,
    MAX_TEMP_SECONDI,
    Decisione,
    can_add_option,
    comportamento_ammesso,
    controlla_limiti,
    decidi_azione,
    posti_finiti,
    risposta_personale,
    MAX_RISPOSTA,
    STILI_BOTTONE,
    analizza_coppie,
    MAX_TESTO_COPPIE,
    VALORE_AZZERA,
    sposta_ruolo,
    decidi_selezione,
    id_emoji_personalizzata,
    membro_ammesso,
    valida_emoji,
)
from core.scheduler import in_seconds, scheduler
from core.role_safety import check_role_assignable
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.role_menus")

MODULE_ROLE_MENUS = "role_menus"

BUTTON_CUSTOM_ID_PREFIX = "iyokai_rolemenu_btn"
SELECT_CUSTOM_ID_PREFIX = "iyokai_rolemenu_select"
ROLEMENU_TEMP_ACTION_TYPE = "rolemenu_temp_remove"


def _build_embed(menu: RoleMenu, options: list[RoleMenuOption]) -> discord.Embed:
    embed = discord.Embed(
        title=menu.title[:256],
        description=(menu.description or None) and menu.description[:2000],
        color=discord.Color(menu.color) if menu.color is not None else discord.Color.blurple(),  # RUO-052
    )
    if menu.behavior != COMPORTAMENTO_DI_BASE:
        embed.set_footer(text=COMPORTAMENTI.get(menu.behavior, menu.behavior)[:2048])
    if not options:
        embed.add_field(name="—", value="No roles configured yet.", inline=False)
        return embed
    if menu.mode == "reaction":
        titolo = "React to get a role"
        righe = [f"{opt.emoji or '❓'} — <@&{opt.role_id}>" for opt in options]
    else:
        titolo = "Available roles"
        righe = [f"• {opt.label or '(no label)'} — <@&{opt.role_id}>" for opt in options]
    # LIM-17: un campo tiene 1024 caratteri; con 25 etichette lunghe l'elenco
    # va su più campi (mai oltre 25 campi e 6000 caratteri in tutto).
    for numero, blocco in enumerate(dividi_in_blocchi(righe, 1024)):
        embed.add_field(name=titolo if numero == 0 else "\u200b", value=blocco, inline=False)
    return embed


# RUO-085: i colori dei bottoni (nel database: il nome di discord.py)
_STILI = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
}
_STILE_DA_SCELTA = {"blu": "primary", "grigio": "secondary", "verde": "success", "rosso": "danger"}

_SCELTE_COMPORTAMENTO = [app_commands.Choice(name=nome, value=nome) for nome in COMPORTAMENTI]


def _errore_comportamento(mode: str, comportamento: str, durata_minuti: int | None) -> str | None:
    """Il motivo per cui il comportamento non va con la modalità o manca la durata, altrimenti None."""
    if not comportamento_ammesso(mode, comportamento):
        solo = "reazioni" if comportamento == "reversed" else "reazioni e bottoni"
        return f"Il comportamento «{comportamento}» non funziona con questa modalità: vale solo per le {solo}."
    if comportamento == "temp" and not durata_minuti:
        return "Per il comportamento temp indica la durata del ruolo in minuti."
    return None


class MenuNonPubblicabile(Exception):
    """Il messaggio del menu non si può pubblicare o aggiornare; il testo è per l'admin."""


PAUSA_SVUOTA_SECONDI = 0.5
PAUSA_REAZIONI_SECONDI = 0.25  # RUO-074: una richiesta per reazione, con una pausa
_SG_RUOLI = ("ruoli", "Ruoli: ruoli-premio per livello e menu di ruoli")


class RoleMenuCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Un blocco per menu: due /menu-aggiungi insieme si mettono in fila
        # (altrimenti una delle due opzioni sparisce o escono due messaggi).
        self._svuotamenti: set[int] = set()  # RUO-080: un'eliminazione in blocco alla volta per server
        self._blocchi_menu: "weakref.WeakValueDictionary[int, asyncio.Lock]" = (
            weakref.WeakValueDictionary()
        )
        self._blocchi_membro: "weakref.WeakValueDictionary[tuple[int, int], asyncio.Lock]" = (
            weakref.WeakValueDictionary()
        )

    def _blocco_membro(self, menu_id: int, user_id: int) -> asyncio.Lock:
        """Un blocco per (menu, membro): due clic insieme di una persona si mettono in fila."""
        chiave = (menu_id, user_id)
        blocco = self._blocchi_membro.get(chiave)
        if blocco is None:
            blocco = asyncio.Lock()
            self._blocchi_membro[chiave] = blocco
        return blocco

    @staticmethod
    async def _membro_aggiornato(guild: discord.Guild, member: discord.Member) -> discord.Member:
        """I ruoli di chi clicca, riletti DOPO aver preso il blocco (l'interazione porta una foto vecchia)."""
        try:
            return await guild.fetch_member(member.id)
        except discord.HTTPException:
            return member

    def _blocco_menu(self, menu_id: int) -> asyncio.Lock:
        blocco = self._blocchi_menu.get(menu_id)
        if blocco is None:
            blocco = asyncio.Lock()
            self._blocchi_menu[menu_id] = blocco
        return blocco

    # ================================================================
    # Costruzione delle view dinamiche
    # ================================================================
    def _build_button_view(self, menu_id: int, options: list[RoleMenuOption]) -> discord.ui.View:
        view = BaseView(timeout=None)
        for opt in options:
            button: discord.ui.Button = discord.ui.Button(
                label=(opt.label or "Role")[:80],
                emoji=opt.emoji,
                style=_STILI.get(opt.button_style, discord.ButtonStyle.secondary),  # RUO-085
                custom_id=f"{BUTTON_CUSTOM_ID_PREFIX}:{menu_id}:{opt.role_id}",
            )
            button.callback = self._make_button_callback(menu_id, opt.role_id)
            view.add_item(button)
        return view

    def _build_select_view(
        self, menu_id: int, options: list[RoleMenuOption], max_selectable: int | None, placeholder: str = "",
        con_azzera: bool = False,
    ) -> discord.ui.View:
        view = BaseView(timeout=None)
        select_options = [
            discord.SelectOption(
                label=(opt.label or "Role")[:100], value=str(opt.role_id), emoji=opt.emoji,
                description=opt.description[:100] or None,  # RUO-086
            )
            for opt in options
        ]
        limite = max_selectable if max_selectable else len(select_options)
        limite = max(1, min(limite, len(select_options)))
        if con_azzera:  # RUO-087: in fondo, dentro le 25 voci
            select_options.append(discord.SelectOption(label="Togli tutti i ruoli", value=VALORE_AZZERA, emoji="🧹"))

        select: discord.ui.Select = discord.ui.Select(
            custom_id=f"{SELECT_CUSTOM_ID_PREFIX}:{menu_id}",
            placeholder=placeholder[:150] or "Choose your roles...",  # RUO-086
            min_values=0,
            max_values=limite,
            options=select_options,
        )
        select.callback = self._make_select_callback(menu_id, select)
        view.add_item(select)
        return view

    def _make_button_callback(self, menu_id: int, role_id: int):
        async def callback(interaction: discord.Interaction) -> None:
            await self._handle_button_click(interaction, menu_id, role_id)

        return callback

    def _make_select_callback(self, menu_id: int, select: discord.ui.Select):
        async def callback(interaction: discord.Interaction) -> None:
            await self._handle_select(interaction, menu_id, select)

        return callback

    async def _build_view_for_menu(
        self, menu: RoleMenu, options: list[RoleMenuOption]
    ) -> discord.ui.View | None:
        """Un solo punto che decide quale view costruire per modalità
        — usato sia dal refresh dopo una modifica sia dalla
        ricostruzione all'avvio del bot, per non duplicare la
        diramazione button/select in due posti diversi."""
        if menu.mode == "button":
            return self._build_button_view(menu.id, options)
        if menu.mode == "select":
            return self._build_select_view(menu.id, options, menu.max_selectable, menu.placeholder, menu.reset_option)
        return None

    async def _pubblica_menu(
        self, guild: discord.Guild, menu: RoleMenu, options: list[RoleMenuOption]
    ) -> int:
        """
        Pubblica o aggiorna il messaggio del menu con `options` (l'elenco
        DOPO la modifica, non ancora salvato) e registra la View. Se non
        riesce solleva MenuNonPubblicabile: il chiamante salva nel database
        solo dopo che Discord ha accettato il messaggio. Restituisce l'ID
        del messaggio (nuovo se quello vecchio era stato cancellato).
        """
        channel = guild.get_channel(menu.channel_id)
        if not isinstance(channel, discord.TextChannel):
            raise MenuNonPubblicabile("Il canale del menu non esiste più o non lo vedo.")

        embed = _build_embed(menu, options)
        if len(embed) > 6000:
            raise MenuNonPubblicabile(
                "Il menu supera i 6000 caratteri consentiti da Discord: accorcia titolo, "
                "descrizione o etichette."
            )
        view = await self._build_view_for_menu(menu, options)

        message = None
        if menu.message_id is not None:
            try:
                message = await channel.fetch_message(menu.message_id)
            except discord.NotFound:
                message = None  # cancellato a mano: si ripubblica
            except discord.HTTPException as errore:
                logger.warning(
                    "Impossibile leggere il messaggio del role menu %s (server %s): %s",
                    menu.id, guild.id, errore,
                )
                raise MenuNonPubblicabile(
                    "Non riesco a leggere il messaggio del menu (permessi mancanti)."
                ) from errore
        nuovo = message is None
        if nuovo and menu.external:  # RUO-072: un messaggio di altri non si ripubblica
            raise MenuNonPubblicabile("Il messaggio a cui è agganciato il menu non esiste più.")
        if nuovo:
            try:
                message = await channel.send(embed=embed, view=view)
            except discord.HTTPException as errore:
                logger.warning(
                    "Impossibile pubblicare il role menu %s (server %s): %s",
                    menu.id, guild.id, errore,
                )
                raise MenuNonPubblicabile(
                    "Non riesco a pubblicare il messaggio del menu nel canale "
                    "(permessi mancanti o testo troppo lungo)."
                ) from errore

        reazioni_aggiunte: list[str] = []
        if menu.mode == "reaction":
            # Le reazioni PRIMA di toccare l'embed: se Discord ne rifiuta una,
            # il messaggio resta com'era (o, se è nuovo, sparisce).
            try:
                esistenti = {str(r.emoji) for r in message.reactions}
                for opt in options:
                    if opt.emoji and opt.emoji not in esistenti:
                        idp = id_emoji_personalizzata(opt.emoji)
                        if idp is not None and self.bot.get_emoji(idp) is None:
                            continue  # RUO-075: emoji di un server dove il bot non c'è, la mette l'admin a mano
                        await message.add_reaction(opt.emoji)
                        reazioni_aggiunte.append(opt.emoji)
                        await asyncio.sleep(PAUSA_REAZIONI_SECONDI)
            except discord.HTTPException as errore:
                await self._annulla_pubblicazione(message, nuovo, reazioni_aggiunte)
                raise MenuNonPubblicabile(
                    "Discord non accetta una delle emoji del menu come reazione."
                ) from errore

        if not nuovo and not menu.external:
            try:
                await message.edit(embed=embed, view=view)
            except discord.HTTPException as errore:
                await self._annulla_pubblicazione(message, False, reazioni_aggiunte)
                logger.warning(
                    "Impossibile aggiornare il messaggio del role menu %s (server %s): %s",
                    menu.id, guild.id, errore,
                )
                raise MenuNonPubblicabile(
                    "Discord ha rifiutato la modifica del messaggio del menu "
                    "(permessi mancanti o testo troppo lungo)."
                ) from errore
        else:
            await role_menu_repo.set_menu_message(menu.id, message.id)

        if menu.mode == "reaction":
            # Le reazioni dei ruoli tolti dal menu non servono più.
            tenute = {opt.emoji for opt in options if opt.emoji}
            for reazione in list(message.reactions):
                if menu.external and not reazione.me:
                    continue  # su un messaggio di altri si tolgono solo le reazioni messe dal bot
                if str(reazione.emoji) not in tenute:
                    try:
                        await message.clear_reaction(reazione.emoji)
                    except discord.HTTPException:
                        pass
        elif view is not None:
            self.bot.add_view(view, message_id=message.id)
        return message.id

    @staticmethod
    async def _annulla_pubblicazione(
        message: discord.Message, nuovo: bool, reazioni_aggiunte: list[str]
    ) -> None:
        """Rimette le cose com'erano dopo un rifiuto di Discord (best effort)."""
        try:
            if nuovo:
                await message.delete()
                return
            for emoji in reazioni_aggiunte:
                await message.clear_reaction(emoji)
        except discord.HTTPException:
            logger.warning("Non sono riuscito ad annullare la pubblicazione del role menu.")

    # ================================================================
    # Gestori delle interazioni
    # ================================================================
    async def _handle_button_click(
        self, interaction: discord.Interaction, menu_id: int, role_id: int
    ) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_ROLE_MENUS):
            await interaction.response.send_message(await testo_per(interaction, "rm_non_attivo"), ephemeral=True)
            return

        role = guild.get_role(role_id)
        if role is None:
            await interaction.response.send_message(
                await testo_per(interaction, "rolemenus_this_role_no_longer_exists"), ephemeral=True
            )
            return

        menu = await role_menu_repo.get_menu(menu_id)
        if menu is None:
            await interaction.response.send_message(await testo_per(interaction, "rolemenus_questo_menu_non_esiste_piu"), ephemeral=True)
            return
        # fetch_member, add_roles e scheduler possono superare i 3 secondi: si prenota la risposta.
        await interaction.response.defer(ephemeral=True)
        async with self._blocco_membro(menu.id, interaction.user.id):
            utente = await self._membro_aggiornato(guild, interaction.user)
            ruoli_membro = {r.id for r in utente.roles}
            negato = membro_ammesso(list(menu.allowed_role_ids), list(menu.excluded_role_ids), ruoli_membro)
            if negato is not None:
                await interaction.followup.send(negato, ephemeral=True)
                return
            opzioni = await role_menu_repo.get_options(menu_id)
            decisione = decidi_azione(
                menu.behavior,
                attiva=True,
                via_reazione=False,
                ruolo_id=role_id,
                ruoli_menu={o.role_id for o in opzioni},
                ruoli_membro=ruoli_membro,
                toggle=menu.toggle,
                temp_secondi=menu.temp_seconds,
            )
            if decisione.rifiuto is None:
                limite = self._rifiuto_limiti(guild, menu, opzioni, decisione, ruoli_membro)
                decisione = dataclasses.replace(decisione, rifiuto=limite) if limite else decisione
            if decisione.rifiuto is not None:
                await interaction.followup.send(decisione.rifiuto, ephemeral=True)
                return

            errore = await self._applica(guild, utente, decisione, "Role menu")
            if errore is not None:
                await interaction.followup.send(errore, ephemeral=True)
                return
        if not menu.notify:  # RUO-081: niente conferma in privato
            try:
                await interaction.delete_original_response()
            except discord.HTTPException:
                pass
            return
        if decisione.aggiungi and menu.reply_text:  # RUO-082
            testo = risposta_personale(menu.reply_text, role.mention)
        elif decisione.aggiungi:
            testo = f"Role {role.mention} added."
            if decisione.temporaneo_secondi:
                testo += f" Lo perderai tra {max(decisione.temporaneo_secondi // 60, 1)} minuti."
        elif decisione.togli:
            testo = f"Role {role.mention} removed."
        else:
            testo = "Nessun cambiamento."
        await interaction.followup.send(testo, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @staticmethod
    def _rifiuto_limiti(
        guild: discord.Guild, menu: RoleMenu, opzioni: list, decisione: Decisione, ruoli_membro: set[int]
    ) -> str | None:
        """RUO-062, 063, 065: tetto e minimo di ruoli del menu, posti limitati per opzione."""
        motivo = controlla_limiti(
            decisione,
            ruoli_menu={o.role_id for o in opzioni},
            ruoli_membro=ruoli_membro,
            massimo=menu.max_selectable,
            minimo=menu.min_roles,
        )
        if motivo is not None:
            return motivo
        tetti = {o.role_id: o.max_members for o in opzioni if o.max_members is not None}
        for rid in decisione.aggiungi:
            ruolo = guild.get_role(rid)
            if rid in tetti and ruolo is not None and posti_finiti(
                membri_con_ruolo=len(ruolo.members), max_membri=tetti[rid]
            ):
                return "I posti per questo ruolo sono finiti."
        return None

    async def _applica(
        self, guild: discord.Guild, member: discord.Member, decisione: Decisione, motivo: str
    ) -> str | None:
        """
        Dà e toglie i ruoli di una decisione. SEC-4/SEC-17: ogni ruolo da DARE si ricontrolla
        (self_service); toglierlo resta sempre permesso. None se tutto bene, altrimenti il
        testo per l'utente. Il ruolo temporaneo programma la propria rimozione.
        """
        da_dare = []
        for rid in decisione.aggiungi:
            ruolo = guild.get_role(rid)
            if ruolo is None:
                continue
            rifiuto = check_role_assignable(guild, ruolo, guild.me, self_service=True)
            if rifiuto is not None:
                if len(decisione.aggiungi) == 1:
                    return rifiuto
                continue  # un ruolo diventato pericoloso si salta, gli altri passano
            da_dare.append(ruolo)
        da_togliere = [r for r in (guild.get_role(rid) for rid in decisione.togli) if r is not None]
        try:
            if da_dare:
                await member.add_roles(*da_dare, reason=motivo)
            if da_togliere:
                await member.remove_roles(*da_togliere, reason=motivo)
        except discord.Forbidden:
            return "I don't have permission to manage that role."
        except discord.HTTPException:
            logger.warning("Errore Discord con i ruoli del menu nel server %s.", guild.id)
            return "Discord ha dato un errore: riprova tra poco."
        if decisione.temporaneo_secondi and da_dare:
            for ruolo in da_dare:
                # Ruolo ripreso prima della scadenza: la vecchia rimozione lo toglierebbe subito.
                for vecchia in await scheduler.list_pending_for_user(member.id, ROLEMENU_TEMP_ACTION_TYPE, 100):
                    if vecchia["guild_id"] == guild.id and vecchia["payload"].get("role_id") == ruolo.id:
                        await scheduler.cancel(vecchia["id"])
                await scheduler.schedule(
                    guild.id, member.id, ROLEMENU_TEMP_ACTION_TYPE,
                    in_seconds(decisione.temporaneo_secondi), {"role_id": ruolo.id},
                )
        return None

    async def handle_rolemenu_temp(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Handler dello scheduler: toglie il ruolo a tempo, se il membro c'è ancora e lo ha."""
        guild = self.bot.get_guild(guild_id)
        role_id = payload.get("role_id")
        if guild is None or role_id is None:
            return
        member = guild.get_member(user_id)
        ruolo = guild.get_role(role_id)
        if member is None or ruolo is None or ruolo not in member.roles:
            return
        await member.remove_roles(ruolo, reason="Role menu (ruolo a tempo scaduto)")

    async def _handle_select(
        self, interaction: discord.Interaction, menu_id: int, select: discord.ui.Select
    ) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_ROLE_MENUS):
            await interaction.response.send_message(await testo_per(interaction, "rm_non_attivo"), ephemeral=True)
            return

        menu = await role_menu_repo.get_menu(menu_id)
        if menu is None:
            await interaction.response.send_message(await testo_per(interaction, "rolemenus_questo_menu_non_esiste_piu"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        options = await role_menu_repo.get_options(menu_id)
        async with self._blocco_membro(menu.id, interaction.user.id):
            utente = await self._membro_aggiornato(guild, interaction.user)
            ruoli_membro = {r.id for r in utente.roles}
            negato = membro_ammesso(list(menu.allowed_role_ids), list(menu.excluded_role_ids), ruoli_membro)
            if negato is not None:
                await interaction.followup.send(negato, ephemeral=True)
                return
            decisione = decidi_selezione(
                menu.behavior,
                ruoli_menu={opt.role_id for opt in options},
                ruoli_membro=ruoli_membro,
                scelti=set() if VALORE_AZZERA in select.values else {int(v) for v in select.values},
                temp_secondi=menu.temp_seconds,
            )
            if decisione.rifiuto is None:
                limite = self._rifiuto_limiti(guild, menu, options, decisione, ruoli_membro)
                decisione = dataclasses.replace(decisione, rifiuto=limite) if limite else decisione
            if decisione.rifiuto is not None:
                await interaction.followup.send(decisione.rifiuto, ephemeral=True)
                return
            errore = await self._applica(guild, utente, decisione, "Role menu")
            if errore is not None:
                await interaction.followup.send(errore, ephemeral=True)
                return

        if not menu.notify:  # RUO-081
            try:
                await interaction.delete_original_response()
            except discord.HTTPException:
                pass
            return
        if menu.reply_text and decisione.aggiungi:  # RUO-082
            ruolo = guild.get_role(decisione.aggiungi[0])
            if ruolo is not None:
                await interaction.followup.send(
                    risposta_personale(menu.reply_text, ruolo.mention),
                    ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
                )
                return
        await interaction.followup.send(await testo_per(interaction, "rm_ruoli_aggiornati"), ephemeral=True)

    # ================================================================
    # Modalità reaction
    # ================================================================
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.member is None or payload.member.bot:
            return

        # SEC-10: un utente in blacklist non deve poter ottenere ruoli
        # reagendo a un role menu.
        if await blacklist_repo.is_user_blacklisted(payload.member.id):
            return

        if not await db.is_module_active_for_guild(payload.guild_id, MODULE_ROLE_MENUS):
            return

        menu = await role_menu_repo.get_menu_by_message(payload.guild_id, payload.message_id)
        if menu is None or menu.mode != "reaction":
            return

        option = await role_menu_repo.get_option_by_emoji(menu.id, str(payload.emoji))
        if option is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None or guild.get_role(option.role_id) is None:
            return
        await self._reazione(guild, menu, option.role_id, payload.member, attiva=True, motivo="Role menu (reaction)")

    async def _reazione(
        self, guild: discord.Guild, menu: RoleMenu, role_id: int, member: discord.Member, *, attiva: bool, motivo: str
    ) -> None:
        """Una reazione messa o tolta su un menu: accesso, comportamento, ruoli (nessuna risposta possibile)."""
        async with self._blocco_membro(menu.id, member.id):
            member = await self._membro_aggiornato(guild, member)
            ruoli_membro = {r.id for r in member.roles}
            if membro_ammesso(list(menu.allowed_role_ids), list(menu.excluded_role_ids), ruoli_membro) is not None:
                return
            opzioni = await role_menu_repo.get_options(menu.id)
            decisione = decidi_azione(
                menu.behavior,
                attiva=attiva,
                via_reazione=True,
                ruolo_id=role_id,
                ruoli_menu={o.role_id for o in opzioni},
                ruoli_membro=ruoli_membro,
                toggle=menu.toggle,
                temp_secondi=menu.temp_seconds,
            )
            if decisione.rifiuto is None:
                decisione = dataclasses.replace(
                    decisione, rifiuto=self._rifiuto_limiti(guild, menu, opzioni, decisione, ruoli_membro)
                )
            if decisione.rifiuto is not None:
                return
            errore = await self._applica(guild, member, decisione, motivo)
            if errore is not None:
                logger.warning("Reazione sul menu %s nel server %s: %s", menu.id, guild.id, errore)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        # A differenza di on_raw_reaction_add, qui payload.member NON
        # è disponibile (Discord non lo invia per gli eventi di
        # rimozione) — va recuperato dalla cache della guild.
        if payload.guild_id is None:
            return

        if not await db.is_module_active_for_guild(payload.guild_id, MODULE_ROLE_MENUS):
            return

        menu = await role_menu_repo.get_menu_by_message(payload.guild_id, payload.message_id)
        if menu is None or menu.mode != "reaction":
            return

        option = await role_menu_repo.get_option_by_emoji(menu.id, str(payload.emoji))
        if option is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        member = guild.get_member(payload.user_id)
        if member is None or member.bot:
            return
        if guild.get_role(option.role_id) is None:
            return
        await self._reazione(
            guild, menu, option.role_id, member, attiva=False, motivo="Role menu (reaction removed)"
        )

    # ================================================================
    # Comandi
    # ================================================================

    @comando_di_gruppo(
        "admin-ruoli",
        nome="crea",
        descrizione="Crea un nuovo role menu.",
        sottogruppo=SOTTOGRUPPI["admin-ruoli menu"],
    )
    @app_commands.describe(
        title="Titolo del menu",
        mode="Modalità di interazione",
        description="Descrizione facoltativa",
        channel="Canale dove pubblicare il menu (default: questo canale)",
        toggle="Ri-cliccare/reagire toglie il ruolo? (solo bottone/reazione)",
        max_selectable="Quanti ruoli del menu si possono avere insieme",
        min_ruoli="Quanti ruoli del menu restano sempre (almeno questi)",
        comportamento="Come si comporta il menu (unique, verify, drop, reversed, binding, temp, lock)",
        durata_minuti="Quanto dura il ruolo (solo comportamento temp)",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Reaction", value="reaction"),
            app_commands.Choice(name="Button", value="button"),
            app_commands.Choice(name="Select menu", value="select"),
        ],
        comportamento=_SCELTE_COMPORTAMENTO,
    )
    async def create_cmd(
        self,
        interaction: discord.Interaction,
        title: app_commands.Range[str, 1, 256],
        mode: app_commands.Choice[str],
        description: app_commands.Range[str, 0, 2000] = "",
        channel: discord.TextChannel | None = None,
        toggle: bool = True,
        max_selectable: app_commands.Range[int, 1, 25] | None = None,
        comportamento: str = COMPORTAMENTO_DI_BASE,
        durata_minuti: app_commands.Range[int, 1, MAX_TEMP_SECONDI // 60] | None = None,
        min_ruoli: app_commands.Range[int, 1, 25] | None = None,
        coppie: app_commands.Range[str, 1, MAX_TESTO_COPPIE] | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return
        if min_ruoli and max_selectable and min_ruoli > max_selectable:  # RUO-063
            await interaction.response.send_message("Il minimo non può superare il massimo.", ephemeral=True)
            return

        errore = _errore_comportamento(mode.value, comportamento, durata_minuti)
        if errore is not None:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        if mode.value == "select" and comportamento == "unique":
            max_selectable = 1

        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                await testo_per(interaction, "rolemenus_scegli_un_canale_di_testo"), ephemeral=True
            )
            return

        menu_id = await role_menu_repo.create_menu(
            guild_id=guild.id,
            channel_id=target_channel.id,
            mode=mode.value,
            toggle=toggle,
            max_selectable=max_selectable,
            title=title,
            description=description,
            behavior=comportamento,
            temp_seconds=durata_minuti * 60 if durata_minuti else None,
        )
        if min_ruoli:
            await role_menu_repo.update_menu(menu_id, min_roles=min_ruoli)
        if coppie is not None and isinstance(interaction.user, discord.Member):  # RUO-048
            await interaction.response.defer(ephemeral=True)
            esito = await self._aggiungi_coppie(guild, interaction.user, menu_id, coppie)
            await interaction.followup.send(
                f"Menu creato (ID {menu_id}). {esito}", ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
            )
            return

        await interaction.response.send_message(
            await testo_per(interaction, "rolemenus_role_menu_creato_id_modalita", menu_id=menu_id, name=mode.name),
            ephemeral=True,
        )

    @comando_di_gruppo(
        "admin-ruoli",
        nome="aggiungi",
        descrizione="Aggiungi un'opzione a un role menu.",
        sottogruppo=SOTTOGRUPPI["admin-ruoli menu"],
    )
    @app_commands.describe(
        menu_id="ID del menu (mostrato da /admin-ruoli menu crea)",
        role="Il ruolo da assegnare",
        emoji="Emoji (obbligatoria per reaction/button)",
        label="Etichetta del bottone/opzione (obbligatoria per button/select)",
        max_membri="Posti limitati: quanti membri al massimo possono avere il ruolo da questo menu",
        colore="Colore del bottone",
        descrizione="Riga sotto l'opzione nella tendina (massimo 100 caratteri)",
        emoji_esterna="Emoji di un server dove il bot non c'è (menu a reazioni): la reazione la metti tu",
    )
    @app_commands.choices(colore=[app_commands.Choice(name=n, value=n) for n in STILI_BOTTONE])
    async def add_option_cmd(
        self,
        interaction: discord.Interaction,
        menu_id: int,
        role: discord.Role,
        emoji: app_commands.Range[str, 1, 60] | None = None,
        label: app_commands.Range[str, 1, 80] | None = None,
        max_membri: app_commands.Range[int, 1, 1_000_000] | None = None,
        colore: str | None = None,
        descrizione: app_commands.Range[str, 0, 100] = "",
        emoji_esterna: bool = False,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return

        menu = await role_menu_repo.get_menu(menu_id)
        if menu is None or menu.guild_id != guild.id:
            await interaction.response.send_message(
                await testo_per(interaction, "rolemenus_nessun_role_menu_trovato_con"),
                ephemeral=True,
            )
            return

        if menu.mode in ("reaction", "button") and emoji is None:
            await interaction.response.send_message(
                await testo_per(interaction, "rolemenus_la_modalita_richiede_un_emoji", mode=menu.mode), ephemeral=True
            )
            return
        if menu.mode in ("button", "select") and label is None:
            await interaction.response.send_message(
                await testo_per(interaction, "rolemenus_la_modalita_richiede_un_etichetta", mode=menu.mode), ephemeral=True
            )
            return

        conteggio = await role_menu_repo.count_options(menu_id)
        if not can_add_option(conteggio + int(menu.reset_option), menu.mode):
            await interaction.response.send_message(
                await testo_per(interaction, "rolemenus_limite_di_opzioni_raggiunto_per", mode=menu.mode),
                ephemeral=True,
            )
            return

        if not isinstance(interaction.user, discord.Member):
            return

        motivo_rifiuto = check_role_assignable(guild, role, interaction.user, self_service=True)
        if motivo_rifiuto is not None:
            await interaction.response.send_message(motivo_rifiuto, ephemeral=True)
            return

        if emoji is not None:
            if not valida_emoji(emoji):
                await interaction.response.send_message(
                    await testo_per(interaction, "rolemenus_quella_non_un_emoji_valida"),
                    ephemeral=True,
                )
                return
            id_personalizzata = id_emoji_personalizzata(emoji)
            esterna_ok = emoji_esterna and menu.mode == "reaction"  # RUO-075: la reazione la mette l'admin
            if id_personalizzata is not None and self.bot.get_emoji(id_personalizzata) is None and not esterna_ok:
                await interaction.response.send_message(
                    await testo_per(interaction, "rolemenus_non_vedo_quell_emoji_personalizzata"),
                    ephemeral=True,
                )
                return

        stile = _STILE_DA_SCELTA.get(colore or "", "secondary")  # RUO-085
        await interaction.response.defer(ephemeral=True)
        async with self._blocco_menu(menu_id):
            # Dentro il blocco si rilegge tutto: un altro comando potrebbe aver
            # appena pubblicato il messaggio o cambiato le opzioni.
            menu = await role_menu_repo.get_menu(menu_id)
            if menu is None:
                await interaction.followup.send(await testo_per(interaction, "rolemenus_questo_menu_non_esiste_piu"), ephemeral=True)
                return
            esistenti = [
                o for o in await role_menu_repo.get_options(menu_id) if o.role_id != role.id
            ]
            if not can_add_option(len(esistenti) + int(menu.reset_option), menu.mode):
                await interaction.followup.send(
                    await testo_per(interaction, "rolemenus_limite_di_opzioni_raggiunto_per", mode=menu.mode),
                    ephemeral=True,
                )
                return
            nuova = RoleMenuOption(
                id=0, menu_id=menu_id, role_id=role.id, emoji=emoji, label=label,
                position=len(esistenti), max_members=max_membri,
                button_style=stile, description=descrizione,
            )
            # Prima si pubblica il messaggio con la nuova opzione, poi la si salva:
            # se Discord rifiuta (campo troppo lungo, permessi, emoji) nel
            # database non resta un'opzione che nel menu non c'è.
            try:
                await self._pubblica_menu(guild, menu, esistenti + [nuova])
            except MenuNonPubblicabile as errore:
                await interaction.followup.send(
                    f"L'opzione {role.mention} non è stata aggiunta. {errore}", ephemeral=True
                )
                return
            await role_menu_repo.add_option(menu_id, role.id, emoji, label, max_membri, stile, descrizione)

        testo_finale = await testo_per(interaction, "rolemenus_opzione_aggiunta", mention=role.mention)
        if emoji_esterna and menu.mode == "reaction" and emoji and id_emoji_personalizzata(emoji) is not None \
                and self.bot.get_emoji(id_emoji_personalizzata(emoji)) is None:
            testo_finale += " Il bot non vede quell'emoji: metti tu la reazione sul messaggio del menu."
        await interaction.followup.send(testo_finale, ephemeral=True)

    async def _aggiungi_coppie(
        self, guild: discord.Guild, attore: discord.Member, menu_id: int, testo: str
    ) -> str:
        """
        RUO-048, RUO-049: aggiunge a un menu tutte le coppie «emoji ruolo» in un colpo. Si controlla tutto prima
        (ruoli, emoji, posti), si pubblica una volta sola e solo dopo si salva: o passano tutte o nessuna.
        Torna il testo da mostrare a chi ha lanciato il comando.
        """
        coppie, errore = analizza_coppie(
            testo, lambda nome: next((r.id for r in guild.roles if r.name.lower() == nome.lower()), None)
        )
        if errore is not None:
            return errore
        async with self._blocco_menu(menu_id):
            menu = await role_menu_repo.get_menu(menu_id)
            if menu is None or menu.guild_id != guild.id:
                return "Nessun menu con quell'ID."
            esistenti = await role_menu_repo.get_options(menu_id)
            nuovi_ruoli = {rid for _, rid in coppie}
            tenuti = [o for o in esistenti if o.role_id not in nuovi_ruoli]
            if not can_add_option(len(tenuti) + len(coppie) - 1 + int(menu.reset_option), menu.mode):
                return f"Il menu non ha posto per {len(coppie)} opzioni in più."
            nuove = []
            for posto, (emoji, rid) in enumerate(coppie, start=len(tenuti)):
                ruolo = guild.get_role(rid)
                if ruolo is None:
                    return "Uno dei ruoli non esiste più."
                rifiuto = check_role_assignable(guild, ruolo, attore, self_service=True)
                if rifiuto is not None:
                    return f"{ruolo.name[:40]}: {rifiuto}"
                if menu.mode in ("reaction", "button") and emoji is None:
                    return f"Per «{ruolo.name[:40]}» serve un'emoji."
                if emoji is not None:
                    personalizzata = id_emoji_personalizzata(emoji)
                    if personalizzata is not None and self.bot.get_emoji(personalizzata) is None:
                        return f"Non vedo l'emoji personalizzata di «{ruolo.name[:40]}»: il bot deve essere nel suo server."
                nuove.append(
                    RoleMenuOption(
                        id=0, menu_id=menu_id, role_id=rid, emoji=emoji, label=ruolo.name[:80],
                        position=posto, button_style="secondary", description="",
                    )
                )
            try:
                await self._pubblica_menu(guild, menu, tenuti + nuove)
            except MenuNonPubblicabile as errore_pubblicazione:
                return f"Nessuna opzione aggiunta. {errore_pubblicazione}"
            for o in nuove:
                await role_menu_repo.add_option(menu_id, o.role_id, o.emoji, o.label)
        return f"Aggiunte {len(nuove)} opzioni."

    @comando_di_gruppo(
        "admin-ruoli",
        nome="aggiungi-molti",
        descrizione="Aggiungi a un menu più coppie emoji-ruolo in un colpo solo.",
        sottogruppo=SOTTOGRUPPI["admin-ruoli menu"],
    )
    @app_commands.describe(
        menu_id="ID del menu",
        coppie="Coppie «emoji ruolo» separate da punto e virgola, per esempio: 🎮 @Gamer; 🎨 @Artista",
    )
    async def add_many_cmd(
        self, interaction: discord.Interaction, menu_id: int, coppie: app_commands.Range[str, 1, MAX_TESTO_COPPIE]
    ) -> None:
        """RUO-049: tutte le coppie in un comando su un menu che c'è già."""
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            return
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
            await self._aggiungi_coppie(guild, interaction.user, menu_id, coppie), ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo(
        "admin-ruoli",
        nome="togli",
        descrizione="Rimuovi un'opzione da un role menu.",
        sottogruppo=SOTTOGRUPPI["admin-ruoli menu"],
    )
    @app_commands.describe(menu_id="ID del menu", role="Il ruolo da rimuovere dal menu")
    async def remove_option_cmd(
        self, interaction: discord.Interaction, menu_id: int, role: discord.Role
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return

        menu = await role_menu_repo.get_menu(menu_id)
        if menu is None or menu.guild_id != guild.id:
            await interaction.response.send_message(
                await testo_per(interaction, "rolemenus_nessun_role_menu_trovato_con"),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        async with self._blocco_menu(menu_id):
            menu = await role_menu_repo.get_menu(menu_id)
            if menu is None:
                await interaction.followup.send(await testo_per(interaction, "rolemenus_questo_menu_non_esiste_piu"), ephemeral=True)
                return
            opzioni = await role_menu_repo.get_options(menu_id)
            if not any(o.role_id == role.id for o in opzioni):
                await interaction.followup.send(
                    await testo_per(interaction, "rolemenus_quel_ruolo_non_fa_parte"), ephemeral=True
                )
                return

            rimaste = [o for o in opzioni if o.role_id != role.id]
            if not rimaste:
                # Una tendina senza opzioni non è valida per Discord e un menu
                # vuoto non serve a nessuno: si toglie il menu intero.
                messaggio_cancellato = await self._elimina_menu(guild, menu)
                dettaglio = (
                    "e l'ho eliminato."
                    if messaggio_cancellato
                    else "e l'ho eliminato dal database, ma non sono riuscito a cancellare "
                    "il messaggio: cancellalo a mano."
                )
                await interaction.followup.send(
                    f"Opzione rimossa: {role.mention}. Il menu era rimasto senza opzioni "
                    f"{dettaglio}",
                    ephemeral=True,
                )
                return

            try:
                await self._pubblica_menu(guild, menu, rimaste)
            except MenuNonPubblicabile as errore:
                await interaction.followup.send(
                    f"L'opzione {role.mention} non è stata rimossa: il messaggio del menu "
                    f"non si aggiorna. {errore}",
                    ephemeral=True,
                )
                return
            await role_menu_repo.remove_option(menu_id, role.id)
        await interaction.followup.send(await testo_per(interaction, "rolemenus_opzione_rimossa", mention=role.mention), ephemeral=True)

    async def _elimina_menu(self, guild: discord.Guild, menu: RoleMenu) -> bool:
        """
        Elimina il menu dal database e prova a cancellare il messaggio.
        True se il messaggio non c'è più (cancellato, già sparito o mai
        pubblicato); False se Discord non ha permesso di cancellarlo.
        """
        messaggio_sparito = True
        if menu.external and menu.message_id is not None:  # RUO-072: il messaggio non è del bot, non si cancella
            await self._stacca_messaggio(guild, menu)
            await role_menu_repo.delete_menu(menu.id)
            return True
        if menu.message_id is not None:
            channel = guild.get_channel(menu.channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.fetch_message(menu.message_id)
                    await message.delete()
                except discord.NotFound:
                    pass
                except discord.HTTPException:
                    messaggio_sparito = False
            else:
                messaggio_sparito = False
        await role_menu_repo.delete_menu(menu.id)
        return messaggio_sparito

    @comando_di_gruppo(
        "admin-ruoli",
        nome="elenco",
        descrizione="Mostra i menu di ruoli del server, con gli ID.",
        sottogruppo=SOTTOGRUPPI["admin-ruoli menu"],
    )
    async def list_cmd(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        menu = await role_menu_repo.list_menus_for_guild(guild.id)
        righe = []
        for m in menu:
            n = await role_menu_repo.count_options(m.id)
            righe.append(f"`{m.id}` · {m.title[:60]} · {m.mode}/{m.behavior} · <#{m.channel_id}> · {n} opzioni")
        testo, _ = righe_entro_limite(righe or ["Nessun menu di ruoli."], 3900)
        await interaction.response.send_message(
            embed=discord.Embed(title=await testo_per(interaction, "rolemenus_menu_di_ruoli", v1=len(menu)), description=testo),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo(
        "admin-ruoli",
        nome="modifica",
        descrizione="Cambia titolo, descrizione o comportamento di un menu già pubblicato.",
        sottogruppo=SOTTOGRUPPI["admin-ruoli menu"],
    )
    @app_commands.describe(
        menu_id="ID del menu (lo mostra /admin-ruoli menu elenco)",
        titolo="Nuovo titolo",
        descrizione="Nuova descrizione",
        comportamento="Nuovo comportamento",
        durata_minuti="Durata del ruolo (comportamento temp)",
        massimo="Quanti ruoli del menu si possono avere insieme (0 = nessun tetto)",
        minimo="Quanti ruoli del menu restano sempre (0 = nessun minimo)",
        colore="Colore del messaggio, per esempio #C24A3A (oppure «predefinito»)",
        testo_guida="Testo-guida della tendina (vuoto = quello di base)",
        risposta="Risposta a chi prende un ruolo; {ruolo} diventa il ruolo (vuoto = quella di base)",
        avvisa="Conferma in privato a chi usa il menu (bottoni e tendina)",
        voce_azzera="Tendina: aggiungi in fondo la voce «Togli tutti i ruoli»",
    )
    @app_commands.choices(comportamento=_SCELTE_COMPORTAMENTO)
    async def edit_cmd(
        self,
        interaction: discord.Interaction,
        menu_id: int,
        titolo: app_commands.Range[str, 1, 256] | None = None,
        descrizione: app_commands.Range[str, 0, 2000] | None = None,
        comportamento: str | None = None,
        durata_minuti: app_commands.Range[int, 1, MAX_TEMP_SECONDI // 60] | None = None,
        massimo: app_commands.Range[int, 0, 25] | None = None,
        minimo: app_commands.Range[int, 0, 25] | None = None,
        colore: app_commands.Range[str, 4, 11] | None = None,
        testo_guida: app_commands.Range[str, 0, 150] | None = None,
        risposta: app_commands.Range[str, 0, MAX_RISPOSTA] | None = None,
        avvisa: bool | None = None,
        voce_azzera: bool | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return
        menu = await role_menu_repo.get_menu(menu_id)
        if menu is None or menu.guild_id != guild.id:
            await interaction.response.send_message(
                await testo_per(interaction, "rolemenus_nessun_role_menu_trovato_con"), ephemeral=True
            )
            return
        campi: dict = {}
        if colore is not None:  # RUO-052
            if colore.lower() == "predefinito":
                campi["color"] = None
            else:
                esadecimale = colore_valido(colore)
                if esadecimale is None:
                    await interaction.response.send_message(
                        "Il colore va scritto come #RRGGBB, oppure «predefinito».", ephemeral=True
                    )
                    return
                campi["color"] = int(esadecimale[1:], 16)
        if testo_guida is not None:  # RUO-086
            campi["placeholder"] = testo_guida
        if risposta is not None:  # RUO-082
            campi["reply_text"] = risposta
        if avvisa is not None:  # RUO-081
            campi["notify"] = avvisa
        if voce_azzera is not None:  # RUO-087
            if voce_azzera and menu.mode != "select":
                await interaction.response.send_message("La voce serve solo alle tendine.", ephemeral=True)
                return
            if voce_azzera and await role_menu_repo.count_options(menu_id) >= 25:
                await interaction.response.send_message(
                    "La tendina ha già 25 opzioni: toglierne una per fare posto.", ephemeral=True
                )
                return
            campi["reset_option"] = voce_azzera
        if massimo is not None:  # RUO-062
            campi["max_selectable"] = massimo or None
        if minimo is not None:  # RUO-063
            campi["min_roles"] = minimo or None
        nuovo_max = campi.get("max_selectable", menu.max_selectable)
        nuovo_min = campi.get("min_roles", menu.min_roles)
        if nuovo_max and nuovo_min and nuovo_min > nuovo_max:
            await interaction.response.send_message("Il minimo non può superare il massimo.", ephemeral=True)
            return
        if titolo is not None:
            campi["title"] = titolo
        if descrizione is not None:
            campi["description"] = descrizione
        if comportamento is not None or durata_minuti is not None:
            nuovo = comportamento or menu.behavior
            durata = durata_minuti or (menu.temp_seconds // 60 if menu.temp_seconds else None)
            errore = _errore_comportamento(menu.mode, nuovo, durata)
            if errore is not None:
                await interaction.response.send_message(errore, ephemeral=True)
                return
            if durata_minuti is not None and nuovo != "temp":
                await interaction.response.send_message(
                    await testo_per(interaction, "rolemenus_la_durata_serve_solo_al"), ephemeral=True
                )
                return
            campi["behavior"] = nuovo
            campi["temp_seconds"] = durata * 60 if nuovo == "temp" and durata else None
            if menu.mode == "select" and nuovo == "unique":
                campi["max_selectable"] = 1
        if not campi:
            await interaction.response.send_message(await testo_per(interaction, "customcomman_non_hai_indicato_nulla_da"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        async with self._blocco_menu(menu_id):
            menu = await role_menu_repo.get_menu(menu_id)
            if menu is None:
                await interaction.followup.send(await testo_per(interaction, "rolemenus_questo_menu_non_esiste_piu"), ephemeral=True)
                return
            opzioni = await role_menu_repo.get_options(menu_id)
            if opzioni:
                # Prima il messaggio, poi il database: se Discord rifiuta, il menu resta com'era.
                try:
                    await self._pubblica_menu(guild, dataclasses.replace(menu, **campi), opzioni)
                except MenuNonPubblicabile as errore:
                    await interaction.followup.send(
                        f"Il menu non è stato modificato: il messaggio non si aggiorna. {errore}", ephemeral=True
                    )
                    return
            await role_menu_repo.update_menu(menu_id, **campi)
        await interaction.followup.send(await testo_per(interaction, "rolemenus_menu_aggiornato"), ephemeral=True)

    @comando_di_gruppo(
        "admin-ruoli",
        nome="accesso",
        descrizione="Limita un menu a certi ruoli o escludine altri.",
        sottogruppo=SOTTOGRUPPI["admin-ruoli menu"],
    )
    @app_commands.describe(
        menu_id="ID del menu",
        ruolo="Il ruolo da aggiungere o togliere (non serve per svuotare)",
        elenco="Ammessi: solo chi ha uno di questi ruoli. Esclusi: chi ne ha uno non può usare il menu",
        azione="Aggiungere o togliere il ruolo dall'elenco",
    )
    @app_commands.choices(
        elenco=[app_commands.Choice(name="ammesso", value="ammesso"), app_commands.Choice(name="escluso", value="escluso")],
        azione=[app_commands.Choice(name=n, value=n) for n in ("aggiungi", "togli", "svuota")],
    )
    async def access_cmd(
        self,
        interaction: discord.Interaction,
        menu_id: int,
        elenco: str,
        ruolo: discord.Role | None = None,
        azione: str = "aggiungi",
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return
        menu = await role_menu_repo.get_menu(menu_id)
        if menu is None or menu.guild_id != guild.id:
            await interaction.response.send_message(
                await testo_per(interaction, "rolemenus_nessun_role_menu_trovato_con"), ephemeral=True
            )
            return
        ammessi, esclusi = list(menu.allowed_role_ids), list(menu.excluded_role_ids)
        lista = ammessi if elenco == "ammesso" else esclusi
        if azione == "svuota":  # RUO-068
            lista.clear()
        elif ruolo is None:
            await interaction.response.send_message("Scegli un ruolo.", ephemeral=True)
            return
        elif azione == "aggiungi":
            if ruolo.id not in lista:
                if len(lista) >= MAX_RUOLI_ACCESSO:
                    await interaction.response.send_message(
                        await testo_per(interaction, "rolemenus_elenco_ha_gia_ruoli_togline", v1=MAX_RUOLI_ACCESSO), ephemeral=True
                    )
                    return
                lista.append(ruolo.id)
        elif ruolo.id in lista:
            lista.remove(ruolo.id)
        await role_menu_repo.set_access_lists(menu_id, ammessi, esclusi)
        await interaction.response.send_message(
            await testo_per(interaction, "rolemenus_ruoli_ammessi_esclusi", v1=len(ammessi), v2=len(esclusi)), ephemeral=True
        )

    async def _stacca_messaggio(self, guild: discord.Guild, menu: RoleMenu) -> None:
        """RUO-079: toglie bottoni, tendina e reazioni del bot dal messaggio, che resta (best effort)."""
        channel = guild.get_channel(menu.channel_id)
        if menu.message_id is None or not isinstance(channel, discord.TextChannel):
            return
        try:
            message = await channel.fetch_message(menu.message_id)
            if menu.external:  # messaggio di altri: si tolgono solo le reazioni del bot
                for reazione in list(message.reactions):
                    if reazione.me:
                        await message.remove_reaction(reazione.emoji, guild.me)
                return
            await message.edit(view=None)
            if menu.mode == "reaction":
                await message.clear_reactions()
        except discord.HTTPException:
            logger.info("Menu %s: messaggio non staccato del tutto nel server %s.", menu.id, guild.id)

    @comando_di_gruppo(
        "admin-ruoli",
        nome="opzione",
        descrizione="Cambia emoji, etichetta, descrizione, colore o posto di un'opzione di un menu.",
        sottogruppo=SOTTOGRUPPI["admin-ruoli menu"],
    )
    @app_commands.describe(
        menu_id="ID del menu",
        ruolo="Il ruolo dell'opzione da cambiare",
        emoji="Nuova emoji",
        etichetta="Nuova etichetta (massimo 80 caratteri)",
        descrizione="Nuova riga sotto l'opzione nella tendina (massimo 100 caratteri)",
        colore="Nuovo colore del bottone",
        posto="Nuovo posto nel menu (1 = primo)",
    )
    @app_commands.choices(colore=[app_commands.Choice(name=n, value=n) for n in STILI_BOTTONE])
    async def option_edit_cmd(
        self,
        interaction: discord.Interaction,
        menu_id: int,
        ruolo: discord.Role,
        emoji: app_commands.Range[str, 1, 60] | None = None,
        etichetta: app_commands.Range[str, 1, 80] | None = None,
        descrizione: app_commands.Range[str, 0, 100] | None = None,
        colore: str | None = None,
        posto: app_commands.Range[int, 1, 25] | None = None,
    ) -> None:
        """RUO-076 (emoji, etichetta, ...) e RUO-077 (posto): il messaggio si aggiorna prima, il database dopo."""
        guild = interaction.guild
        if guild is None:
            return
        menu = await role_menu_repo.get_menu(menu_id)
        if menu is None or menu.guild_id != guild.id:
            await interaction.response.send_message(
                await testo_per(interaction, "rolemenus_nessun_role_menu_trovato_con"), ephemeral=True
            )
            return
        campi: dict = {}
        if emoji is not None:
            if not valida_emoji(emoji):
                await interaction.response.send_message(
                    await testo_per(interaction, "rolemenus_quella_non_un_emoji_valida"), ephemeral=True
                )
                return
            personalizzata = id_emoji_personalizzata(emoji)
            if personalizzata is not None and self.bot.get_emoji(personalizzata) is None:
                await interaction.response.send_message(
                    await testo_per(interaction, "rolemenus_non_vedo_quell_emoji_personalizzata"), ephemeral=True
                )
                return
            campi["emoji"] = emoji
        if etichetta is not None:
            campi["label"] = etichetta
        if descrizione is not None:
            campi["description"] = descrizione
        if colore is not None:
            campi["button_style"] = _STILE_DA_SCELTA[colore]
        if not campi and posto is None:
            await interaction.response.send_message(await testo_per(interaction, "customcomman_non_hai_indicato_nulla_da"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        async with self._blocco_menu(menu_id):
            opzioni = await role_menu_repo.get_options(menu_id)
            if ruolo.id not in {o.role_id for o in opzioni}:
                await interaction.followup.send("Quel ruolo non è in questo menu.", ephemeral=True)
                return
            nuove = [dataclasses.replace(o, **campi) if o.role_id == ruolo.id else o for o in opzioni]
            if posto is not None:
                ordine = sposta_ruolo([o.role_id for o in nuove], ruolo.id, posto)
                nuove = sorted(nuove, key=lambda o: ordine.index(o.role_id))
            try:
                await self._pubblica_menu(guild, menu, nuove)
            except MenuNonPubblicabile as errore:
                await interaction.followup.send(f"Il menu non è stato modificato. {errore}", ephemeral=True)
                return
            if campi:
                await role_menu_repo.update_option(menu_id, ruolo.id, **campi)
            if posto is not None:
                await role_menu_repo.set_positions(menu_id, [o.role_id for o in nuove])
        await interaction.followup.send(await testo_per(interaction, "rolemenus_menu_aggiornato"), ephemeral=True)

    @comando_di_gruppo(
        "admin-ruoli",
        nome="svuota",
        descrizione="Elimina tutti i menu di ruoli del server, o di un canale.",
        sottogruppo=SOTTOGRUPPI["admin-ruoli menu"],
    )
    @app_commands.describe(
        canale="Solo i menu di questo canale (se vuoto: tutto il server)",
        conferma="Scrivi sì per eliminare davvero; senza, vedi solo quanti sono",
    )
    async def purge_cmd(
        self, interaction: discord.Interaction, canale: discord.TextChannel | None = None, conferma: bool = False
    ) -> None:
        """RUO-080: elimina i menu in blocco, con conferma, una sola operazione per server e una pausa tra un menu e l'altro."""
        guild = interaction.guild
        if guild is None:
            return
        menu = [m for m in await role_menu_repo.list_menus_for_guild(guild.id) if canale is None or m.channel_id == canale.id]
        if not conferma or not menu:
            await interaction.response.send_message(
                f"Menu da eliminare: {len(menu)}. Per farlo davvero ripeti il comando con `conferma: sì`.", ephemeral=True
            )
            return
        if guild.id in self._svuotamenti:
            await interaction.response.send_message("Un'eliminazione è già in corso.", ephemeral=True)
            return
        self._svuotamenti.add(guild.id)
        await interaction.response.defer(ephemeral=True)
        eliminati = rimasti = 0
        try:
            for m in menu:
                async with self._blocco_menu(m.id):
                    if await self._elimina_menu(guild, m):
                        eliminati += 1
                    else:
                        rimasti += 1  # il menu non c'è più, il messaggio non si è lasciato cancellare
                await asyncio.sleep(PAUSA_SVUOTA_SECONDI)
        finally:
            self._svuotamenti.discard(guild.id)
        await interaction.followup.send(
            f"Menu eliminati: {eliminati + rimasti}. Messaggi non cancellati: {rimasti}.", ephemeral=True
        )

    @comando_di_gruppo(
        "admin-ruoli",
        nome="sposta",
        descrizione="Aggancia o sposta un menu a reazioni su un messaggio già scritto.",
        sottogruppo=SOTTOGRUPPI["admin-ruoli menu"],
    )
    @app_commands.describe(
        menu_id="ID del menu a reazioni",
        messaggio_id="ID del messaggio (tasto destro > Copia ID messaggio)",
        canale="Il canale del messaggio (se non lo indichi, quello del menu)",
    )
    async def move_cmd(
        self,
        interaction: discord.Interaction,
        menu_id: int,
        messaggio_id: app_commands.Range[str, 15, 22],
        canale: discord.TextChannel | None = None,
    ) -> None:
        """RUO-072, RUO-073: il menu a reazioni passa a un altro messaggio; se è di altri il bot non lo modifica."""
        guild = interaction.guild
        if guild is None or not messaggio_id.isdigit():
            if guild is not None:
                await interaction.response.send_message("L'ID del messaggio sono solo cifre.", ephemeral=True)
            return
        menu = await role_menu_repo.get_menu(menu_id)
        if menu is None or menu.guild_id != guild.id:
            await interaction.response.send_message(
                await testo_per(interaction, "rolemenus_nessun_role_menu_trovato_con"), ephemeral=True
            )
            return
        if menu.mode != "reaction":
            await interaction.response.send_message(
                "Bottoni e tendina vivono solo sui messaggi del bot: si agganciano solo i menu a reazioni.", ephemeral=True
            )
            return
        destinazione = canale or guild.get_channel(menu.channel_id)
        if not isinstance(destinazione, discord.TextChannel):
            await interaction.response.send_message(
                await testo_per(interaction, "rolemenus_scegli_un_canale_di_testo"), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        async with self._blocco_menu(menu_id):
            menu = await role_menu_repo.get_menu(menu_id)
            if menu is None:
                await interaction.followup.send(await testo_per(interaction, "rolemenus_questo_menu_non_esiste_piu"), ephemeral=True)
                return
            try:
                nuovo = await destinazione.fetch_message(int(messaggio_id))
            except discord.HTTPException:
                await interaction.followup.send("Non trovo quel messaggio in quel canale.", ephemeral=True)
                return
            if await role_menu_repo.get_menu_by_message(guild.id, nuovo.id) is not None:
                await interaction.followup.send("Quel messaggio ha già un menu.", ephemeral=True)
                return
            opzioni = await role_menu_repo.get_options(menu_id)
            vecchio = menu
            esterno = nuovo.author.id != guild.me.id
            spostato = dataclasses.replace(
                menu, channel_id=destinazione.id, message_id=nuovo.id, external=esterno
            )
            try:
                await self._pubblica_menu(guild, spostato, opzioni)
            except MenuNonPubblicabile as errore:
                await interaction.followup.send(f"Il menu non è stato spostato. {errore}", ephemeral=True)
                return
            await role_menu_repo.update_menu(menu_id, channel_id=destinazione.id, message_id=nuovo.id, external=esterno)
            if vecchio.message_id != nuovo.id:  # il vecchio messaggio perde le reazioni del bot (o si cancella se era suo)
                await self._stacca_o_cancella(guild, vecchio)
        await interaction.followup.send("Menu spostato.", ephemeral=True)

    async def _stacca_o_cancella(self, guild: discord.Guild, menu: RoleMenu) -> None:
        """Il messaggio vecchio di un menu spostato: se era del bot si cancella, se di altri si tolgono solo le reazioni del bot."""
        channel = guild.get_channel(menu.channel_id)
        if menu.message_id is None or not isinstance(channel, discord.TextChannel):
            return
        if menu.external:
            await self._stacca_messaggio(guild, menu)
            return
        try:
            await (await channel.fetch_message(menu.message_id)).delete()
        except discord.HTTPException:
            logger.info("Vecchio messaggio del menu %s non cancellato nel server %s.", menu.id, guild.id)

    @comando_di_gruppo(
        "admin-ruoli",
        nome="ripara",
        descrizione="Rimetti le reazioni del bot su un menu a reazioni se qualcuno le ha tolte.",
        sottogruppo=SOTTOGRUPPI["admin-ruoli menu"],
    )
    @app_commands.describe(menu_id="ID del menu a reazioni")
    async def repair_cmd(self, interaction: discord.Interaction, menu_id: int) -> None:
        """RUO-074: una richiesta per reazione, con una pausa; una sola riparazione alla volta per menu."""
        guild = interaction.guild
        if guild is None:
            return
        menu = await role_menu_repo.get_menu(menu_id)
        if menu is None or menu.guild_id != guild.id:
            await interaction.response.send_message(
                await testo_per(interaction, "rolemenus_nessun_role_menu_trovato_con"), ephemeral=True
            )
            return
        if menu.mode != "reaction":
            await interaction.response.send_message("Serve solo ai menu a reazioni.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        async with self._blocco_menu(menu_id):
            try:
                await self._pubblica_menu(guild, menu, await role_menu_repo.get_options(menu_id))
            except MenuNonPubblicabile as errore:
                await interaction.followup.send(f"Non riesco a ripararlo. {errore}", ephemeral=True)
                return
        await interaction.followup.send("Reazioni rimesse a posto.", ephemeral=True)

    @comando_di_gruppo(
        "admin-ruoli",
        nome="elimina",
        descrizione="Elimina un role menu.",
        sottogruppo=SOTTOGRUPPI["admin-ruoli menu"],
    )
    @app_commands.describe(
        menu_id="ID del menu da eliminare",
        tieni_messaggio="Stacca il menu ma lascia il messaggio, senza più bottoni né reazioni che funzionano",
    )
    async def delete_cmd(
        self, interaction: discord.Interaction, menu_id: int, tieni_messaggio: bool = False
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return

        menu = await role_menu_repo.get_menu(menu_id)
        if menu is None or menu.guild_id != guild.id:
            await interaction.response.send_message(
                await testo_per(interaction, "rolemenus_nessun_role_menu_trovato_con"),
                ephemeral=True,
            )
            return

        if tieni_messaggio:  # RUO-079
            await interaction.response.defer(ephemeral=True)
            await self._stacca_messaggio(guild, menu)
            await role_menu_repo.delete_menu(menu.id)
            await interaction.followup.send("Menu staccato: il messaggio è rimasto, ma non dà più ruoli.", ephemeral=True)
            return
        cancellato = await self._elimina_menu(guild, menu)
        if not cancellato:
            await interaction.response.send_message(
                await testo_per(interaction, "rolemenus_role_menu_eliminato_dal_database"),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(await testo_per(interaction, "rolemenus_role_menu_eliminato"), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_ROLE_MENUS,
            display_name="Role Menus",
            category="utility",
            description="Reaction/Button/Select menu per l'auto-assegnazione dei ruoli.",
            premium_capable=False,
        )
    )
    cog = RoleMenuCog(bot)
    await bot.add_cog(cog)
    scheduler.register_handler(ROLEMENU_TEMP_ACTION_TYPE, cog.handle_rolemenu_temp)

    # Ricostruzione delle View dinamiche persistenti PER-MESSAGGIO,
    # per OGNI menu bottone/select esistente su qualunque server, ad
    # ogni avvio — stesso principio delle view "a bottone fisso" già
    # in uso altrove (bot.add_view() va richiamato ad ogni avvio, non
    # solo alla prima pubblicazione), applicato qui al caso dinamico
    # per-messaggio tramite il parametro message_id di add_view().
    for mode in ("button", "select"):
        menus = await role_menu_repo.list_menus_by_mode(mode)
        for menu in menus:
            options = await role_menu_repo.get_options(menu.id)
            if not options:
                continue  # menu rimasto vuoto: niente View da registrare
            view = await cog._build_view_for_menu(menu, options)
            if view is not None:
                bot.add_view(view, message_id=menu.message_id)
