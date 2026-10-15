"""
cogs/music/playlist.py
======================
Playlist salvate degli utenti: salvare la coda del proprio canale,
ricaricarla in ogni server, elencarle, cancellarle, scaricarle come file
e ricaricarle da un file.
Funzioni coperte: SPEC §23 (NF-19), catalogo MUS-082
Dipende da: cogs/music/player.py (MusicCog.accoda e controlli comuni),
core/music_playlist_logic.py, core/repositories/music_playlist_repo.py.
"""

from __future__ import annotations

import io
import logging
import re

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.music_playlist_logic import (
    FILE_MAX_BYTE,
    MAX_BRANI_PER_PLAYLIST,
    MAX_PLAYLIST_PER_UTENTE,
    NOME_MAX,
    brani_da_coda,
    dati_playlist_wavelink,
    file_esportazione,
    leggi_file_importazione,
    nome_valido,
    riferimenti_traccia,
    riga_elenco,
)
from core.repositories.music_playlist_repo import LimitePlaylistRaggiunto, music_playlist_repo
from core.safe_http import url_e_sicuro

logger = logging.getLogger("iyokai.music.playlist")

SG_PLAYLIST = ("playlist", "Le tue playlist salvate: valgono in ogni server.")
MSG_NOME = (
    f"Nome non valido: da 1 a {NOME_MAX} caratteri, lettere, numeri, spazi e punteggiatura semplice."
)
MSG_TETTO = f"Hai già {MAX_PLAYLIST_PER_UTENTE} playlist: cancellane una prima di salvarne un'altra."


async def decodifica_brani(nodo: wavelink.Node, nome: str, brani) -> wavelink.Playlist | None:
    """Una sola richiesta a Lavalink (/v4/decodetracks) per tutti i brani salvati."""
    try:
        tracce = await nodo.send("POST", path="v4/decodetracks", data=[b.encoded for b in brani])
    except (wavelink.exceptions.WavelinkException, OSError):
        logger.warning("Decodifica della playlist non riuscita sul nodo %s.", nodo.identifier)
        return None
    if not isinstance(tracce, list):
        return None
    # Un `encoded` arriva anche da un file importato: si suona solo cio' che
    # Lavalink puo' leggere in sicurezza (niente file locali, niente URL interni).
    controllati: dict[str, bool] = {}
    ammesse = []
    for traccia in tracce:
        riferimenti = riferimenti_traccia(traccia.get("info") if isinstance(traccia, dict) else None)
        if riferimenti is None:
            continue
        for url in riferimenti:
            if url not in controllati:
                controllati[url] = await url_e_sicuro(url)
        if all(controllati[url] for url in riferimenti):
            ammesse.append(traccia)
    if len(ammesse) < len(tracce):
        logger.info("Playlist %r: %d brani rifiutati (file locali o URL non pubblici).",
                    nome, len(tracce) - len(ammesse))
    if not ammesse:
        return None
    return wavelink.Playlist(dati_playlist_wavelink(nome, ammesse))


class MusicPlaylistCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _musica(self):
        return self.bot.get_cog("MusicCog")

    async def _nomi(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        riassunti = await music_playlist_repo.list_for_user(interaction.user.id)
        attuale = (current or "").lower()
        return [
            app_commands.Choice(name=r.nome, value=r.nome)
            for r in riassunti
            if attuale in r.nome.lower()
        ][:25]

    @comando_di_gruppo("music", nome="salva", descrizione="Salva la coda del tuo canale come playlist.",
                       sottogruppo=SG_PLAYLIST)
    @app_commands.describe(nome="Nome della playlist (se esiste già, viene sostituita)")
    async def salva(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, NOME_MAX]
    ) -> None:
        pulito = nome_valido(nome)
        if pulito is None:
            await interaction.response.send_message(MSG_NOME, ephemeral=True)
            return
        musica = self._musica()
        if musica is None:
            await interaction.response.send_message("La musica non è disponibile ora.", ephemeral=True)
            return
        player = await musica._giocatore_attivo(interaction)
        if player is None:
            return
        brani, fuori = brani_da_coda(player.current, player.queue)
        if not brani:
            await interaction.response.send_message("Non c'è niente da salvare: la coda è vuota.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            nuova = await music_playlist_repo.save(interaction.user.id, pulito, brani)
        except LimitePlaylistRaggiunto:
            await interaction.followup.send(MSG_TETTO, ephemeral=True)
            return
        testo = f"💾 Playlist **{pulito}** {'salvata' if nuova else 'aggiornata'}: {len(brani)} brani."
        if fuori:
            testo += f" ({fuori} oltre il massimo di {MAX_BRANI_PER_PLAYLIST} non salvati.)"
        await interaction.followup.send(testo, ephemeral=True)

    @comando_di_gruppo("music", nome="carica", descrizione="Mette in coda una tua playlist salvata.",
                       sottogruppo=SG_PLAYLIST)
    @app_commands.describe(nome="Nome della playlist")
    @app_commands.autocomplete(nome=_nomi)
    async def carica(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, NOME_MAX]
    ) -> None:
        musica = self._musica()
        if musica is None:
            await interaction.response.send_message("La musica non è disponibile ora.", ephemeral=True)
            return
        if not await musica._controlli_base(interaction):
            return
        await interaction.response.defer()
        brani = await music_playlist_repo.get(interaction.user.id, nome)
        if not brani:
            await interaction.followup.send("Non hai una playlist con questo nome.")
            return

        async def cerca(nodo, _nodo_locale):
            return await decodifica_brani(nodo, nome, brani), nodo

        await musica.accoda(
            interaction.guild, interaction.user, nome, interaction.followup.send,
            interaction=interaction, cerca=cerca,
        )


    @comando_di_gruppo("music", nome="elenco", descrizione="Le tue playlist salvate.",
                       sottogruppo=SG_PLAYLIST)
    async def elenco(self, interaction: discord.Interaction) -> None:
        riassunti = await music_playlist_repo.list_for_user(interaction.user.id)
        if not riassunti:
            await interaction.response.send_message(
                "Non hai playlist salvate. Mettine una in coda e salvala con il comando salva.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title=f"💾 Le tue playlist ({len(riassunti)}/{MAX_PLAYLIST_PER_UTENTE})",
            description="\n".join(riga_elenco(r.nome, r.numero_brani, r.durata_ms) for r in riassunti),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo("music", nome="elimina", descrizione="Cancella una tua playlist salvata.",
                       sottogruppo=SG_PLAYLIST)
    @app_commands.describe(nome="Nome della playlist")
    @app_commands.autocomplete(nome=_nomi)
    async def elimina(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, NOME_MAX]
    ) -> None:
        tolta = await music_playlist_repo.delete(interaction.user.id, nome)
        await interaction.response.send_message(
            f"🗑️ Playlist **{nome}** cancellata." if tolta else "Non hai una playlist con questo nome.",
            ephemeral=True,
        )


    @comando_di_gruppo("music", nome="esporta", descrizione="Scarica una tua playlist come file.",
                       sottogruppo=SG_PLAYLIST)
    @app_commands.describe(nome="Nome della playlist")
    @app_commands.autocomplete(nome=_nomi)
    async def esporta(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, NOME_MAX]
    ) -> None:
        brani = await music_playlist_repo.get(interaction.user.id, nome)
        if not brani:
            await interaction.response.send_message("Non hai una playlist con questo nome.", ephemeral=True)
            return
        nome_file = re.sub(r"[^\w-]+", "_", nome)[:40] or "playlist"
        file = discord.File(io.BytesIO(file_esportazione(nome, brani)), filename=f"{nome_file}.json")
        await interaction.response.send_message(
            f"📄 Playlist **{nome}** ({len(brani)} brani). La ricarichi con il comando importa.",
            file=file,
            ephemeral=True,
        )


    @comando_di_gruppo("music", nome="importa", descrizione="Salva una playlist da un file esportato.",
                       sottogruppo=SG_PLAYLIST)
    @app_commands.describe(file="Il file .json esportato", nome="Nome da dare alla playlist")
    async def importa(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        nome: app_commands.Range[str, 1, NOME_MAX],
    ) -> None:
        pulito = nome_valido(nome)
        if pulito is None:
            await interaction.response.send_message(MSG_NOME, ephemeral=True)
            return
        if file.size > FILE_MAX_BYTE:
            await interaction.response.send_message(
                f"Il file supera {FILE_MAX_BYTE // 1024} KB.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            contenuto = await file.read()
        except discord.HTTPException:
            await interaction.followup.send("Non riesco a leggere il file.", ephemeral=True)
            return
        brani, errore = leggi_file_importazione(contenuto)
        if errore:
            await interaction.followup.send(errore, ephemeral=True)
            return
        try:
            await music_playlist_repo.save(interaction.user.id, pulito, brani)
        except LimitePlaylistRaggiunto:
            await interaction.followup.send(MSG_TETTO, ephemeral=True)
            return
        await interaction.followup.send(
            f"📥 Playlist **{pulito}** importata: {len(brani)} brani.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicPlaylistCog(bot))
