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
    MAX_PLAYLIST_PER_SERVER,
    MAX_PLAYLIST_PER_UTENTE,
    NOME_MAX,
    LINK_ORIGINE_MAX,
    MAX_COLLABORATORI,
    brani_da_coda,
    brano_da_traccia,
    codice_valido,
    link_origine_valido,
    nome_per_copia,
    dati_playlist_wavelink,
    file_esportazione,
    leggi_file_importazione,
    nome_valido,
    pagina_brani,
    riferimenti_traccia,
    riga_elenco,
    togli_doppioni,
    togli_posizione,
    unisci_brani,
)
from core import music_sources as fonti_musicali
from core.music_logic import MSG_QUERY_RIFIUTATA, QUERY_RIFIUTATA, classify_query
from core.music_nodes import MAIN_KEY
from core.music_sound_logic import PausaUtente
from core.repositories.music_playlist_repo import (
    LimitePlaylistRaggiunto,
    music_guild_playlist_repo,
    music_playlist_repo,
)
from core.safe_http import url_e_sicuro

logger = logging.getLogger("iyokai.music.playlist")

PAUSA_CODICE = 5.0  # secondi tra due codici provati (per utente): chi indovina a caso viene frenato
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


class MusicPlaylistCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.pausa_ricerche = PausaUtente(pausa=PAUSA_RICERCA)
        self.pausa_codici = PausaUtente(pausa=PAUSA_CODICE)

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

    @comando_di_gruppo("music-playlist", nome="salva", descrizione="Salva la coda del tuo canale come playlist.")
    @app_commands.describe(
        nome="Nome della playlist (se esiste già, viene sostituita)",
        link="Un link https (di una playlist o di un brano) da salvare al posto della coda",
    )
    async def salva(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, NOME_MAX],
        link: app_commands.Range[str, 1, LINK_ORIGINE_MAX] | None = None,
    ) -> None:
        pulito = nome_valido(nome)
        if pulito is None:
            await interaction.response.send_message(MSG_NOME, ephemeral=True)
            return
        if link is not None:  # MUS-072: si salva da un link, senza bisogno di una coda
            await self._salva_da_link(interaction, pulito, link)
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

    async def _proprietario(self, interaction: discord.Interaction, di: discord.User | None, nome: str):
        """
        MUS-086: l'id di chi possiede la playlist su cui si lavora. Una playlist di un altro si tocca solo
        se il proprietario ti ha aggiunto come collaboratore; se no, stesso messaggio di «non esiste».
        None = già risposto.
        """
        if di is None or di.id == interaction.user.id:
            return interaction.user.id
        if await music_playlist_repo.puo_modificare(di.id, nome, interaction.user.id):
            return di.id
        await interaction.response.send_message(await testo_per(interaction, "playlist_non_hai_una_playlist_con"), ephemeral=True)
        return None

    def _frena(self, interaction: discord.Interaction) -> bool:
        """Vero se l'utente deve aspettare; se no segna subito la ricerca (prima di ogni await)."""
        chiave = interaction.guild_id or 0
        if self.pausa_ricerche.resta(chiave, interaction.user.id) > 0:
            return True
        self.pausa_ricerche.segna(chiave, interaction.user.id)
        return False

    async def _salva_da_link(self, interaction: discord.Interaction, nome: str, link: str) -> None:
        """MUS-072: salva una playlist da un link; il link resta come origine (MUS-083)."""
        origine = link_origine_valido(link)
        if origine is None:
            await interaction.response.send_message(await testo_per(interaction, "playlist_serve_link_https"), ephemeral=True)
            return
        if self._frena(interaction):
            await interaction.response.send_message(await testo_per(interaction, "playlist_piano_un_attimo"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        brani = await self._trova_brani(interaction, origine)
        if brani is None:
            return
        brani, doppioni = togli_doppioni(brani)
        try:
            nuova = await music_playlist_repo.save(interaction.user.id, nome, brani, origine)
        except LimitePlaylistRaggiunto:
            await interaction.followup.send(MSG_TETTO, ephemeral=True)
            return
        await interaction.followup.send(
            await testo_per(interaction, "playlist_salvata_da_link", nome=nome, v1=len(brani), v2=doppioni),
            ephemeral=True,
        )

    @comando_di_gruppo("music-playlist", nome="aggiorna", descrizione="Rilegge il link da cui hai salvato una playlist.")
    @app_commands.describe(nome="Nome della playlist salvata da un link")
    @app_commands.autocomplete(nome=_nomi)
    async def aggiorna(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, NOME_MAX]
    ) -> None:
        origine = await music_playlist_repo.origine(interaction.user.id, nome)  # MUS-083
        if origine is None:
            await interaction.response.send_message(await testo_per(interaction, "playlist_senza_link_di_origine"), ephemeral=True)
            return
        if self._frena(interaction):
            await interaction.response.send_message(await testo_per(interaction, "playlist_piano_un_attimo"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        brani = await self._trova_brani(interaction, origine)  # stessi controlli di /music play, anche sul link vecchio
        if brani is None:
            return
        brani, _ = togli_doppioni(brani)
        await music_playlist_repo.save(interaction.user.id, nome, brani, origine)
        await interaction.followup.send(
            await testo_per(interaction, "playlist_aggiornata", nome=nome, v1=len(brani)), ephemeral=True
        )

    @comando_di_gruppo("music-playlist", nome="condividi", descrizione="Crea un codice per condividere una tua playlist.")
    @app_commands.describe(nome="Nome della playlist", nuovo="Crea un codice nuovo: il vecchio smette di valere",
                           revoca="Togli il codice: nessuno potrà più usarlo")
    @app_commands.autocomplete(nome=_nomi)
    async def condividi(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, NOME_MAX],
        nuovo: bool = False,
        revoca: bool = False,
    ) -> None:
        if revoca:  # MUS-084
            tolto = await music_playlist_repo.revoca_codice(interaction.user.id, nome)
            chiave = "playlist_codice_revocato" if tolto else "playlist_nessun_codice"
            await interaction.response.send_message(await testo_per(interaction, chiave, nome=nome), ephemeral=True)
            return
        codice = await music_playlist_repo.codice(interaction.user.id, nome, nuovo=nuovo)
        if codice is None:
            await interaction.response.send_message(await testo_per(interaction, "playlist_non_hai_una_playlist_con"), ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "playlist_codice_di", nome=nome, codice=codice), ephemeral=True
        )

    @comando_di_gruppo("music-playlist", nome="ricevi", descrizione="Salva una copia di una playlist condivisa con un codice.")
    @app_commands.describe(codice="Il codice di 8 caratteri che ti ha dato chi condivide la playlist")
    async def ricevi(
        self, interaction: discord.Interaction, codice: app_commands.Range[str, 1, 20]
    ) -> None:
        chiave = interaction.guild_id or 0
        if self.pausa_codici.resta(chiave, interaction.user.id) > 0:  # frena chi prova codici a caso
            await interaction.response.send_message(await testo_per(interaction, "playlist_piano_un_attimo"), ephemeral=True)
            return
        self.pausa_codici.segna(chiave, interaction.user.id)
        pulito = codice_valido(codice)
        trovata = await music_playlist_repo.da_codice(pulito) if pulito else None
        if trovata is None or not trovata[2]:
            await interaction.response.send_message(await testo_per(interaction, "playlist_codice_non_valido"), ephemeral=True)
            return
        _proprietario, nome, brani = trovata
        nome_copia = nome_per_copia(nome, await music_playlist_repo.nomi(interaction.user.id))  # MUS-084
        try:
            await music_playlist_repo.save(interaction.user.id, nome_copia, brani)
        except LimitePlaylistRaggiunto:
            await interaction.response.send_message(MSG_TETTO, ephemeral=True)
            return
        await interaction.response.send_message(
            await testo_per(interaction, "playlist_copia_ricevuta", nome=nome_copia, v1=len(brani)), ephemeral=True
        )

    @comando_di_gruppo("music-playlist", nome="carica", descrizione="Mette in coda una tua playlist salvata.")
    @app_commands.describe(nome="Nome della playlist",
                           di="Il proprietario, per una playlist condivisa con te come collaboratore")
    @app_commands.autocomplete(nome=_nomi)
    async def carica(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, NOME_MAX],
        di: discord.User | None = None,
    ) -> None:
        musica = self._musica()
        if musica is None:
            await interaction.response.send_message(await testo_per(interaction, "soundboard_la_musica_non_disponibile_ora"), ephemeral=True)
            return
        if not await musica.controlli_base(interaction):
            return
        proprietario = await self._proprietario(interaction, di, nome)  # MUS-086
        if proprietario is None:
            return
        await interaction.response.defer()
        brani = await music_playlist_repo.get(proprietario, nome)
        if not brani:
            await interaction.followup.send(await testo_per(interaction, "playlist_non_hai_una_playlist_con", pubblica=True))
            return
        await self._metti_in_coda(musica, interaction, nome, brani)

    @staticmethod
    async def _metti_in_coda(musica, interaction: discord.Interaction, nome: str, brani) -> None:
        """Decodifica i brani sul nodo del worker (con i controlli di sicurezza) e li mette in coda."""

        async def cerca(nodo, _nodo_locale):
            return await decodifica_brani(nodo, nome, brani), nodo

        await musica.accoda(
            interaction.guild, interaction.user, nome, interaction.followup.send,
            interaction=interaction, cerca=cerca,
        )


    @comando_di_gruppo("music-playlist", nome="elenco", descrizione="Le tue playlist salvate, o i brani di una.")
    @app_commands.describe(nome="Una playlist di cui vedere i brani (vuoto = l'elenco delle playlist)",
                           pagina="Pagina dei brani (da 1)",
                           di="Il proprietario, per una playlist condivisa con te come collaboratore")
    @app_commands.autocomplete(nome=_nomi)
    async def elenco(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, NOME_MAX] | None = None,
        pagina: app_commands.Range[int, 1, 50] = 1,
        di: discord.User | None = None,
    ) -> None:
        if nome is not None:  # MUS-079: il dettaglio dei brani, a pagine
            proprietario = await self._proprietario(interaction, di, nome)  # MUS-086
            if proprietario is None:
                return
            brani = await music_playlist_repo.get(proprietario, nome)
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
        condivise = await music_playlist_repo.condivise_con(interaction.user.id)  # MUS-086
        if not riassunti and not condivise:
            await interaction.response.send_message(
                await testo_per(interaction, "playlist_non_hai_playlist_salvate_mettine"),
                ephemeral=True,
            )
            return
        righe = [riga_elenco(r.nome, r.numero_brani, r.durata_ms) for r in riassunti]
        if condivise:
            righe.append(await testo_per(interaction, "playlist_condivise_con_te"))
            righe += [f"**{nome_c[:50]}** — <@{proprietario}>" for proprietario, nome_c in condivise]
        embed = discord.Embed(
            title=await testo_per(interaction, "playlist_le_tue_playlist", v1=len(riassunti), v2=MAX_PLAYLIST_PER_UTENTE),
            description="\n".join(righe)[:4000],
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @comando_di_gruppo("music-playlist", nome="crea", descrizione="Crea una playlist vuota.")
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

    @comando_di_gruppo("music-playlist", nome="aggiungi", descrizione="Aggiunge un brano (o un link) a una tua playlist.")
    @app_commands.describe(nome="Nome della playlist", brano="Titolo o link del brano",
                           di="Il proprietario, se la playlist è sua e ti ha messo tra i collaboratori")
    @app_commands.autocomplete(nome=_nomi)
    async def aggiungi(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, NOME_MAX],
        brano: app_commands.Range[str, 1, 300],
        di: discord.User | None = None,
    ) -> None:
        # MUS-074: la pausa si segna prima del primo await (due comandi insieme non passano)
        if self._frena(interaction):
            await interaction.response.send_message(await testo_per(interaction, "playlist_piano_un_attimo"), ephemeral=True)
            return
        proprietario = await self._proprietario(interaction, di, nome)  # MUS-086
        if proprietario is None:
            return
        await interaction.response.defer(ephemeral=True)
        if await music_playlist_repo.get(proprietario, nome) is None:
            await interaction.followup.send(await testo_per(interaction, "playlist_non_hai_una_playlist_con"), ephemeral=True)
            return
        nuovi = await self._trova_brani(interaction, brano)
        if nuovi is None:
            return
        esito = await music_playlist_repo.aggiorna_brani(
            proprietario, nome, lambda esistenti: unisci_brani(esistenti, nuovi)
        )
        if esito is None:
            await interaction.followup.send(await testo_per(interaction, "playlist_non_hai_una_playlist_con"), ephemeral=True)
            return
        aggiunti, doppioni, fuori = esito
        await interaction.followup.send(
            await testo_per(interaction, "playlist_aggiunti", nome=nome, v1=aggiunti, v2=doppioni, v3=fuori),
            ephemeral=True,
        )

    @comando_di_gruppo("music-playlist", nome="togli", descrizione="Toglie un brano da una tua playlist.")
    @app_commands.describe(nome="Nome della playlist", posizione="Numero del brano (lo vedi con /music-playlist elenco)",
                           di="Il proprietario, se la playlist è sua e ti ha messo tra i collaboratori")
    @app_commands.autocomplete(nome=_nomi)
    async def togli(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, NOME_MAX],
        posizione: app_commands.Range[int, 1, MAX_BRANI_PER_PLAYLIST],
        di: discord.User | None = None,
    ) -> None:
        proprietario = await self._proprietario(interaction, di, nome)  # MUS-086
        if proprietario is None:
            return
        esito = await music_playlist_repo.aggiorna_brani(
            proprietario, nome, lambda brani: togli_posizione(brani, posizione)  # MUS-075
        )
        if esito is None and await music_playlist_repo.get(proprietario, nome) is None:
            testo = await testo_per(interaction, "playlist_non_hai_una_playlist_con")
        elif esito is None:
            testo = await testo_per(interaction, "playlist_nessun_brano_in_posizione", v1=posizione)
        else:
            testo = await testo_per(interaction, "playlist_brano_tolto", titolo=esito.titolo[:100], nome=nome)
        await interaction.response.send_message(testo, ephemeral=True)

    @comando_di_gruppo("music-playlist", nome="rinomina", descrizione="Cambia il nome di una tua playlist.")
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

    @comando_di_gruppo("music-playlist", nome="elimina", descrizione="Cancella una tua playlist salvata.")
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


    @comando_di_gruppo("music-playlist", nome="esporta", descrizione="Scarica una tua playlist come file.")
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


    @comando_di_gruppo("music-playlist", nome="importa", descrizione="Salva una playlist da un file esportato.")
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


    @comando_di_gruppo("music-playlist", nome="collabora", descrizione="Chi può modificare una tua playlist.")
    @app_commands.describe(nome="Nome della tua playlist", utente="La persona da aggiungere o togliere",
                           togli="Togli la persona invece di aggiungerla")
    @app_commands.autocomplete(nome=_nomi)
    async def collabora(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, NOME_MAX],
        utente: discord.User | None = None,
        togli: bool = False,
    ) -> None:
        """MUS-086: playlist a più mani. Senza `utente` mostra chi può modificarla."""
        if utente is None:
            elenco = await music_playlist_repo.collaboratori(interaction.user.id, nome)
            testo = (
                await testo_per(interaction, "playlist_collaboratori", nome=nome, utenti=", ".join(f"<@{u}>" for u in elenco))
                if elenco else await testo_per(interaction, "playlist_nessun_collaboratore", nome=nome)
            )
            await interaction.response.send_message(testo, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            return
        if togli:
            tolto = await music_playlist_repo.togli_collaboratore(interaction.user.id, nome, utente.id)
            chiave = "playlist_collaboratore_tolto" if tolto else "playlist_collaboratore_assente"
        elif utente.bot or utente.id == interaction.user.id:
            chiave = "playlist_collaboratore_non_valido"
        else:
            esito = await music_playlist_repo.aggiungi_collaboratore(interaction.user.id, nome, utente.id)
            chiave = {
                "ok": "playlist_collaboratore_aggiunto", "gia": "playlist_collaboratore_gia",
                "pieno": "playlist_collaboratori_pieno",
            }.get(esito, "playlist_non_hai_una_playlist_con")
        await interaction.response.send_message(
            await testo_per(interaction, chiave, nome=nome, utente=f"<@{utente.id}>", v1=MAX_COLLABORATORI),
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )

    # ------------------------------------------------------------------
    # MUS-081: playlist del server (le gestisce chi ha «Gestisci server»)
    # ------------------------------------------------------------------
    async def _nomi_server(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if interaction.guild_id is None:
            return []
        riassunti = await music_guild_playlist_repo.list_for_guild(interaction.guild_id)
        attuale = (current or "").lower()
        return [app_commands.Choice(name=r.nome, value=r.nome) for r in riassunti if attuale in r.nome.lower()][:25]

    @staticmethod
    def _puo_gestire(interaction: discord.Interaction) -> bool:
        permessi = getattr(interaction.user, "guild_permissions", None)
        return bool(permessi and permessi.manage_guild)

    @comando_di_gruppo("music-playlist", nome="server-salva", descrizione="Salva la coda come playlist del server.")
    @app_commands.describe(nome="Nome della playlist del server (se esiste già, viene sostituita)")
    async def server_salva(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, NOME_MAX]
    ) -> None:
        if interaction.guild_id is None or not self._puo_gestire(interaction):
            await interaction.response.send_message(await testo_per(interaction, "playlist_serve_gestisci_server"), ephemeral=True)
            return
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
        brani, _fuori = brani_da_coda(player.current, player.queue)
        brani, _doppioni = togli_doppioni(brani)
        if not brani:
            await interaction.response.send_message(await testo_per(interaction, "playlist_non_niente_da_salvare_la"), ephemeral=True)
            return
        try:
            nuova = await music_guild_playlist_repo.save(interaction.guild_id, pulito, brani, interaction.user.id)
        except LimitePlaylistRaggiunto:
            await interaction.response.send_message(
                await testo_per(interaction, "playlist_server_tetto", v1=MAX_PLAYLIST_PER_SERVER), ephemeral=True
            )
            return
        chiave = "playlist_server_salvata" if nuova else "playlist_server_aggiornata"
        await interaction.response.send_message(
            await testo_per(interaction, chiave, nome=pulito, v1=len(brani)), ephemeral=True
        )

    @comando_di_gruppo("music-playlist", nome="server-carica", descrizione="Mette in coda una playlist del server.")
    @app_commands.describe(nome="Nome della playlist del server")
    @app_commands.autocomplete(nome=_nomi_server)
    async def server_carica(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, NOME_MAX]
    ) -> None:
        musica = self._musica()
        if musica is None or interaction.guild_id is None:
            await interaction.response.send_message(await testo_per(interaction, "soundboard_la_musica_non_disponibile_ora"), ephemeral=True)
            return
        if not await musica.controlli_base(interaction):
            return
        await interaction.response.defer()
        brani = await music_guild_playlist_repo.get(interaction.guild_id, nome)
        if not brani:
            await interaction.followup.send(await testo_per(interaction, "playlist_server_non_trovata", pubblica=True))
            return
        await self._metti_in_coda(musica, interaction, nome, brani)

    @comando_di_gruppo("music-playlist", nome="server-elenco", descrizione="Le playlist del server.")
    async def server_elenco(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        riassunti = await music_guild_playlist_repo.list_for_guild(interaction.guild_id)
        if not riassunti:
            await interaction.response.send_message(await testo_per(interaction, "playlist_server_nessuna"), ephemeral=True)
            return
        embed = discord.Embed(
            title=await testo_per(interaction, "playlist_server_titolo", v1=len(riassunti), v2=MAX_PLAYLIST_PER_SERVER),
            description="\n".join(riga_elenco(r.nome, r.numero_brani, r.durata_ms) for r in riassunti),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo("music-playlist", nome="server-elimina", descrizione="Cancella una playlist del server.")
    @app_commands.describe(nome="Nome della playlist del server")
    @app_commands.autocomplete(nome=_nomi_server)
    async def server_elimina(
        self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, NOME_MAX]
    ) -> None:
        if interaction.guild_id is None or not self._puo_gestire(interaction):
            await interaction.response.send_message(await testo_per(interaction, "playlist_serve_gestisci_server"), ephemeral=True)
            return
        tolta = await music_guild_playlist_repo.delete(interaction.guild_id, nome)
        chiave = "playlist_playlist_cancellata" if tolta else "playlist_server_non_trovata"
        await interaction.response.send_message(await testo_per(interaction, chiave, nome=nome), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicPlaylistCog(bot))
