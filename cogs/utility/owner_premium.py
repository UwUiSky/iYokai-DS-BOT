"""
cogs/utility/owner_premium.py
================================
Comando riservato al proprietario del bot per accendere/spegnere
la natura Premium di ogni modulo, e per gestire la whitelist.

Questo è l'unico punto del progetto che può TRASFORMARE un modulo
gratuito in premium — e lo fa per tutti i server contemporaneamente
(eccetto quelli whitelistati). Per questo il controllo di identità
è il primo controllo di OGNI funzione qui dentro, prima di qualsiasi
altra logica.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.config import config
from core.database import db
from core.premium import PremiumModule, registry


def _is_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.id == config.OWNER_ID


def _build_premium_panel_embed(modules: list[PremiumModule]) -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ Pannello moduli Premium",
        description="Scegli un modulo dal menu qui sotto per cambiarne lo stato.",
        color=discord.Color.blurple(),
    )
    for modulo in modules:
        stato = "🟢 PREMIUM ATTIVO" if modulo.is_premium_active else "⚪ gratuito"
        embed.add_field(name=modulo.display_name, value=f"`{modulo.name}` — {stato}", inline=False)
    return embed


class _PremiumConfirmView(discord.ui.View):
    """
    Secondo step della conferma (SPEC.md §17.10: "conferma a due
    step"). Il primo step è la selezione del modulo nel menu
    (_PremiumPanelView); questo è il vero e proprio "sei sicuro?"
    prima di applicare un cambio che vale per TUTTI i server insieme
    — lo stesso motivo per cui /owner premium-toggle esiste già come
    comando esplicito e non come side-effect di qualcos'altro.
    """

    def __init__(self, cog: "OwnerPremiumCog", module: PremiumModule, nuovo_stato: bool) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.module = module
        self.nuovo_stato = nuovo_stato

    @discord.ui.button(label="Conferma", style=discord.ButtonStyle.danger)
    async def conferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog._apply_premium_toggle(self.module.name, self.nuovo_stato, interaction.user.id)

        stato_testo = "PREMIUM" if self.nuovo_stato else "GRATUITO"
        embed = discord.Embed(
            title="✅ Modulo aggiornato",
            description=f"`{self.module.name}` è ora **{stato_testo}**.",
            color=discord.Color.green(),
        )
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def annulla(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        embed = discord.Embed(
            title="Annullato",
            description="Nessuna modifica applicata.",
            color=discord.Color.greyple(),
        )
        await interaction.response.edit_message(embed=embed, view=None)


class _PremiumPanelSelect(discord.ui.Select):
    def __init__(self, cog: "OwnerPremiumCog", modules: list[PremiumModule]) -> None:
        self.cog = cog
        self._modules_by_name = {m.name: m for m in modules}
        options = [
            discord.SelectOption(
                label=modulo.display_name,
                value=modulo.name,
                description="Premium attivo" if modulo.is_premium_active else "Gratuito",
            )
            for modulo in modules
        ]
        super().__init__(placeholder="Scegli un modulo da cambiare...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        modulo = self._modules_by_name[self.values[0]]
        nuovo_stato = not modulo.is_premium_active
        stato_testo = "PREMIUM" if nuovo_stato else "GRATUITO"

        embed = discord.Embed(
            title="Conferma richiesta",
            description=(
                f"Vuoi impostare **{modulo.display_name}** (`{modulo.name}`) "
                f"su **{stato_testo}** per tutti i server?"
            ),
            color=discord.Color.orange(),
        )
        view = _PremiumConfirmView(self.cog, modulo, nuovo_stato)
        await interaction.response.edit_message(embed=embed, view=view)


class _PremiumPanelView(discord.ui.View):
    def __init__(self, cog: "OwnerPremiumCog", modules: list[PremiumModule]) -> None:
        super().__init__(timeout=120)
        self.add_item(_PremiumPanelSelect(cog, modules))


class OwnerPremiumCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    owner_group = app_commands.Group(
        name="owner",
        description="Comandi riservati al proprietario del bot.",
    )

    @owner_group.command(
        name="premium-list",
        description="[OWNER] Mostra lo stato premium di tutti i moduli.",
    )
    async def premium_list(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        modules = registry.all_modules()
        lines = []
        for m in modules:
            if not m.premium_capable:
                stato = "sempre gratuito"
            elif m.is_premium_active:
                stato = "PREMIUM ATTIVO"
            else:
                stato = "gratuito (predisposto)"
            lines.append(f"`{m.name}` — {m.display_name}: **{stato}**")

        testo = "\n".join(lines) if lines else "Nessun modulo registrato."
        await interaction.response.send_message(testo, ephemeral=True)

    async def _apply_premium_toggle(
        self, module_name: str, active: bool, changed_by: int
    ) -> None:
        """
        Applica un cambio premium con tutte e tre le conseguenze che
        deve avere: stato in memoria (registry, letto da requires_
        module su ogni comando gated), stato persistente più recente
        (premium_module_flags, riletto all'avvio), e log persistente
        dell'intero storico (premium_toggle_history, SPEC.md §17.10
        — distinta da premium_module_flags apposta: quella tiene
        solo l'ULTIMO stato, questa ogni cambiamento mai fatto).
        Condivisa da /owner premium-toggle e dal pannello interattivo
        — un solo punto che applica il cambio, mai due copie della
        stessa logica che potrebbero divergere.
        """
        registry.set_module_premium(module_name, active)

        await db.pool.execute(
            """
            INSERT INTO premium_module_flags (module_name, is_active, updated_by)
            VALUES ($1, $2, $3)
            ON CONFLICT (module_name) DO UPDATE
                SET is_active = EXCLUDED.is_active,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = now()
            """,
            module_name,
            active,
            changed_by,
        )
        await db.pool.execute(
            """
            INSERT INTO premium_toggle_history (module_name, new_value, changed_by)
            VALUES ($1, $2, $3)
            """,
            module_name,
            active,
            changed_by,
        )

    @owner_group.command(
        name="premium-toggle",
        description="[OWNER] Accende o spegne la natura premium di un modulo.",
    )
    @app_commands.describe(
        module_name="Nome tecnico del modulo (vedi /owner premium-list)",
        active="True per rendere premium, False per rendere gratis",
    )
    async def premium_toggle(
        self,
        interaction: discord.Interaction,
        module_name: str,
        active: bool,
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        module = registry.get(module_name)
        if module is None:
            await interaction.response.send_message(
                f"Modulo `{module_name}` non trovato. "
                f"Usa /owner premium-list per la lista esatta.",
                ephemeral=True,
            )
            return

        if not module.premium_capable:
            await interaction.response.send_message(
                f"`{module_name}` è marcato come sempre-gratuito "
                f"e non può diventare premium.",
                ephemeral=True,
            )
            return

        await self._apply_premium_toggle(module_name, active, interaction.user.id)

        stato = "PREMIUM" if active else "GRATUITO"
        await interaction.response.send_message(
            f"Modulo `{module_name}` impostato su **{stato}**.",
            ephemeral=True,
        )

    @owner_group.command(
        name="whitelist-add",
        description="[OWNER] Aggiunge un server alla whitelist premium.",
    )
    @app_commands.describe(
        guild_id="ID del server da aggiungere",
        reason="Motivo (facoltativo)",
    )
    async def whitelist_add(
        self,
        interaction: discord.Interaction,
        guild_id: str,
        reason: str | None = None,
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        try:
            gid = int(guild_id)
        except ValueError:
            await interaction.response.send_message(
                "ID server non valido.", ephemeral=True
            )
            return

        await db.add_guild_to_whitelist(gid, interaction.user.id, reason)
        await interaction.response.send_message(
            f"Server `{gid}` aggiunto alla whitelist premium.",
            ephemeral=True,
        )

    @owner_group.command(
        name="whitelist-remove",
        description="[OWNER] Rimuove un server dalla whitelist premium.",
    )
    @app_commands.describe(guild_id="ID del server da rimuovere")
    async def whitelist_remove(
        self, interaction: discord.Interaction, guild_id: str
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        try:
            gid = int(guild_id)
        except ValueError:
            await interaction.response.send_message(
                "ID server non valido.", ephemeral=True
            )
            return

        await db.remove_guild_from_whitelist(gid)
        await interaction.response.send_message(
            f"Server `{gid}` rimosso dalla whitelist premium.",
            ephemeral=True,
        )

    @owner_group.command(
        name="memory-status",
        description="[OWNER] Mostra il consumo di RAM attuale del processo.",
    )
    async def memory_status(self, interaction: discord.Interaction) -> None:
        # Vive in questo file (nominalmente "premium") e non in un
        # proprio file dedicato per un motivo tecnico, non di
        # comodità: app_commands.Group con lo stesso nome "owner"
        # registrato da due cog diversi verrebbe rifiutato da
        # discord.py come comando duplicato. Finché il progetto ha un
        # solo gruppo /owner, i comandi owner-only condividono questo
        # file — da riorganizzare se/quando il gruppo crescerà troppo.
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        from core.memory_guard import memory_guard
        from core.memory_guard_logic import format_memory_status

        rss = memory_guard.read_rss_bytes()
        await interaction.response.send_message(
            format_memory_status(rss, config.MEMORY_ALERT_THRESHOLD_MB),
            ephemeral=True,
        )

    @owner_group.command(
        name="premium-panel",
        description="[OWNER] Pannello interattivo per attivare/disattivare i moduli premium.",
    )
    async def premium_panel(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        moduli_premium_capable = [m for m in registry.all_modules() if m.premium_capable]
        if not moduli_premium_capable:
            await interaction.response.send_message(
                "Nessun modulo può diventare premium al momento.", ephemeral=True
            )
            return

        view = _PremiumPanelView(self, moduli_premium_capable)
        await interaction.response.send_message(
            embed=_build_premium_panel_embed(moduli_premium_capable), view=view, ephemeral=True
        )

    # ================================================================
    # Blacklist globale (SPEC.md §17.4 utenti, §17.5 server)
    # ================================================================
    @owner_group.command(
        name="blacklist-user-add",
        description="[OWNER] Blocca globalmente un utente dall'uso del bot.",
    )
    @app_commands.describe(user_id="ID Discord dell'utente", reason="Motivo (facoltativo)")
    async def blacklist_user_add(
        self, interaction: discord.Interaction, user_id: str, reason: str | None = None
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message("ID utente non valido.", ephemeral=True)
            return

        from core.repositories.blacklist_repo import blacklist_repo

        await blacklist_repo.add_user(uid, reason, added_by=interaction.user.id)
        await interaction.response.send_message(
            f"Utente `{uid}` bloccato globalmente.", ephemeral=True
        )

    @owner_group.command(
        name="blacklist-user-remove",
        description="[OWNER] Rimuove un utente dalla blacklist globale.",
    )
    @app_commands.describe(user_id="ID Discord dell'utente")
    async def blacklist_user_remove(
        self, interaction: discord.Interaction, user_id: str
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message("ID utente non valido.", ephemeral=True)
            return

        from core.repositories.blacklist_repo import blacklist_repo

        rimosso = await blacklist_repo.remove_user(uid)
        if rimosso:
            await interaction.response.send_message(
                f"Utente `{uid}` rimosso dalla blacklist.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Utente `{uid}` non era in blacklist.", ephemeral=True
            )

    @owner_group.command(
        name="blacklist-user-list", description="[OWNER] Mostra gli utenti bloccati globalmente."
    )
    async def blacklist_user_list(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        from core.repositories.blacklist_repo import blacklist_repo

        utenti = await blacklist_repo.list_users()
        if not utenti:
            await interaction.response.send_message("Nessun utente in blacklist.", ephemeral=True)
            return

        righe = [f"`{u['user_id']}` — {u['reason'] or 'nessun motivo'}" for u in utenti]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    @owner_group.command(
        name="blacklist-guild-add",
        description="[OWNER] Blocca globalmente un server (il bot ne uscirà se già presente).",
    )
    @app_commands.describe(guild_id="ID del server", reason="Motivo (facoltativo)")
    async def blacklist_guild_add(
        self, interaction: discord.Interaction, guild_id: str, reason: str | None = None
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        try:
            gid = int(guild_id)
        except ValueError:
            await interaction.response.send_message("ID server non valido.", ephemeral=True)
            return

        from core.repositories.blacklist_repo import blacklist_repo

        await blacklist_repo.add_guild(gid, reason, added_by=interaction.user.id)

        # Se il bot è già in quel server, ne esce subito — non ha
        # senso bloccare un server e restarci dentro fino al prossimo
        # riavvio o al prossimo controllo casuale.
        guild_gia_presente = self.bot.get_guild(gid)
        if guild_gia_presente is not None:
            await guild_gia_presente.leave()
            await interaction.response.send_message(
                f"Server `{gid}` bloccato globalmente — il bot ne è appena uscito.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"Server `{gid}` bloccato globalmente.", ephemeral=True
            )

    @owner_group.command(
        name="blacklist-guild-remove",
        description="[OWNER] Rimuove un server dalla blacklist globale.",
    )
    @app_commands.describe(guild_id="ID del server")
    async def blacklist_guild_remove(
        self, interaction: discord.Interaction, guild_id: str
    ) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        try:
            gid = int(guild_id)
        except ValueError:
            await interaction.response.send_message("ID server non valido.", ephemeral=True)
            return

        from core.repositories.blacklist_repo import blacklist_repo

        rimosso = await blacklist_repo.remove_guild(gid)
        if rimosso:
            await interaction.response.send_message(
                f"Server `{gid}` rimosso dalla blacklist.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Server `{gid}` non era in blacklist.", ephemeral=True
            )

    @owner_group.command(
        name="blacklist-guild-list", description="[OWNER] Mostra i server bloccati globalmente."
    )
    async def blacklist_guild_list(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        from core.repositories.blacklist_repo import blacklist_repo

        server = await blacklist_repo.list_guilds()
        if not server:
            await interaction.response.send_message("Nessun server in blacklist.", ephemeral=True)
            return

        righe = [f"`{g['guild_id']}` — {g['reason'] or 'nessun motivo'}" for g in server]
        await interaction.response.send_message("\n".join(righe), ephemeral=True)

    # ================================================================
    # Leave guild forzato (SPEC.md §17.9)
    # ================================================================
    @owner_group.command(
        name="leave-guild",
        description="[OWNER] Forza il bot a lasciare un server specifico (senza bloccarlo).",
    )
    @app_commands.describe(guild_id="ID del server da cui uscire")
    async def leave_guild(self, interaction: discord.Interaction, guild_id: str) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        try:
            gid = int(guild_id)
        except ValueError:
            await interaction.response.send_message("ID server non valido.", ephemeral=True)
            return

        guild = self.bot.get_guild(gid)
        if guild is None:
            await interaction.response.send_message(
                f"Il bot non risulta presente nel server `{gid}`.", ephemeral=True
            )
            return

        nome_server = guild.name
        await guild.leave()
        await interaction.response.send_message(
            f"Il bot è uscito da **{nome_server}** (`{gid}`).", ephemeral=True
        )


    @owner_group.command(
        name="announce", description="[OWNER] Manda un annuncio a tutti i server."
    )
    @app_commands.describe(message="Il testo dell'annuncio")
    async def announce(self, interaction: discord.Interaction, message: str) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title="📢 Annuncio da iYokai",
            description=message,
            color=discord.Color.gold(),
        )

        raggiunti = 0
        falliti = 0
        for guild in self.bot.guilds:
            # Riusa la stessa catena di fallback del messaggio di
            # benvenuto (system_channel → primo canale scrivibile →
            # DM al proprietario) — SPEC.md §17.7, appena estratta in
            # un metodo generico su iYokaiBot proprio per questo.
            riuscito = await self.bot._send_embed_with_fallback(
                guild, embed, contesto="annuncio globale"
            )
            if riuscito:
                raggiunti += 1
            else:
                falliti += 1

        await interaction.followup.send(
            f"Annuncio inviato a {raggiunti} server ({falliti} non raggiunti).",
            ephemeral=True,
        )

    @owner_group.command(
        name="stats", description="[OWNER] Statistiche globali del bot."
    )
    async def stats(self, interaction: discord.Interaction) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        from core.memory_guard import memory_guard
        from core.memory_guard_logic import bytes_to_mb
        from core.bot_stats import command_counter, error_counter

        rss_mb = bytes_to_mb(memory_guard.read_rss_bytes())
        latenza_ms = round(self.bot.latency * 1000)

        embed = discord.Embed(title="📊 Statistiche globali", color=discord.Color.blurple())
        embed.add_field(name="Server", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(
            name="Membri totali (stimati)",
            value=str(sum(g.member_count or 0 for g in self.bot.guilds)),
            inline=True,
        )
        embed.add_field(name="RAM", value=f"{rss_mb:.0f} MB", inline=True)
        embed.add_field(name="Latenza", value=f"{latenza_ms} ms", inline=True)

        # Shard health: latenza per singolo shard (AutoShardedBot).
        # bot.latencies è una lista di (shard_id, latenza) — se il
        # bot non è ancora sharded del tutto (avvio in corso) può
        # essere vuota, gestito senza sollevare.
        if self.bot.latencies:
            righe_shard = [
                f"Shard {shard_id}: {round(lat * 1000)} ms" for shard_id, lat in self.bot.latencies
            ]
            embed.add_field(name="Shard", value="\n".join(righe_shard), inline=False)

        embed.add_field(
            name="Comandi (ultimo minuto)", value=str(command_counter.count_in_window()), inline=True
        )
        embed.add_field(
            name="Errori (ultimo minuto)", value=str(error_counter.count_in_window()), inline=True
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ================================================================
    # Forced cog load/unload/reload (SPEC.md §17.6)
    # ================================================================
    @owner_group.command(
        name="cog-load", description="[OWNER] Carica un'estensione (es. cogs.moderation.actions)."
    )
    @app_commands.describe(extension="Percorso completo del modulo, es. cogs.moderation.actions")
    async def owner_cog_load(self, interaction: discord.Interaction, extension: str) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        try:
            await self.bot.load_extension(extension)
        except commands.ExtensionError as exc:
            await interaction.response.send_message(
                f"Impossibile caricare `{extension}`: {exc}", ephemeral=True
            )
            return
        except Exception as exc:
            # bot.load_extension() può sollevare eccezioni Python
            # NON derivate da commands.ExtensionError — verificato
            # con una prova diretta: un percorso di modulo con un
            # pacchetto intermedio inesistente (es. typo dell'owner)
            # fa arrivare un ModuleNotFoundError grezzo da
            # importlib.util.find_spec(), che ExtensionError da solo
            # non intercetta. Un typo dell'owner deve restare un
            # messaggio d'errore, non un crash del comando.
            await interaction.response.send_message(
                f"Impossibile caricare `{extension}`: {type(exc).__name__}: {exc}",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(f"Caricato `{extension}`.", ephemeral=True)

    @owner_group.command(name="cog-unload", description="[OWNER] Scarica un'estensione.")
    @app_commands.describe(extension="Percorso completo del modulo")
    async def owner_cog_unload(self, interaction: discord.Interaction, extension: str) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        try:
            await self.bot.unload_extension(extension)
        except commands.ExtensionError as exc:
            await interaction.response.send_message(
                f"Impossibile scaricare `{extension}`: {exc}", ephemeral=True
            )
            return
        except Exception as exc:
            await interaction.response.send_message(
                f"Impossibile scaricare `{extension}`: {type(exc).__name__}: {exc}",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(f"Scaricato `{extension}`.", ephemeral=True)

    @owner_group.command(
        name="cog-reload", description="[OWNER] Ricarica un'estensione già caricata."
    )
    @app_commands.describe(extension="Percorso completo del modulo")
    async def owner_cog_reload(self, interaction: discord.Interaction, extension: str) -> None:
        if not _is_owner(interaction):
            await interaction.response.send_message(
                "Comando riservato al proprietario del bot.", ephemeral=True
            )
            return

        try:
            await self.bot.reload_extension(extension)
        except commands.ExtensionError as exc:
            await interaction.response.send_message(
                f"Impossibile ricaricare `{extension}`: {exc}", ephemeral=True
            )
            return
        except Exception as exc:
            await interaction.response.send_message(
                f"Impossibile ricaricare `{extension}`: {type(exc).__name__}: {exc}",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(f"Ricaricato `{extension}`.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OwnerPremiumCog(bot))
