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

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.premium import PremiumModule, registry
from core.repositories.role_menu_repo import RoleMenu, RoleMenuOption, role_menu_repo
from core.role_menu_logic import can_add_option, compute_select_sync, compute_toggle_action

logger = logging.getLogger("iyokai.role_menus")

MODULE_ROLE_MENUS = "role_menus"

BUTTON_CUSTOM_ID_PREFIX = "iyokai_rolemenu_btn"
SELECT_CUSTOM_ID_PREFIX = "iyokai_rolemenu_select"


def _build_embed(menu: RoleMenu, options: list[RoleMenuOption]) -> discord.Embed:
    embed = discord.Embed(
        title=menu.title,
        description=menu.description or None,
        color=discord.Color.blurple(),
    )
    if not options:
        embed.add_field(name="—", value="No roles configured yet.", inline=False)
    elif menu.mode == "reaction":
        righe = [
            f"{opt.emoji or '❓'} — <@&{opt.role_id}>" for opt in options
        ]
        embed.add_field(name="React to get a role", value="\n".join(righe), inline=False)
    else:
        righe = [f"• {opt.label or '(no label)'} — <@&{opt.role_id}>" for opt in options]
        embed.add_field(name="Available roles", value="\n".join(righe), inline=False)
    return embed


class RoleMenuCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ================================================================
    # Costruzione delle view dinamiche
    # ================================================================
    def _build_button_view(self, menu_id: int, options: list[RoleMenuOption]) -> discord.ui.View:
        view = discord.ui.View(timeout=None)
        for opt in options:
            button: discord.ui.Button = discord.ui.Button(
                label=opt.label or "Role",
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
        view = discord.ui.View(timeout=None)
        select_options = [
            discord.SelectOption(
                label=opt.label or "Role", value=str(opt.role_id), emoji=opt.emoji
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

    async def _refresh_menu_message(self, guild: discord.Guild, menu: RoleMenu) -> None:
        """
        Ripubblica o aggiorna il messaggio del menu dopo una modifica
        alle opzioni (aggiunta/rimozione), e per la modalità bottone/
        select registra la View aggiornata come persistente per quel
        messaggio specifico.
        """
        channel = guild.get_channel(menu.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        options = await role_menu_repo.get_options(menu.id)
        embed = _build_embed(menu, options)
        view = await self._build_view_for_menu(menu, options)

        if menu.message_id is None:
            message = await channel.send(embed=embed, view=view)
            await role_menu_repo.set_menu_message(menu.id, message.id)
            message_id = message.id
        else:
            try:
                message = await channel.fetch_message(menu.message_id)
                await message.edit(embed=embed, view=view)
                message_id = menu.message_id
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.warning(
                    "Impossibile aggiornare il messaggio del role menu %s (server %s).",
                    menu.id,
                    guild.id,
                )
                return

        if menu.mode == "reaction":
            try:
                esistenti = {str(r.emoji) for r in message.reactions}
                for opt in options:
                    if opt.emoji and opt.emoji not in esistenti:
                        await message.add_reaction(opt.emoji)
            except discord.HTTPException:
                logger.warning(
                    "Impossibile aggiungere una reazione al role menu %s "
                    "(emoji non valida?).",
                    menu.id,
                )
        elif view is not None:
            self.bot.add_view(view, message_id=message_id)

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

        azione = compute_toggle_action(role in interaction.user.roles)
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

        await interaction.response.send_message("Your roles have been updated.", ephemeral=True)

    # ================================================================
    # Modalità reaction
    # ================================================================
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.member is None or payload.member.bot:
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

        try:
            await payload.member.add_roles(role, reason="Role menu (reaction)")
        except discord.Forbidden:
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
        except discord.Forbidden:
            logger.warning(
                "Permessi insufficienti per rimuovere il ruolo via reazione "
                "nel server %s.",
                payload.guild_id,
            )

    # ================================================================
    # Comandi
    # ================================================================
    rolemenu_group = app_commands.Group(
        name="rolemenu", description="Crea e gestisci i menu di assegnazione ruoli."
    )

    @rolemenu_group.command(name="create", description="[Admin] Crea un nuovo role menu.")
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
    @app_commands.checks.has_permissions(manage_roles=True)
    async def create_cmd(
        self,
        interaction: discord.Interaction,
        title: str,
        mode: app_commands.Choice[str],
        description: str = "",
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
            f"Usa `/rolemenu add-option` per aggiungere le opzioni — il "
            f"messaggio verrà pubblicato/aggiornato automaticamente ad "
            f"ogni opzione aggiunta.",
            ephemeral=True,
        )

    @rolemenu_group.command(
        name="add-option", description="[Admin] Aggiungi un'opzione a un role menu."
    )
    @app_commands.describe(
        menu_id="ID del menu (mostrato da /rolemenu create)",
        role="Il ruolo da assegnare",
        emoji="Emoji (obbligatoria per reaction/button)",
        label="Etichetta del bottone/opzione (obbligatoria per button/select)",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def add_option_cmd(
        self,
        interaction: discord.Interaction,
        menu_id: int,
        role: discord.Role,
        emoji: str | None = None,
        label: str | None = None,
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

        await interaction.response.defer(ephemeral=True)
        await role_menu_repo.add_option(menu_id, role.id, emoji, label)
        await self._refresh_menu_message(guild, menu)

        await interaction.followup.send(
            f"Opzione aggiunta: {role.mention}.", ephemeral=True
        )

    @rolemenu_group.command(
        name="remove-option", description="[Admin] Rimuovi un'opzione da un role menu."
    )
    @app_commands.describe(menu_id="ID del menu", role="Il ruolo da rimuovere dal menu")
    @app_commands.checks.has_permissions(manage_roles=True)
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

        rimosso = await role_menu_repo.remove_option(menu_id, role.id)
        if not rimosso:
            await interaction.response.send_message(
                "Quel ruolo non fa parte di questo menu.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        await self._refresh_menu_message(guild, menu)
        await interaction.followup.send(f"Opzione rimossa: {role.mention}.", ephemeral=True)

    @rolemenu_group.command(name="delete", description="[Admin] Elimina un role menu.")
    @app_commands.describe(menu_id="ID del menu da eliminare")
    @app_commands.checks.has_permissions(manage_roles=True)
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

        if menu.message_id is not None:
            channel = guild.get_channel(menu.channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.fetch_message(menu.message_id)
                    await message.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

        await role_menu_repo.delete_menu(menu_id)
        await interaction.response.send_message("Role menu eliminato.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_ROLE_MENUS,
            display_name="Role Menus",
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
            view = await cog._build_view_for_menu(menu, options)
            if view is not None:
                bot.add_view(view, message_id=menu.message_id)
