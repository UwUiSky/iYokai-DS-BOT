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

# DA FARE (issue #85, fase F9): NF-14, Modalità dei reaction roles. Vedi
#   revisione/02-piano/NUOVE_FUNZIONI.md.

from __future__ import annotations

import asyncio
import logging
import weakref

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.blacklist_repo import blacklist_repo
from core.repositories.role_menu_repo import RoleMenu, RoleMenuOption, role_menu_repo
from core.lista_limiti_logic import dividi_in_blocchi
from core.role_menu_logic import (
    can_add_option,
    compute_select_sync,
    compute_toggle_action,
    id_emoji_personalizzata,
    valida_emoji,
)
from core.role_safety import check_role_assignable
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.role_menus")

MODULE_ROLE_MENUS = "role_menus"

BUTTON_CUSTOM_ID_PREFIX = "iyokai_rolemenu_btn"
SELECT_CUSTOM_ID_PREFIX = "iyokai_rolemenu_select"


def _build_embed(menu: RoleMenu, options: list[RoleMenuOption]) -> discord.Embed:
    embed = discord.Embed(
        title=menu.title[:256],
        description=(menu.description or None) and menu.description[:2000],
        color=discord.Color.blurple(),
    )
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


class MenuNonPubblicabile(Exception):
    """Il messaggio del menu non si può pubblicare o aggiornare; il testo è per l'admin."""


_SG_RUOLI = ("ruoli", "Ruoli: ruoli-premio per livello e menu di ruoli")


class RoleMenuCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Un blocco per menu: due /menu-aggiungi insieme si mettono in fila
        # (altrimenti una delle due opzioni sparisce o escono due messaggi).
        self._blocchi_menu: "weakref.WeakValueDictionary[int, asyncio.Lock]" = (
            weakref.WeakValueDictionary()
        )

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
                style=discord.ButtonStyle.secondary,
                custom_id=f"{BUTTON_CUSTOM_ID_PREFIX}:{menu_id}:{opt.role_id}",
            )
            button.callback = self._make_button_callback(menu_id, opt.role_id)
            view.add_item(button)
        return view

    def _build_select_view(
        self, menu_id: int, options: list[RoleMenuOption], max_selectable: int | None
    ) -> discord.ui.View:
        view = BaseView(timeout=None)
        select_options = [
            discord.SelectOption(
                label=(opt.label or "Role")[:100], value=str(opt.role_id), emoji=opt.emoji
            )
            for opt in options
        ]
        limite = max_selectable if max_selectable else len(select_options)
        limite = max(1, min(limite, len(select_options)))

        select: discord.ui.Select = discord.ui.Select(
            custom_id=f"{SELECT_CUSTOM_ID_PREFIX}:{menu_id}",
            placeholder="Choose your roles...",
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
            return self._build_select_view(menu.id, options, menu.max_selectable)
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
                        await message.add_reaction(opt.emoji)
                        reazioni_aggiunte.append(opt.emoji)
            except discord.HTTPException as errore:
                await self._annulla_pubblicazione(message, nuovo, reazioni_aggiunte)
                raise MenuNonPubblicabile(
                    "Discord non accetta una delle emoji del menu come reazione."
                ) from errore

        if not nuovo:
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
            await interaction.response.send_message(
                "This feature is not active on this server.", ephemeral=True
            )
            return

        role = guild.get_role(role_id)
        if role is None:
            await interaction.response.send_message(
                "This role no longer exists.", ephemeral=True
            )
            return

        ha_il_ruolo = role in interaction.user.roles
        if ha_il_ruolo:
            # toggle=False: il bottone dà il ruolo ma non lo toglie.
            menu = await role_menu_repo.get_menu(menu_id)
            if menu is not None and not menu.toggle:
                await interaction.response.send_message(
                    f"Hai già il ruolo {role.mention}: da questo menu non si può togliere.",
                    ephemeral=True,
                )
                return

        azione = compute_toggle_action(ha_il_ruolo)

        # SEC-4/SEC-17: ricontrolla il ruolo solo quando lo si sta per
        # ASSEGNARE (self_service=True) — rimuoverlo resta sempre
        # permesso, non è un'escalation di permessi.
        if azione == "add":
            motivo_rifiuto = check_role_assignable(guild, role, guild.me, self_service=True)
            if motivo_rifiuto is not None:
                await interaction.response.send_message(motivo_rifiuto, ephemeral=True)
                return

        try:
            if azione == "add":
                await interaction.user.add_roles(role, reason="Role menu")
            else:
                await interaction.user.remove_roles(role, reason="Role menu")
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to manage that role.", ephemeral=True
            )
            return
        except discord.HTTPException:
            logger.warning("Errore Discord assegnando il ruolo %s nel server %s.", role_id, guild.id)
            await interaction.response.send_message(
                "Discord ha dato un errore: riprova tra poco.", ephemeral=True
            )
            return

        verbo = "added" if azione == "add" else "removed"
        await interaction.response.send_message(f"Role {role.mention} {verbo}.", ephemeral=True)

    async def _handle_select(
        self, interaction: discord.Interaction, menu_id: int, select: discord.ui.Select
    ) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_ROLE_MENUS):
            await interaction.response.send_message(
                "This feature is not active on this server.", ephemeral=True
            )
            return

        options = await role_menu_repo.get_options(menu_id)
        menu_role_ids = {opt.role_id for opt in options}
        selected_role_ids = {int(v) for v in select.values}
        current_role_ids = {r.id for r in interaction.user.roles}

        da_aggiungere, da_rimuovere = compute_select_sync(
            current_role_ids, menu_role_ids, selected_role_ids
        )

        ruoli_da_aggiungere = [guild.get_role(rid) for rid in da_aggiungere]
        ruoli_da_aggiungere = [r for r in ruoli_da_aggiungere if r is not None]
        # SEC-4/SEC-17: assegnazione self-service, ricontrolla ogni
        # ruolo — un ruolo diventato pericoloso viene saltato senza
        # bloccare l'aggiornamento degli altri.
        ruoli_da_aggiungere = [
            r for r in ruoli_da_aggiungere
            if check_role_assignable(guild, r, guild.me, self_service=True) is None
        ]
        ruoli_da_rimuovere = [guild.get_role(rid) for rid in da_rimuovere]
        ruoli_da_rimuovere = [r for r in ruoli_da_rimuovere if r is not None]

        try:
            if ruoli_da_aggiungere:
                await interaction.user.add_roles(*ruoli_da_aggiungere, reason="Role menu")
            if ruoli_da_rimuovere:
                await interaction.user.remove_roles(*ruoli_da_rimuovere, reason="Role menu")
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to manage one or more of those roles.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            logger.warning("Errore Discord aggiornando i ruoli del menu %s.", menu_id)
            await interaction.response.send_message(
                "Discord ha dato un errore: riprova tra poco.", ephemeral=True
            )
            return

        await interaction.response.send_message("Your roles have been updated.", ephemeral=True)

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
        if guild is None:
            return
        role = guild.get_role(option.role_id)
        if role is None:
            return

        # SEC-4/SEC-17: assegnazione self-service via reazione.
        if check_role_assignable(guild, role, guild.me, self_service=True) is not None:
            return

        try:
            await payload.member.add_roles(role, reason="Role menu (reaction)")
        except discord.HTTPException:  # comprende Forbidden
            logger.warning(
                "Permessi insufficienti per assegnare il ruolo via reazione "
                "nel server %s.",
                payload.guild_id,
            )

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
        if menu is None or menu.mode != "reaction" or not menu.toggle:
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
        role = guild.get_role(option.role_id)
        if role is None:
            return

        try:
            await member.remove_roles(role, reason="Role menu (reaction removed)")
        except discord.HTTPException:  # comprende Forbidden
            logger.warning(
                "Permessi insufficienti per rimuovere il ruolo via reazione "
                "nel server %s.",
                payload.guild_id,
            )

    # ================================================================
    # Comandi
    # ================================================================

    @comando_di_gruppo(
        "gestione",
        nome="menu-crea",
        descrizione="Crea un nuovo role menu.",
        sottogruppo=_SG_RUOLI,
    )
    @app_commands.describe(
        title="Titolo del menu",
        mode="Modalità di interazione",
        description="Descrizione facoltativa",
        channel="Canale dove pubblicare il menu (default: questo canale)",
        toggle="Ri-cliccare/reagire toglie il ruolo? (solo bottone/reazione)",
        max_selectable="Quante opzioni si possono scegliere insieme (solo select)",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Reaction", value="reaction"),
            app_commands.Choice(name="Button", value="button"),
            app_commands.Choice(name="Select menu", value="select"),
        ]
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
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                "Scegli un canale di testo valido.", ephemeral=True
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
        )

        await interaction.response.send_message(
            f"Role menu creato (ID `{menu_id}`, modalità **{mode.name}**). "
            f"Usa `/gestione ruoli menu-aggiungi` per aggiungere le opzioni — il "
            f"messaggio verrà pubblicato/aggiornato automaticamente ad "
            f"ogni opzione aggiunta.",
            ephemeral=True,
        )

    @comando_di_gruppo(
        "gestione",
        nome="menu-aggiungi",
        descrizione="Aggiungi un'opzione a un role menu.",
        sottogruppo=_SG_RUOLI,
    )
    @app_commands.describe(
        menu_id="ID del menu (mostrato da /gestione ruoli menu-crea)",
        role="Il ruolo da assegnare",
        emoji="Emoji (obbligatoria per reaction/button)",
        label="Etichetta del bottone/opzione (obbligatoria per button/select)",
    )
    async def add_option_cmd(
        self,
        interaction: discord.Interaction,
        menu_id: int,
        role: discord.Role,
        emoji: app_commands.Range[str, 1, 60] | None = None,
        label: app_commands.Range[str, 1, 80] | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return

        menu = await role_menu_repo.get_menu(menu_id)
        if menu is None or menu.guild_id != guild.id:
            await interaction.response.send_message(
                "Nessun role menu trovato con questo ID in questo server.",
                ephemeral=True,
            )
            return

        if menu.mode in ("reaction", "button") and emoji is None:
            await interaction.response.send_message(
                f"La modalità **{menu.mode}** richiede un'emoji.", ephemeral=True
            )
            return
        if menu.mode in ("button", "select") and label is None:
            await interaction.response.send_message(
                f"La modalità **{menu.mode}** richiede un'etichetta.", ephemeral=True
            )
            return

        conteggio = await role_menu_repo.count_options(menu_id)
        if not can_add_option(conteggio, menu.mode):
            await interaction.response.send_message(
                f"Limite di opzioni raggiunto per la modalità **{menu.mode}**.",
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
                    "Quella non è un'emoji valida: scrivi un'emoji (🎮) oppure una "
                    "personalizzata nel formato <:nome:id>.",
                    ephemeral=True,
                )
                return
            id_personalizzata = id_emoji_personalizzata(emoji)
            if id_personalizzata is not None and self.bot.get_emoji(id_personalizzata) is None:
                await interaction.response.send_message(
                    "Non vedo quell'emoji personalizzata: il bot deve essere nel server "
                    "a cui appartiene.",
                    ephemeral=True,
                )
                return

        await interaction.response.defer(ephemeral=True)
        async with self._blocco_menu(menu_id):
            # Dentro il blocco si rilegge tutto: un altro comando potrebbe aver
            # appena pubblicato il messaggio o cambiato le opzioni.
            menu = await role_menu_repo.get_menu(menu_id)
            if menu is None:
                await interaction.followup.send("Questo menu non esiste più.", ephemeral=True)
                return
            esistenti = [
                o for o in await role_menu_repo.get_options(menu_id) if o.role_id != role.id
            ]
            if not can_add_option(len(esistenti), menu.mode):
                await interaction.followup.send(
                    f"Limite di opzioni raggiunto per la modalità **{menu.mode}**.",
                    ephemeral=True,
                )
                return
            nuova = RoleMenuOption(
                id=0, menu_id=menu_id, role_id=role.id, emoji=emoji, label=label,
                position=len(esistenti),
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
            await role_menu_repo.add_option(menu_id, role.id, emoji, label)

        await interaction.followup.send(
            f"Opzione aggiunta: {role.mention}.", ephemeral=True
        )

    @comando_di_gruppo(
        "gestione",
        nome="menu-togli",
        descrizione="Rimuovi un'opzione da un role menu.",
        sottogruppo=_SG_RUOLI,
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
                "Nessun role menu trovato con questo ID in questo server.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        async with self._blocco_menu(menu_id):
            menu = await role_menu_repo.get_menu(menu_id)
            if menu is None:
                await interaction.followup.send("Questo menu non esiste più.", ephemeral=True)
                return
            opzioni = await role_menu_repo.get_options(menu_id)
            if not any(o.role_id == role.id for o in opzioni):
                await interaction.followup.send(
                    "Quel ruolo non fa parte di questo menu.", ephemeral=True
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
        await interaction.followup.send(f"Opzione rimossa: {role.mention}.", ephemeral=True)

    async def _elimina_menu(self, guild: discord.Guild, menu: RoleMenu) -> bool:
        """
        Elimina il menu dal database e prova a cancellare il messaggio.
        True se il messaggio non c'è più (cancellato, già sparito o mai
        pubblicato); False se Discord non ha permesso di cancellarlo.
        """
        messaggio_sparito = True
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
        "gestione",
        nome="menu-elimina",
        descrizione="Elimina un role menu.",
        sottogruppo=_SG_RUOLI,
    )
    @app_commands.describe(menu_id="ID del menu da eliminare")
    async def delete_cmd(self, interaction: discord.Interaction, menu_id: int) -> None:
        guild = interaction.guild
        if guild is None:
            return

        menu = await role_menu_repo.get_menu(menu_id)
        if menu is None or menu.guild_id != guild.id:
            await interaction.response.send_message(
                "Nessun role menu trovato con questo ID in questo server.",
                ephemeral=True,
            )
            return

        cancellato = await self._elimina_menu(guild, menu)
        if not cancellato:
            await interaction.response.send_message(
                "Role menu eliminato dal database, ma non sono riuscito a cancellare il "
                "messaggio: cancellalo a mano.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message("Role menu eliminato.", ephemeral=True)


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
