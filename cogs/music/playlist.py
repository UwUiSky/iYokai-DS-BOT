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
from core.i18n import testo_per
from core.music_playlist_logic import (
    FILE_MAX_BYTE,
    MAX_BRANI_PER_PLAYLIST,
    MAX_PLAYLIST_PER_UTENTE,
    NOME_MAX,
    aggiungi_senza_doppioni,
    brani_da_coda,
    brano_da_traccia,
    dati_playlist_wavelink,
    file_esportazione,
    leggi_file_importazione,
    nome_valido,
    pagina_brani,
    riferimenti_traccia,
    riga_elenco,
    togli_doppioni,
    togli_posizione,
)
from core import music_sources as fonti_musicali
from core.music_logic import MSG_QUERY_RIFIUTATA, QUERY_RIFIUTATA, classify_query
from core.music_nodes import MAIN_KEY
from core.music_sound_logic import PausaUtente
from core.repositories.music_playlist_repo import LimitePlaylistRaggiunto, music_playlist_repo
from core.safe_http import url_e_sicuro

logger = logging.getLogger("iyokai.music.playlist")

PAUSA_RICERCA = 3.0  # secondi tra due ricerche di brani da aggiungere a una playlist (per utente)

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


def _unisci(esistenti, nuovi):
    """Per `aggiorna_brani`: aggiunge i brani nuovi senza doppioni; il risultato sono i conteggi."""
    elenco, aggiunti, doppioni, fuori = aggiungi_senza_doppioni(esistenti, nuovi)
    return elenco, (aggiunti, doppioni, fuori)


class MusicPlaylistCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.pausa_ricerche = PausaUtente(pausa=PAUSA_RICERCA)

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
            await interaction.response.send_message(await testo_per(interaction, "soundboard_la_musica_non_disponibile_ora"), ephemeral=True)
            return
        player = await musica._giocatore_attivo(interaction)
        if player is None:
            return
        brani, fuori = brani_da_coda(player.current, player.queue)
        if not brani:
            await interaction.response.send_message(await testo_per(interaction, "playlist_non_niente_da_salvare_la"), ephemeral=True)
            return
        brani, doppioni = togli_doppioni(brani)  # MUS-076: fatto da solo al salvataggio
        await interaction.response.defer(ephemeral=True)
        try:
            nuova = await music_playlist_repo.save(interaction.user.id, pulito, brani)
        except LimitePlaylistRaggiunto:
            await interaction.followup.send(MSG_TETTO, ephemeral=True)
            return
        testo = f"💾 Playlist **{pulito}** {'salvata' if nuova else 'aggiornata'}: {len(brani)} brani."
        if fuori:
            testo += f" ({fuori} oltre il massimo di {MAX_BRANI_PER_PLAYLIST} non salvati.)"
        if doppioni:
            testo += f" ({doppioni} doppioni tolti.)"
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
            await interaction.response.send_message(await testo_per(interaction, "soundboard_la_musica_non_disponibile_ora"), ephemeral=True)
            return
        if not await musica._controlli_base(interaction):
            return
        await interaction.response.defer()
        brani = await music_playlist_repo.get(interaction.user.id, nome)
        if not brani:
            await interaction.followup.send(await testo_per(interaction, "playlist_non_hai_una_playlist_con", pubblica=True))
            return

        async def cerca(nodo, _nodo_locale):
            return await decodifica_brani(nodo, nome, brani), nodo

        await musica.accoda(
            interaction.guild, interaction.user, nome, interaction.followup.send,
            interaction=interaction, cerca=cerca,
        )


    @comando_di_gruppo("music", nome="elenco", descrizione="Le tue playlist salvate, o i brani di una.",
                       sottogruppo=SG_PLAYLIST)
    @app_commands.describe(nome="Una playlist di cui vedere i brani (vuoto = l'elenco delle playlist)",
                           pagina="Pagina dei brani (da 1)")
    @app_commands.autocomplete(nome=_nomi)
    async def elenco(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, NOME_MAX] | None = None,
        pagina: app_commands.Range[int, 1, 50] = 1,
    ) -> None:
        if nome is not None:  # MUS-079: il dettaglio dei brani, a pagine
            brani = await music_playlist_repo.get(interaction.user.id, nome)
            if brani is None:
                await interaction.response.send_message(await testo_per(interaction, "playlist_non_hai_una_playlist_con"), ephemeral=True)
                return
            righe, pagine = pagina_brani(brani, pagina)
            embed = discord.Embed(
                title=f"📃 {nome[:100]} ({len(brani)})",
                description="\n".join(righe) or await testo_per(interaction, "playlist_vuota"),
                color=discord.Color.blurple(),
            )
            embed.set_footer(text=await testo_per(interaction, "playlist_pagina_di", v1=min(pagina, pagine), v2=pagine))
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        riassunti = await music_playlist_repo.list_for_user(interaction.user.id)
        if not riassunti:
            await interaction.response.send_message(
                await testo_per(interaction, "playlist_non_hai_playlist_salvate_mettine"),
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title=await testo_per(interaction, "playlist_le_tue_playlist", v1=len(riassunti), v2=MAX_PLAYLIST_PER_UTENTE),
            description="\n".join(riga_elenco(r.nome, r.numero_brani, r.durata_ms) for r in riassunti),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo("music", nome="crea", descrizione="Crea una playlist vuota.", sottogruppo=SG_PLAYLIST)
    @app_commands.describe(nome="Nome della nuova playlist")
    async def crea(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, NOME_MAX]) -> None:
        pulito = nome_valido(nome)  # MUS-073
        if pulito is None:
            await interaction.response.send_message(MSG_NOME, ephemeral=True)
            return
        try:
            creata = await music_playlist_repo.crea_vuota(interaction.user.id, pulito)
        except LimitePlaylistRaggiunto:
            await interaction.response.send_message(MSG_TETTO, ephemeral=True)
            return
        chiave = "playlist_creata" if creata else "playlist_esiste_gia"
        await interaction.response.send_message(await testo_per(interaction, chiave, nome=pulito), ephemeral=True)

    async def _trova_brani(self, interaction: discord.Interaction, query: str) -> list | None:
        """Cerca i brani di un titolo o link (stessi controlli di /music play). None = già risposto."""
        musica = self._musica()
        gestore = getattr(self.bot, "music_nodes", None)
        nodo = gestore.node_for(MAIN_KEY) if gestore is not None else None
        if musica is None or nodo is None:
            await interaction.followup.send(await testo_per(interaction, "music_nessun_nodo"), ephemeral=True)
            return None
        if classify_query(query) == QUERY_RIFIUTATA:
            await interaction.followup.send(MSG_QUERY_RIFIUTATA, ephemeral=True)
            return None
        try:
            risultati = await musica._cerca_su(query, nodo)
        except fonti_musicali.FonteNonRisponde as exc:
            await interaction.followup.send(
                await fonti_musicali.messaggio_per_fonte(exc.fonte, interaction.guild_id, interaction.user.id),
                ephemeral=True,
            )
            return None
        except wavelink.exceptions.WavelinkException:
            logger.warning("Ricerca per la playlist fallita.", exc_info=True)
            risultati = None
        if not risultati:
            await interaction.followup.send(await testo_per(interaction, "music_nessun_risultato"), ephemeral=True)
            return None
        tracce = list(risultati.tracks) if isinstance(risultati, wavelink.Playlist) else [risultati[0]]
        return [b for b in (brano_da_traccia(t) for t in tracce[:MAX_BRANI_PER_PLAYLIST]) if b is not None]

    @comando_di_gruppo("music", nome="aggiungi", descrizione="Aggiunge un brano (o un link) a una tua playlist.",
                       sottogruppo=SG_PLAYLIST)
    @app_commands.describe(nome="Nome della playlist", brano="Titolo o link del brano")
    @app_commands.autocomplete(nome=_nomi)
    async def aggiungi(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, NOME_MAX],
        brano: app_commands.Range[str, 1, 300],
    ) -> None:
        # MUS-074: la pausa si segna prima del primo await (due comandi insieme non passano)
        chiave = interaction.guild_id or 0
        if self.pausa_ricerche.resta(chiave, interaction.user.id) > 0:
            await interaction.response.send_message(await testo_per(interaction, "playlist_piano_un_attimo"), ephemeral=True)
            return
        self.pausa_ricerche.segna(chiave, interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        if await music_playlist_repo.get(interaction.user.id, nome) is None:
            await interaction.followup.send(await testo_per(interaction, "playlist_non_hai_una_playlist_con"), ephemeral=True)
            return
        nuovi = await self._trova_brani(interaction, brano)
        if nuovi is None:
            return
        esito = await music_playlist_repo.aggiorna_brani(
            interaction.user.id, nome, lambda esistenti: _unisci(esistenti, nuovi)
        )
        if esito is None:
            await interaction.followup.send(await testo_per(interaction, "playlist_non_hai_una_playlist_con"), ephemeral=True)
            return
        aggiunti, doppioni, fuori = esito
        await interaction.followup.send(
            await testo_per(interaction, "playlist_aggiunti", nome=nome, v1=aggiunti, v2=doppioni, v3=fuori),
            ephemeral=True,
        )

    @comando_di_gruppo("music", nome="togli", descrizione="Toglie un brano da una tua playlist.",
                       sottogruppo=SG_PLAYLIST)
    @app_commands.describe(nome="Nome della playlist", posizione="Numero del brano (lo vedi con /music playlist elenco)")
    @app_commands.autocomplete(nome=_nomi)
    async def togli(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, NOME_MAX],
        posizione: app_commands.Range[int, 1, MAX_BRANI_PER_PLAYLIST],
    ) -> None:
        esito = await music_playlist_repo.aggiorna_brani(
            interaction.user.id, nome, lambda brani: togli_posizione(brani, posizione)  # MUS-075
        )
        if esito is None and await music_playlist_repo.get(interaction.user.id, nome) is None:
            testo = await testo_per(interaction, "playlist_non_hai_una_playlist_con")
        elif esito is None:
            testo = await testo_per(interaction, "playlist_nessun_brano_in_posizione", v1=posizione)
        else:
            testo = await testo_per(interaction, "playlist_brano_tolto", titolo=esito.titolo[:100], nome=nome)
        await interaction.response.send_message(testo, ephemeral=True)

    @comando_di_gruppo("music", nome="rinomina", descrizione="Cambia il nome di una tua playlist.",
                       sottogruppo=SG_PLAYLIST)
    @app_commands.describe(nome="Nome attuale", nuovo="Nuovo nome")
    @app_commands.autocomplete(nome=_nomi)
    async def rinomina(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, NOME_MAX],
        nuovo: app_commands.Range[str, 1, NOME_MAX],
    ) -> None:
        pulito = nome_valido(nuovo)  # MUS-077
        if pulito is None:
            await interaction.response.send_message(MSG_NOME, ephemeral=True)
            return
        esito = await music_playlist_repo.rinomina(interaction.user.id, nome, pulito)
        chiave = {"ok": "playlist_rinominata", "esiste": "playlist_esiste_gia"}.get(esito, "playlist_non_hai_una_playlist_con")
        await interaction.response.send_message(await testo_per(interaction, chiave, nome=pulito), ephemeral=True)

    @comando_di_gruppo("music", nome="elimina", descrizione="Cancella una tua playlist salvata.",
                       sottogruppo=SG_PLAYLIST)
    @app_commands.describe(nome="Nome della playlist")
    @app_commands.autocomplete(nome=_nomi)
    async def elimina(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, NOME_MAX]
    ) -> None:
        tolta = await music_playlist_repo.delete(interaction.user.id, nome)
        await interaction.response.send_message(
            await testo_per(interaction, "playlist_playlist_cancellata", nome=nome) if tolta else await testo_per(interaction, "playlist_non_hai_una_playlist_con"),
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
            await interaction.response.send_message(await testo_per(interaction, "playlist_non_hai_una_playlist_con"), ephemeral=True)
            return
        nome_file = re.sub(r"[^\w-]+", "_", nome)[:40] or "playlist"
        file = discord.File(io.BytesIO(file_esportazione(nome, brani)), filename=f"{nome_file}.json")
        await interaction.response.send_message(
            await testo_per(interaction, "playlist_playlist_brani_la_ricarichi_con", nome=nome, v2=len(brani)),
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
                await testo_per(interaction, "playlist_il_file_supera_kb", v1=FILE_MAX_BYTE // 1024), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            contenuto = await file.read()
        except discord.HTTPException:
            await interaction.followup.send(await testo_per(interaction, "playlist_non_riesco_leggere_il_file"), ephemeral=True)
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
            await testo_per(interaction, "playlist_playlist_importata_brani", pulito=pulito, v2=len(brani)), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicPlaylistCog(bot))
