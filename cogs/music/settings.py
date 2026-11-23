"""
cogs/music/settings.py
==========================
Impostazioni musicali del server (issue #126: MUS-047, MUS-044, MUS-055,
MUS-059, MUS-066, MUS-054, MUS-062, MUS-064, MUS-037, MUS-065): /admin-musica impostazioni e /admin-musica riepilogo.
Solo admin (lo dà il gruppo /admin-musica). La logica sta in
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
from core.music_playlist_logic import NOME_MAX
from core.repositories.music_playlist_repo import music_guild_playlist_repo
from core.music_sources import FONTI, FONTI_DI_RICERCA
from core.music_jukebox_logic import PREZZO_MAX
from core.music_paese_logic import paese_valido
from core.music_settings_logic import (
    MAX_IDLE_MINUTES,
    MAX_PAROLE_VIETATE,
    SETTING_ALLOWED_CHANNEL,
    SETTING_BANNED_WORDS,
    SETTING_DEFAULT_SEARCH,
    SETTING_IDLE_MINUTES,
    SETTING_ANNOUNCE,
    SETTING_DAILY_PLAYLIST,
    SETTING_FALLBACK_PLAYLIST,
    SETTING_PERSIST_QUEUE,
    SETTING_ANNOUNCE_CHANNEL,
    SETTING_QUEUE_MODE,
    SETTING_JUKEBOX_PRICE,
    SETTING_DJ_MODE,
    SETTING_DJ_ROLE,
    SETTING_SKIP_VOTE,
    SETTING_EMPTY_PAUSE,
    SETTING_AUDIO_ONLY,
    SETTING_BOT_STATUS,
    SETTING_SEARCH_COUNTRY,
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

SCELTE_RICERCA = [app_commands.Choice(name="Automatica (YouTube, poi SoundCloud)", value="automatica")] + [
    app_commands.Choice(name=FONTI[nome].etichetta, value=nome) for nome in FONTI_DI_RICERCA
]
SCELTE_CODA = [
    app_commands.Choice(name="Normale (come arrivano)", value="normale"),
    app_commands.Choice(name="Equa (a giro tra gli utenti)", value="equa"),
]
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
        ricerca_predefinita="Dove cercare un titolo scritto senza link (i link vincono sempre)",
        coda="Ordine dei brani: normale (come arrivano) o equa (a giro tra gli utenti)",
        annunci="Annuncia nel canale scelto il brano che parte (spenti di base)",
        canale_annunci="Canale dove mandare gli annunci «ora in riproduzione»",
        playlist_di_riserva="Playlist del server che parte quando la coda finisce («-» la toglie)",
        playlist_del_giorno="Tiene la playlist «Oggi» con i brani suonati nel giorno",
        coda_salvata="Salva la coda per ritrovarla dopo un riavvio (/music coda ripristina)",
        prezzo_jukebox="Monete per mettere un brano in coda, alla cassa del server (0 = spento)",
        modalita_dj="Solo DJ, staff o chi è solo nel canale comandano coda e player (spenta di base)",
        ruolo_dj="Ruolo dei DJ",
        togli_ruolo_dj="Togli il ruolo DJ",
        voto_salto="Percentuale degli ascoltatori che serve per saltare un brano (1-100, di base 50)",
        pausa_canale_vuoto="Metti in pausa quando nel canale non resta nessuno, riprendi al rientro",
        stato_bot="Mostra il titolo del brano come stato dei music bot",
        paese="Paese delle ricerche (2 lettere, es. TR): scarta i brani non ascoltabili; «-» toglie il filtro",
        solo_audio="Nelle ricerche per titolo, prima le versioni senza «video ufficiale»",
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
        ricerca_predefinita="ricerca-predefinita",
        canale_annunci="canale-annunci",
        playlist_di_riserva="playlist-di-riserva",
        playlist_del_giorno="playlist-del-giorno",
        coda_salvata="coda-salvata",
        prezzo_jukebox="prezzo-jukebox",
        modalita_dj="modalita-dj",
        ruolo_dj="ruolo-dj",
        togli_ruolo_dj="togli-ruolo-dj",
        voto_salto="voto-salto",
        pausa_canale_vuoto="pausa-canale-vuoto",
        stato_bot="stato-bot",
        solo_audio="solo-audio",
    )
    @app_commands.choices(ricerca_predefinita=SCELTE_RICERCA, coda=SCELTE_CODA)
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
        ricerca_predefinita: str | None = None,
        coda: str | None = None,
        annunci: bool | None = None,
        canale_annunci: discord.TextChannel | None = None,
        playlist_di_riserva: app_commands.Range[str, 1, NOME_MAX] | None = None,
        playlist_del_giorno: bool | None = None,
        coda_salvata: bool | None = None,
        prezzo_jukebox: app_commands.Range[int, 0, PREZZO_MAX] | None = None,
        modalita_dj: bool | None = None,
        ruolo_dj: discord.Role | None = None,
        togli_ruolo_dj: bool = False,
        voto_salto: app_commands.Range[int, 1, 100] | None = None,
        pausa_canale_vuoto: bool | None = None,
        stato_bot: bool | None = None,
        paese: app_commands.Range[str, 1, 2] | None = None,
        solo_audio: bool | None = None,
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
        if canale_annunci is not None:  # MUS-058: il bot deve poterci scrivere
            permessi = canale_annunci.permissions_for(guild.me)
            if not (permessi.view_channel and permessi.send_messages and permessi.embed_links):
                await interaction.response.send_message(
                    await testo_per(interaction, "music_annunci_canale_senza_permessi"), ephemeral=True
                )
                return
        riserva = None
        if playlist_di_riserva is not None:  # MUS-041: deve essere una playlist del server
            riserva = _testo_o_vuoto(playlist_di_riserva)
            if riserva and await music_guild_playlist_repo.get(guild.id, riserva) is None:
                await interaction.response.send_message(
                    await testo_per(interaction, "playlist_server_non_trovata"), ephemeral=True
                )
                return
        paese_scelto = None
        if paese is not None:  # MUS-015: «-» toglie il filtro del server
            paese_scelto = None if paese.strip() == "-" else paese_valido(paese)
            if paese.strip() != "-" and paese_scelto is None:
                await interaction.response.send_message(await testo_per(interaction, "music_paese_non_valido"), ephemeral=True)
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
        if ricerca_predefinita is not None:  # «automatica» toglie la scelta (torna YouTube, poi SoundCloud)
            cambi[SETTING_DEFAULT_SEARCH] = None if ricerca_predefinita == "automatica" else ricerca_predefinita
        if coda is not None:  # MUS-037
            cambi[SETTING_QUEUE_MODE] = coda
        if riserva is not None:  # MUS-041: «-» la toglie
            cambi[SETTING_FALLBACK_PLAYLIST] = riserva
        if playlist_del_giorno is not None:  # MUS-045
            cambi[SETTING_DAILY_PLAYLIST] = playlist_del_giorno
        if coda_salvata is not None:  # MUS-042
            cambi[SETTING_PERSIST_QUEUE] = coda_salvata
        if prezzo_jukebox is not None:  # MUS-065: 0 lo spegne
            cambi[SETTING_JUKEBOX_PRICE] = prezzo_jukebox
        if ruolo_dj is not None and togli_ruolo_dj:
            await interaction.response.send_message(
                await testo_per(interaction, "settings_ruolo_dj_oppure_togli"), ephemeral=True
            )
            return
        if modalita_dj is not None:  # MUS-051
            cambi[SETTING_DJ_MODE] = modalita_dj
        if ruolo_dj is not None:
            cambi[SETTING_DJ_ROLE] = ruolo_dj.id
        if voto_salto is not None:  # MUS-052
            cambi[SETTING_SKIP_VOTE] = voto_salto
        if pausa_canale_vuoto is not None:  # MUS-053
            cambi[SETTING_EMPTY_PAUSE] = pausa_canale_vuoto
        if stato_bot is not None:  # MUS-061
            cambi[SETTING_BOT_STATUS] = stato_bot
        if paese is not None:  # MUS-015: None toglie la scelta
            cambi[SETTING_SEARCH_COUNTRY] = paese_scelto
        if solo_audio is not None:  # MUS-016
            cambi[SETTING_AUDIO_ONLY] = solo_audio
        if annunci is not None:  # MUS-057
            cambi[SETTING_ANNOUNCE] = annunci
        if canale_annunci is not None:  # MUS-058
            cambi[SETTING_ANNOUNCE_CHANNEL] = canale_annunci.id
        if canale_vocale is not None:
            cambi[SETTING_ALLOWED_CHANNEL] = canale_vocale.id
        if not cambi and not tutti_i_canali and not togli_ruolo_dj:
            await interaction.response.send_message(
                await testo_per(interaction, "settings_non_hai_cambiato_nulla_indica"),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        for chiave, valore in cambi.items():
            await save_music_setting(db, guild.id, chiave, valore, interaction.user.id)
        if togli_ruolo_dj:
            await save_music_setting(db, guild.id, SETTING_DJ_ROLE, None, interaction.user.id)
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
