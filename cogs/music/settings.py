"""
cogs/music/settings.py
==========================
Impostazioni musicali del server (issue #126: MUS-047, MUS-044, MUS-055,
MUS-059, MUS-066, MUS-054, MUS-062, MUS-064): /admin musica impostazioni e /admin musica riepilogo.
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
from core.i18n import testo_per
from core.music_settings_logic import (
    MAX_IDLE_MINUTES,
    MAX_PAROLE_VIETATE,
    SETTING_ALLOWED_CHANNEL,
    SETTING_BANNED_WORDS,
    SETTING_IDLE_MINUTES,
    SETTING_KNOWN_SITES_ONLY,
    SETTING_MAX_TRACK_MINUTES,
    SETTING_MAX_VOLUME,
    SETTING_STAY_WHEN_QUEUE_ENDS,
    MAX_TRACK_MINUTES,
    MAX_VOLUME,
    load_music_settings,
    save_music_setting,
    summary_lines,
)

SG_MUSICA = ("musica", "Musica: impostazioni del server")


def _testo_o_vuoto(testo: str) -> str:
    """Discord non manda un testo vuoto: «-» vuol dire «nessuna»."""
    testo = testo.strip()
    return "" if testo == "-" else testo


class MusicSettingsCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "admin-musica",
        nome="impostazioni",
        descrizione="Cambia le impostazioni musicali del server.",
    )
    @app_commands.describe(
        volume_massimo="Volume massimo permesso (0-200)",
        durata_massima="Durata massima di un brano in minuti (0 = nessun limite)",
        resta_a_coda_finita="A coda finita il bot resta nel canale invece di uscire",
        canale_vocale="Permetti la musica solo in questo canale vocale",
        tutti_i_canali="Togli la restrizione: la musica è permessa in ogni canale vocale",
        attesa_uscita="Minuti di attesa prima di uscire a coda finita (0 = predefinita)",
        parole_vietate="Parole non ammesse nei titoli, separate da virgola; «-» toglie l'elenco",
        solo_siti_conosciuti="Accetta solo link di siti conosciuti",
    )
    @app_commands.rename(
        volume_massimo="volume-massimo",
        durata_massima="durata-massima",
        resta_a_coda_finita="resta-a-coda-finita",
        canale_vocale="canale-vocale",
        tutti_i_canali="tutti-i-canali",
        attesa_uscita="attesa-uscita",
        parole_vietate="parole-vietate",
        solo_siti_conosciuti="solo-siti-conosciuti",
    )
    async def impostazioni(
        self,
        interaction: discord.Interaction,
        volume_massimo: app_commands.Range[int, 0, MAX_VOLUME] | None = None,
        durata_massima: app_commands.Range[int, 0, MAX_TRACK_MINUTES] | None = None,
        resta_a_coda_finita: bool | None = None,
        canale_vocale: discord.VoiceChannel | None = None,
        tutti_i_canali: bool = False,
        attesa_uscita: app_commands.Range[int, 0, MAX_IDLE_MINUTES] | None = None,
        parole_vietate: app_commands.Range[str, 0, MAX_PAROLE_VIETATE] | None = None,
        solo_siti_conosciuti: bool | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return
        if canale_vocale is not None and tutti_i_canali:
            await interaction.response.send_message(
                await testo_per(interaction, "settings_scegli_canale_vocale_oppure_tutti"), ephemeral=True
            )
            return
        cambi = {
            SETTING_MAX_VOLUME: volume_massimo,
            SETTING_MAX_TRACK_MINUTES: durata_massima,
            SETTING_STAY_WHEN_QUEUE_ENDS: resta_a_coda_finita,
            SETTING_IDLE_MINUTES: attesa_uscita,
            SETTING_BANNED_WORDS: None if parole_vietate is None else _testo_o_vuoto(parole_vietate),
            SETTING_KNOWN_SITES_ONLY: solo_siti_conosciuti,
        }
        cambi = {k: v for k, v in cambi.items() if v is not None}
        if canale_vocale is not None:
            cambi[SETTING_ALLOWED_CHANNEL] = canale_vocale.id
        if not cambi and not tutti_i_canali:
            await interaction.response.send_message(
                await testo_per(interaction, "settings_non_hai_cambiato_nulla_indica"),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        for chiave, valore in cambi.items():
            await save_music_setting(db, guild.id, chiave, valore, interaction.user.id)
        if tutti_i_canali:
            await save_music_setting(db, guild.id, SETTING_ALLOWED_CHANNEL, None, interaction.user.id)

        impostazioni = await load_music_settings(db, guild.id)
        embed = discord.Embed(
            title=await testo_per(interaction, "settings_impostazioni_musicali_aggiornate"),
            description="\n".join(summary_lines(impostazioni)),
            color=discord.Color.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @comando_di_gruppo(
        "admin-musica",
        nome="riepilogo",
        descrizione="Mostra tutte le impostazioni musicali del server.",
    )
    async def riepilogo(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return
        impostazioni = await load_music_settings(db, guild.id)
        embed = discord.Embed(
            title=await testo_per(interaction, "settings_impostazioni_musicali"),
            description="\n".join(summary_lines(impostazioni)),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=await testo_per(interaction, "settings_si_cambiano_con_admin_musica"))
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicSettingsCog(bot))
