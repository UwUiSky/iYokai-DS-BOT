"""
cogs/utility/config_permessi.py
===============================
`/admin-bot config staff` (CFG-022, CFG-023, #122): i ruoli admin, mod e ban del bot, con i gruppi che aprono; si
scelgono o si tolgono qui. `/admin-bot config permessi` (CFG-026): il livello di permesso di un membro, con il motivo.
Le scelte passano da `core/command_access.imposta_ruolo` (un solo punto, D16; il ruolo admin lo sceglie solo chi ha
«Amministratore»). Il resto è sola lettura (`core/permessi_vista.py`).
Funzioni coperte: SPEC §20 (NF-05), catalogo #122
Dipende da: core/command_access.py, core/permessi_vista.py
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.command_access import Livello, TipoRuolo, imposta_ruolo
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import testo_per
from core.permessi_vista import (
    livelli_del_membro,
    ruoli_dello_staff,
)

SOTTOGRUPPO_CONFIG = ("config", "Configurazione: canali, storico, ripristino ed esportazione")
MAX_GRUPPI_MOSTRATI = 8
_NOMI_TIPO = {TipoRuolo.ADMIN: "perm_ruolo_admin", TipoRuolo.MOD: "perm_ruolo_mod", TipoRuolo.MODBAN: "perm_ruolo_ban"}
_NOMI_LIVELLO = {l: f"perm_liv_{l.value}" for l in Livello}


def _gruppi(gruppi: tuple[str, ...]) -> str:
    mostrati = ", ".join(f"`/{g}`" for g in gruppi[:MAX_GRUPPI_MOSTRATI])
    return mostrati + (f" (+{len(gruppi) - MAX_GRUPPI_MOSTRATI})" if len(gruppi) > MAX_GRUPPI_MOSTRATI else "")


class ConfigPermessiCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "admin-bot", nome="staff", descrizione="Ruoli admin, mod e ban del bot: elenco e scelta.",
        sottogruppo=SOTTOGRUPPO_CONFIG,
    )
    @app_commands.describe(
        admin="Il ruolo che gestisce il bot (apre i gruppi admin); serve «Amministratore»",
        mod="Il ruolo dei moderatori (sanzioni, casi, canali)",
        ban="Il ruolo che può anche bannare",
        togli="Togli il ruolo scelto per questo livello",
    )
    @app_commands.choices(
        togli=[
            app_commands.Choice(name="admin", value="admin"),
            app_commands.Choice(name="mod", value="mod"),
            app_commands.Choice(name="ban", value="ban"),
        ]
    )
    async def staff(
        self,
        interaction: discord.Interaction,
        admin: discord.Role | None = None,
        mod: discord.Role | None = None,
        ban: discord.Role | None = None,
        togli: app_commands.Choice[str] | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            return
        scelte = {TipoRuolo.ADMIN: admin, TipoRuolo.MOD: mod, TipoRuolo.MODBAN: ban}
        da_togliere = {"admin": TipoRuolo.ADMIN, "mod": TipoRuolo.MOD, "ban": TipoRuolo.MODBAN}.get(togli.value) if togli else None
        if da_togliere is not None and scelte[da_togliere] is not None:
            await interaction.response.send_message(await testo_per(interaction, "perm_togli_o_scegli"), ephemeral=True)
            return
        cambiato = False
        for tipo, ruolo in scelte.items():
            if ruolo is None and tipo is not da_togliere:
                continue
            try:
                await imposta_ruolo(
                    guild, tipo, guild.get_role(ruolo.id) if ruolo else None, interaction.user.id, autore=interaction.user
                )
            except ValueError as errore:  # ruolo non valido, o ruolo admin senza «Amministratore»
                await interaction.response.send_message(str(errore)[:500], ephemeral=True)
                return
            cambiato = True
        righe = []
        for voce in await ruoli_dello_staff(guild):
            ruolo_testo = (
                f"<@&{voce.ruolo_id}>" if voce.esiste else await testo_per(interaction, "perm_nessun_ruolo")
            )
            righe.append(f"**{await testo_per(interaction, _NOMI_TIPO[voce.tipo])}**: {ruolo_testo}\n{_gruppi(voce.gruppi)}")
        intestazione = await testo_per(interaction, "perm_staff_salvato" if cambiato else "perm_staff_titolo")
        await interaction.response.send_message(
            (intestazione + "\n\n" + "\n\n".join(righe))[:1900],
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @comando_di_gruppo(
        "admin-bot", nome="permessi", descrizione="Mostra il livello di permesso di un membro e perché.",
        sottogruppo=SOTTOGRUPPO_CONFIG,
    )
    @app_commands.describe(membro="Il membro da controllare")
    async def permessi(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        guild = interaction.guild
        if guild is None:
            return
        righe = []
        for voce in await livelli_del_membro(guild, membro):
            esito = await testo_per(interaction, f"perm_motivo_{voce.motivo}")
            segno = "✅" if voce.ha else "❌"
            righe.append(f"{segno} **{await testo_per(interaction, _NOMI_LIVELLO[voce.livello])}**: {esito}")
        titolo = await testo_per(interaction, "perm_permessi_titolo", membro=discord.utils.escape_markdown(membro.display_name)[:80])
        await interaction.response.send_message(
            (titolo + "\n" + "\n".join(righe))[:1900],
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConfigPermessiCog(bot))
