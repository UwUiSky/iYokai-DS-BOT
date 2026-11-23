"""
cogs/utility/identita_bot.py
============================
`/admin-bot setup identita-bot` (MUS-090, D111): il server sceglie per ogni bot secondario (Mod, Creator, NSFW, App)
se tenere nome e logo originali o metterne di suoi, solo in questo server. I bot musicali sono esclusi.
La logica è in `core/bot_identita.py` (la stessa userà il pannello web).
Funzioni coperte: SPEC §23 (MUS-090, D111)
Dipende da: core/bot_identita.py
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core import bot_identita
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import testo_per

logger = logging.getLogger("iyokai.identita_bot")
SOTTOGRUPPO_SETUP = ("setup", "Attivazione dei moduli e configurazione guidata")
ETICHETTE = {"mod": "iYokai Mod", "creator": "iYokai Creator", "nsfw": "iYokai NSFW", "app": "iYokai App"}


class IdentitaBotCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _elenco(self, interaction: discord.Interaction) -> str:
        righe = []
        for s in bot_identita.stati(interaction.guild.id):
            chiave = "idn_riga_personale" if s.personalizzato else "idn_riga_originale"
            righe.append(await testo_per(interaction, chiave, bot=ETICHETTE[s.chiave], nome=s.nick or "-"))
        if not righe:
            return await testo_per(interaction, "idn_nessun_bot")
        return (await testo_per(interaction, "idn_titolo") + "\n" + "\n".join(righe) + "\n" + await testo_per(interaction, "idn_musica_nota"))[:1900]

    @comando_di_gruppo(
        "admin-bot", nome="identita-bot", descrizione="Nome e logo degli altri bot di iYokai in questo server.",
        sottogruppo=SOTTOGRUPPO_SETUP,
    )
    @app_commands.describe(
        bot="Quale bot (senza scelta: l'elenco di come sono ora)",
        nome="Nome da mostrare solo in questo server (massimo 32 caratteri)",
        logo="Logo solo per questo server: PNG, JPEG, GIF o WEBP (massimo 8 MB)",
        originale="Torna al nome e al logo originali",
    )
    @app_commands.choices(bot=[app_commands.Choice(name=n, value=k) for k, n in ETICHETTE.items()])
    @app_commands.guild_only()
    async def identita(
        self,
        interaction: discord.Interaction,
        bot: app_commands.Choice[str] | None = None,
        nome: app_commands.Range[str, 1, bot_identita.MAX_NICK] | None = None,
        logo: discord.Attachment | None = None,
        originale: bool = False,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(await testo_per(interaction, "accesso_solo_server"), ephemeral=True)
            return
        if not bot_identita.puo_gestire(interaction.user):
            await interaction.response.send_message(await testo_per(interaction, "idn_permesso_utente"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if bot is None or (nome is None and logo is None and not originale):
            await interaction.followup.send(await self._elenco(interaction), ephemeral=True)
            return
        if originale:
            chiave = await bot_identita.ripristina_originale(interaction.user, interaction.guild.id, bot.value)
        else:
            campi: dict = {}
            if nome is not None:
                campi["nick"] = nome
            if logo is not None:
                if logo.size > bot_identita.MAX_LOGO:
                    await interaction.followup.send(await testo_per(interaction, "idn_logo_grande"), ephemeral=True)
                    return
                try:
                    campi["logo"] = await logo.read()
                except discord.HTTPException:
                    await interaction.followup.send(await testo_per(interaction, "idn_logo_non_valido"), ephemeral=True)
                    return
            chiave = await bot_identita.applica_identita(interaction.user, interaction.guild.id, bot.value, **campi)
        await interaction.followup.send(await testo_per(interaction, chiave), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(IdentitaBotCog(bot))
