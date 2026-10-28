"""
cogs/moderation/opzioni.py
==========================
Opzioni di moderazione del server (`/mod opzioni`): giorni di messaggi
cancellati al ban, durata predefinita del timeout, DM per tipo di azione,
ruoli immuni alla moderazione manuale, casi per le azioni fatte fuori da
iYokai, avvisi allo staff. La logica e il salvataggio sono in
core/moderation_opzioni.py (un solo punto, anche per il pannello web).
Funzioni coperte: SPEC §5.13 (MOD-010, MOD-017, MOD-057, MOD-068), §5.2 (MOD-047), §5.3 (MOD-036, MOD-064)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs.moderation._shared import MODULE_ACTIONS, ensure_module_enabled, format_duration, parse_duration
from core import moderation_opzioni as opzioni
from core.command_groups import CogConGruppi, comando_di_gruppo

SOTTOGRUPPO = ("opzioni", "Opzioni di moderazione del server.")

_NOMI_AZIONI = {
    "warn": "Warn",
    "kick": "Kick",
    "ban": "Ban",
    "tempban": "Tempban",
    "softban": "Softban",
    "timeout": "Timeout",
    "mute": "Mute con ruolo",
}


def _puo_gestire(interaction: discord.Interaction) -> bool:
    permessi = interaction.user.guild_permissions
    return permessi.administrator or permessi.manage_guild


def _riepilogo(guild: discord.Guild, o: opzioni.OpzioniModerazione) -> discord.Embed:
    dm = ", ".join(_NOMI_AZIONI[a] for a in opzioni.AZIONI_CON_DM if a not in o.dm_spenti) or "nessuna"
    immuni = " ".join(f"<@&{r}>" for r in o.ruoli_immuni) or "nessuno"
    embed = discord.Embed(title="Opzioni di moderazione", color=discord.Color.blurple())
    embed.add_field(name="Giorni di messaggi cancellati al ban", value=str(o.giorni_ban), inline=False)
    embed.add_field(
        name="Timeout senza durata",
        value=format_duration(o.durata_timeout) if o.durata_timeout else "durata obbligatoria",
        inline=False,
    )
    embed.add_field(name="DM all'utente per", value=dm[:1024], inline=False)
    embed.add_field(name="Ruoli immuni", value=immuni[:1024], inline=False)
    embed.add_field(
        name="Casi per le azioni fatte fuori da iYokai",
        value="sì (ban, kick, timeout)" if o.casi_esterni else "no",
        inline=False,
    )
    embed.add_field(
        name="Avvisi allo staff",
        value=(
            (f"warn oltre {o.avviso_warn}" if o.avviso_warn else "warn: spento")
            + "; rientro di chi ha casi: " + ("sì" if o.avviso_rientro else "no")
        ),
        inline=False,
    )
    return embed


class OpzioniModerazioneCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _controlli(self, interaction: discord.Interaction) -> bool:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return False
        if not _puo_gestire(interaction):
            await interaction.response.send_message(
                "Le opzioni le cambia chi ha «Gestire il server».", ephemeral=True
            )
            return False
        return True

    @comando_di_gruppo(
        "mod",
        nome="imposta",
        descrizione="Messaggi al ban, timeout, casi esterni, avvisi. Vuoto: mostra le opzioni.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(
        giorni_ban="Giorni di messaggi cancellati quando il ban non li dice (0-7)",
        durata_timeout="Durata del timeout quando non la scrivi, es. 10m, 1h; «no» per toglierla",
        casi_esterni="Crea un caso anche per ban, kick e timeout fatti dal menu di Discord o da altri bot",
        avviso_warn="Avvisa lo staff quando chi riceve un warn ne ha già questi (0 = spento)",
        avviso_rientro="Avvisa lo staff quando rientra nel server chi ha dei casi",
    )
    async def imposta(
        self,
        interaction: discord.Interaction,
        giorni_ban: app_commands.Range[int, 0, 7] | None = None,
        durata_timeout: app_commands.Range[str, 1, 20] | None = None,
        casi_esterni: bool | None = None,
        avviso_warn: app_commands.Range[int, 0, opzioni.MAX_SOGLIA_WARN] | None = None,
        avviso_rientro: bool | None = None,
    ) -> None:
        if not await self._controlli(interaction):
            return
        guild = interaction.guild
        if durata_timeout is not None:
            if durata_timeout.strip().lower() == "no":
                secondi = None
            else:
                try:
                    secondi = parse_duration(durata_timeout)
                except ValueError as exc:
                    await interaction.response.send_message(str(exc), ephemeral=True)
                    return
                if not opzioni.MIN_TIMEOUT <= secondi <= opzioni.MAX_TIMEOUT:
                    await interaction.response.send_message(
                        "La durata del timeout va da 1 minuto a 28 giorni.", ephemeral=True
                    )
                    return
            await opzioni.imposta_durata_timeout(guild.id, secondi, interaction.user.id)
        # Si salva solo dopo aver controllato tutto: con un errore non cambia niente.
        if giorni_ban is not None:
            await opzioni.imposta_giorni_ban(guild.id, giorni_ban, interaction.user.id)
        if casi_esterni is not None:
            await opzioni.imposta_casi_esterni(guild.id, casi_esterni, interaction.user.id)
        if avviso_warn is not None:
            await opzioni.imposta_avviso_warn(guild.id, avviso_warn, interaction.user.id)
        if avviso_rientro is not None:
            await opzioni.imposta_avviso_rientro(guild.id, avviso_rientro, interaction.user.id)
        await interaction.response.send_message(
            embed=_riepilogo(guild, await opzioni.leggi(guild.id)),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo(
        "mod",
        nome="dm",
        descrizione="Sceglie se l'utente riceve un DM per un tipo di azione.",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(azione="Il tipo di azione", attivo="Mandare il DM?")
    @app_commands.choices(
        azione=[app_commands.Choice(name=nome, value=valore) for valore, nome in _NOMI_AZIONI.items()]
    )
    async def dm(
        self, interaction: discord.Interaction, azione: app_commands.Choice[str], attivo: bool
    ) -> None:
        if not await self._controlli(interaction):
            return
        await opzioni.imposta_dm(interaction.guild.id, azione.value, attivo, interaction.user.id)
        await interaction.response.send_message(
            f"DM per **{azione.name}**: {'acceso' if attivo else 'spento'}.", ephemeral=True
        )

    @comando_di_gruppo(
        "mod",
        nome="immuni",
        descrizione="Ruoli che la moderazione manuale non tocca (solo il proprietario).",
        sottogruppo=SOTTOGRUPPO,
    )
    @app_commands.describe(azione="Aggiungere o togliere", ruolo="Il ruolo")
    @app_commands.choices(
        azione=[
            app_commands.Choice(name="Aggiungi", value="aggiungi"),
            app_commands.Choice(name="Togli", value="togli"),
        ]
    )
    async def immuni(
        self, interaction: discord.Interaction, azione: app_commands.Choice[str], ruolo: discord.Role
    ) -> None:
        if not await ensure_module_enabled(interaction, MODULE_ACTIONS):
            return
        guild = interaction.guild
        # Decide chi si può moderare: lo sceglie solo il proprietario.
        if interaction.user.id != guild.owner_id:
            await interaction.response.send_message(
                "I ruoli immuni li sceglie solo il proprietario del server.", ephemeral=True
            )
            return
        if ruolo.is_default():
            await interaction.response.send_message("@everyone non può essere immune.", ephemeral=True)
            return
        errore = await opzioni.cambia_ruolo_immune(
            guild.id, ruolo.id, azione.value == "aggiungi", interaction.user.id
        )
        if errore:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        await interaction.response.send_message(
            f"{ruolo.mention} {'ora è immune' if azione.value == 'aggiungi' else 'non è più immune'}: "
            "warn, kick, ban, timeout e mute dati a mano non lo toccano (tu sì).",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OpzioniModerazioneCog(bot))
