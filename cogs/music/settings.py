"""
cogs/music/settings.py
==========================
Impostazioni musicali del server (issue #126: MUS-047, MUS-044, MUS-055,
MUS-059, MUS-066): /admin musica impostazioni e /admin musica riepilogo.
Solo admin (lo dà il gruppo /admin). La logica sta in
core/music_settings_logic.py; i controlli che le usano sono in
cogs/music/player.py e core/music_fleet.py.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.music_settings_logic import (
    KEY_ALLOWED_CHANNEL,
    KEY_MAX_TRACK_MINUTES,
    KEY_MAX_VOLUME,
    KEY_STAY_WHEN_QUEUE_ENDS,
    MAX_TRACK_MINUTES,
    MAX_VOLUME,
    load_music_settings,
    save_music_setting,
    summary_lines,
)

SG_MUSICA = ("musica", "Musica: impostazioni del server")


class MusicSettingsCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "admin",
        nome="impostazioni",
        descrizione="Cambia le impostazioni musicali del server.",
        sottogruppo=SG_MUSICA,
    )
    @app_commands.describe(
        volume_massimo="Volume massimo permesso (0-200)",
        durata_massima="Durata massima di un brano in minuti (0 = nessun limite)",
        resta_a_coda_finita="A coda finita il bot resta nel canale invece di uscire",
        canale_vocale="Permetti la musica solo in questo canale vocale",
        tutti_i_canali="Togli la restrizione: la musica è permessa in ogni canale vocale",
    )
    @app_commands.rename(
        volume_massimo="volume-massimo",
        durata_massima="durata-massima",
        resta_a_coda_finita="resta-a-coda-finita",
        canale_vocale="canale-vocale",
        tutti_i_canali="tutti-i-canali",
    )
    async def impostazioni(
        self,
        interaction: discord.Interaction,
        volume_massimo: app_commands.Range[int, 0, MAX_VOLUME] | None = None,
        durata_massima: app_commands.Range[int, 0, MAX_TRACK_MINUTES] | None = None,
        resta_a_coda_finita: bool | None = None,
        canale_vocale: discord.VoiceChannel | None = None,
        tutti_i_canali: bool = False,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        if canale_vocale is not None and tutti_i_canali:
            await interaction.response.send_message(
                "Scegli `canale-vocale` oppure `tutti-i-canali`, non entrambi.", ephemeral=True
            )
            return
        cambi = {
            KEY_MAX_VOLUME: volume_massimo,
            KEY_MAX_TRACK_MINUTES: durata_massima,
            KEY_STAY_WHEN_QUEUE_ENDS: resta_a_coda_finita,
        }
        cambi = {k: v for k, v in cambi.items() if v is not None}
        if canale_vocale is not None:
            cambi[KEY_ALLOWED_CHANNEL] = canale_vocale.id
        if not cambi and not tutti_i_canali:
            await interaction.response.send_message(
                "Non hai cambiato nulla: indica almeno un'opzione. "
                "Per vedere i valori attuali usa `/admin musica riepilogo`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        for chiave, valore in cambi.items():
            await save_music_setting(db, guild.id, chiave, valore, interaction.user.id)
        if tutti_i_canali:
            await save_music_setting(db, guild.id, KEY_ALLOWED_CHANNEL, None, interaction.user.id)

        impostazioni = await load_music_settings(db, guild.id)
        embed = discord.Embed(
            title="✅ Impostazioni musicali aggiornate",
            description="\n".join(summary_lines(impostazioni)),
            color=discord.Color.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @comando_di_gruppo(
        "admin",
        nome="riepilogo",
        descrizione="Mostra tutte le impostazioni musicali del server.",
        sottogruppo=SG_MUSICA,
    )
    async def riepilogo(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        impostazioni = await load_music_settings(db, guild.id)
        embed = discord.Embed(
            title="🎵 Impostazioni musicali",
            description="\n".join(summary_lines(impostazioni)),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Si cambiano con /admin musica impostazioni")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicSettingsCog(bot))
