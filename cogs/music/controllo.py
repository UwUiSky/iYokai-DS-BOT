"""
cogs/music/controllo.py
=======================
Controllo della coda e del brano: `/music coda togli|ultimo|miei|sposta|cima|subito` (MUS-024, 025, 026, 028, 022, 023),
`/music brano ricomincia|vai-a|cerca` (MUS-033, 034, 013). Chi non è DJ o staff tocca solo i propri brani.
Funzioni coperte: SPEC §9 (catalogo MUS-013, 022-026, 028, 033, 034)
Dipende da: cogs/music/player.py (MusicCog: player attivo, privilegi, ricerca), core/music_dj_logic.py
"""

from __future__ import annotations

import asyncio
import logging
import time

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import lingua_interazione, t, testo_per
from core.music_cerca_view import CercaView, Risultato, risultati_da_tracce
from core.music_dj_logic import parse_posizione, puo_toccare_brano
from core.music_lyrics_logic import (
    ServizioNonRisponde, cerca_testi, indice_riga, leggi_lrc, testo_karaoke, tronca_testo,
)
from core.music_logic import QUERY_TESTO, classify_query, format_duration, truncate_title
from core.music_nodes import MAIN_KEY
from core.music_queue_logic import requester_of
from core.music_settings_logic import load_music_settings, title_blocked, track_too_long
from core.music_sound_logic import PausaUtente
from cogs.music.player import SG_CODA

logger = logging.getLogger("iyokai.music.controllo")

SG_BRANO = ("brano", "Posizione nel brano e ricerca con scelta.")
PAUSA_RICERCA = 3.0  # secondi tra due ricerche dello stesso utente
PAUSA_TESTI = 5.0  # secondi tra due richieste di testi dello stesso utente
KARAOKE_INTERVALLO = 2.5  # secondi tra due controlli: Discord limita le modifiche dei messaggi
KARAOKE_DURATA_MAX = 14 * 60  # il messaggio si modifica col gettone dell'interazione, che vale 15 minuti
NESSUNA_MENZIONE = discord.AllowedMentions.none()  # i titoli arrivano da fuori: mai @everyone


def riordina_coda(player, tracce: list) -> None:
    """Rimette la coda in questo ordine senza nessun await in mezzo: nessun altro comando la vede vuota."""
    player.queue.clear()
    player.queue.put(tracce)


def sposta_elemento(tracce: list, da: int, a: int) -> list:
    """Una copia della lista con l'elemento in `da` portato in `a` (indici da 0; `a` tagliato alla lunghezza)."""
    nuova = list(tracce)
    elemento = nuova.pop(da)
    nuova.insert(max(0, min(a, len(nuova))), elemento)
    return nuova


class MusicControlloCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.pausa_ricerche = PausaUtente(pausa=PAUSA_RICERCA)
        self.pausa_testi = PausaUtente(pausa=PAUSA_TESTI)
        self.karaoke: dict[int, asyncio.Task] = {}  # un solo karaoke per server

    async def cog_unload(self) -> None:
        for compito in list(self.karaoke.values()):
            compito.cancel()
        self.karaoke.clear()

    def _musica(self):
        return self.bot.get_cog("MusicCog")

    async def _brano_della_coda(self, interaction: discord.Interaction, posizione: int):
        """(musica, player, indice, traccia, privilegiato) se la posizione esiste e il brano si può toccare; se no None."""
        musica = self._musica()
        if musica is None:
            return None
        player = await musica._giocatore_attivo(interaction)
        if player is None:
            return None
        lunghezza = len(player.queue)
        if not 1 <= posizione <= lunghezza:
            await interaction.response.send_message(
                await testo_per(interaction, "music_coda_posizione_non_valida", lunghezza=lunghezza), ephemeral=True
            )
            return None
        traccia = player.queue[posizione - 1]
        privilegiato = await musica.privilegi(interaction)
        if not puo_toccare_brano(privilegiato, requester_of(traccia), interaction.user.id):
            await interaction.response.send_message(await testo_per(interaction, "music_coda_solo_tuoi"), ephemeral=True)
            return None
        return musica, player, posizione - 1, traccia, privilegiato

    async def _dire(self, interaction: discord.Interaction, chiave: str, **valori) -> None:
        await interaction.response.send_message(
            await testo_per(interaction, chiave, pubblica=True, **valori), allowed_mentions=NESSUNA_MENZIONE
        )

    # ------------------------------ coda ------------------------------
    @comando_di_gruppo("music", nome="togli", descrizione="Toglie un brano dalla coda.", sottogruppo=SG_CODA)
    @app_commands.describe(posizione="Posizione del brano in coda (da 1)")
    async def coda_togli(self, interaction: discord.Interaction, posizione: app_commands.Range[int, 1, 10000]) -> None:
        # MUS-024: i propri brani; DJ e staff anche quelli degli altri
        trovato = await self._brano_della_coda(interaction, posizione)
        if trovato is None:
            return
        musica, player, indice, traccia, _ = trovato
        musica._togli_dalla_coda(player, [indice])
        await self._dire(interaction, "music_coda_tolto", titolo=truncate_title(traccia.title, 150), posizione=posizione)

    @comando_di_gruppo(
        "music", nome="ultimo", descrizione="Toglie l'ultimo brano che hai messo in coda.", sottogruppo=SG_CODA
    )
    async def coda_ultimo(self, interaction: discord.Interaction) -> None:
        # MUS-025: «ho sbagliato brano»
        musica = self._musica()
        player = await musica._giocatore_attivo(interaction) if musica else None
        if player is None:
            return
        miei = [i for i, tr in enumerate(player.queue) if requester_of(tr) == interaction.user.id]
        if not miei:
            await interaction.response.send_message(await testo_per(interaction, "music_coda_nessun_tuo"), ephemeral=True)
            return
        traccia = player.queue[miei[-1]]
        musica._togli_dalla_coda(player, [miei[-1]])
        await self._dire(interaction, "music_coda_tolto", titolo=truncate_title(traccia.title, 150), posizione=miei[-1] + 1)

    @comando_di_gruppo("music", nome="miei", descrizione="Toglie dalla coda tutti i tuoi brani.", sottogruppo=SG_CODA)
    async def coda_miei(self, interaction: discord.Interaction) -> None:
        # MUS-026: anche i tuoi già suonati che il loop della coda riporterebbe
        musica = self._musica()
        player = await musica._giocatore_attivo(interaction) if musica else None
        if player is None:
            return
        utente = interaction.user.id
        miei = [i for i, tr in enumerate(player.queue) if requester_of(tr) == utente]
        tolti = musica._togli_dalla_coda(player, miei, lambda chi: chi == utente)
        if not tolti:
            await interaction.response.send_message(await testo_per(interaction, "music_coda_nessun_tuo"), ephemeral=True)
            return
        await self._dire(interaction, "player_coda_tolti", quanti=tolti)

    @comando_di_gruppo("music", nome="sposta", descrizione="Sposta un brano della coda in un'altra posizione.", sottogruppo=SG_CODA)
    @app_commands.describe(da="Posizione attuale del brano (da 1)", a="Nuova posizione (da 1)")
    async def coda_sposta(
        self,
        interaction: discord.Interaction,
        da: app_commands.Range[int, 1, 10000],
        a: app_commands.Range[int, 1, 10000],
    ) -> None:
        # MUS-028
        trovato = await self._brano_della_coda(interaction, da)
        if trovato is None:
            return
        _musica, player, indice, traccia, _ = trovato
        nuova = min(a, len(player.queue))
        riordina_coda(player, sposta_elemento(list(player.queue), indice, nuova - 1))
        await self._dire(interaction, "music_coda_spostato", titolo=truncate_title(traccia.title, 150), posizione=nuova)

    @comando_di_gruppo(
        "music", nome="cima", descrizione="Porta un brano della coda in cima, subito dopo quello in corso.", sottogruppo=SG_CODA
    )
    @app_commands.describe(posizione="Posizione del brano in coda (da 1)")
    async def coda_cima(self, interaction: discord.Interaction, posizione: app_commands.Range[int, 1, 10000]) -> None:
        # MUS-022: è uno spostamento in prima posizione
        trovato = await self._brano_della_coda(interaction, posizione)
        if trovato is None:
            return
        _musica, player, indice, traccia, _ = trovato
        riordina_coda(player, sposta_elemento(list(player.queue), indice, 0))
        await self._dire(interaction, "music_coda_in_cima", titolo=truncate_title(traccia.title, 150))

    @comando_di_gruppo(
        "music", nome="subito", descrizione="Fa partire subito un brano della coda, saltando quello in corso.",
        sottogruppo=SG_CODA,
    )
    @app_commands.describe(posizione="Posizione del brano in coda (da 1)")
    async def coda_subito(self, interaction: discord.Interaction, posizione: app_commands.Range[int, 1, 10000]) -> None:
        # MUS-023: interrompe il brano di tutti, quindi serve il privilegio (DJ, staff, da soli nel canale)
        musica = self._musica()
        if musica is None or not await musica.controlli_base(interaction):
            return
        if not await musica.privilegi(interaction):
            await interaction.response.send_message(await testo_per(interaction, "music_coda_subito_solo_dj"), ephemeral=True)
            return
        trovato = await self._brano_della_coda(interaction, posizione)
        if trovato is None:
            return
        _musica, player, indice, traccia, _ = trovato
        await interaction.response.defer()  # Lavalink può metterci più di 3 secondi
        riordina_coda(player, sposta_elemento(list(player.queue), indice, 0))
        if getattr(player, "playing", False):
            await player.skip()
        else:
            prossima = await player.queue.get_wait()
            await player.play(prossima)
        await interaction.followup.send(
            await testo_per(interaction, "music_coda_subito", pubblica=True, titolo=truncate_title(traccia.title, 150)),
            allowed_mentions=NESSUNA_MENZIONE,
        )

    # ------------------------------ brano ------------------------------
    async def _player_che_suona(self, interaction: discord.Interaction):
        """Il player con un brano in corso (modalità DJ compresa), o None con la risposta già partita."""
        musica = self._musica()
        player = await musica._giocatore_attivo(interaction, dj=True) if musica else None
        if player is None:
            return None
        if getattr(player, "current", None) is None:
            await interaction.response.send_message(
                await testo_per(interaction, "player_non_nessuna_traccia_in_riproduzione"), ephemeral=True
            )
            return None
        if not getattr(player.current, "is_seekable", True):
            await interaction.response.send_message(await testo_per(interaction, "music_brano_non_cercabile"), ephemeral=True)
            return None
        return player

    @comando_di_gruppo("music", nome="ricomincia", descrizione="Rifà partire da capo il brano in corso.", sottogruppo=SG_BRANO)
    async def brano_ricomincia(self, interaction: discord.Interaction) -> None:
        # MUS-033
        player = await self._player_che_suona(interaction)
        if player is None:
            return
        await interaction.response.defer()
        await player.seek(0)
        await interaction.followup.send(await testo_per(interaction, "music_brano_ricominciato", pubblica=True))

    @comando_di_gruppo(
        "music", nome="vai-a", descrizione="Va a un punto del brano: 1:30, +0:30 avanti, -0:15 indietro.", sottogruppo=SG_BRANO
    )
    @app_commands.describe(punto="Minuti e secondi (1:30), oppure con + o - per muoversi dal punto attuale")
    async def brano_vai_a(self, interaction: discord.Interaction, punto: app_commands.Range[str, 1, 12]) -> None:
        # MUS-034
        player = await self._player_che_suona(interaction)
        if player is None:
            return
        ms = parse_posizione(punto, int(getattr(player, "position", 0) or 0), int(player.current.length or 0))
        if ms is None:
            await interaction.response.send_message(await testo_per(interaction, "music_brano_punto_non_valido"), ephemeral=True)
            return
        await interaction.response.defer()
        await player.seek(ms)
        await interaction.followup.send(
            await testo_per(interaction, "music_brano_vai_a", pubblica=True, punto=format_duration(ms))
        )

    @comando_di_gruppo("music", nome="cerca", descrizione="Cerca un brano e scegli tra 10 risultati.", sottogruppo=SG_BRANO)
    @app_commands.describe(testo="Titolo o artista da cercare")
    async def brano_cerca(self, interaction: discord.Interaction, testo: app_commands.Range[str, 2, 100]) -> None:
        # MUS-013: il menu è tuo e scade dopo 60 secondi; i link si usano con /music play
        musica = self._musica()
        if musica is None or not await musica.controlli_base(interaction):
            return
        if classify_query(testo) != QUERY_TESTO:
            await interaction.response.send_message(await testo_per(interaction, "music_cerca_solo_titoli"), ephemeral=True)
            return
        guild_id, utente_id = interaction.guild.id, interaction.user.id
        resta = self.pausa_ricerche.resta(guild_id, utente_id)
        if resta > 0:
            await interaction.response.send_message(
                await testo_per(interaction, "music_cerca_riprova", secondi=int(resta) + 1), ephemeral=True
            )
            return
        self.pausa_ricerche.segna(guild_id, utente_id)  # prima del primo await lento
        await interaction.response.defer(ephemeral=True)
        lingua = await lingua_interazione(interaction)
        gestore = getattr(self.bot, "music_nodes", None)
        nodo = gestore.node_for(MAIN_KEY) if gestore else None
        if nodo is None:
            await interaction.followup.send(t("music_nessun_nodo", lingua), ephemeral=True)
            return
        impostazioni = await load_music_settings(db, guild_id)
        try:
            trovati = await musica._cerca_su(testo, nodo, impostazioni.default_search or None)
        except wavelink.exceptions.WavelinkException:
            logger.warning("Ricerca con scelta fallita sul nodo %s.", nodo.identifier, exc_info=True)
            trovati = None
        tracce = [] if not trovati or isinstance(trovati, wavelink.Playlist) else list(trovati)
        risultati = risultati_da_tracce(
            tracce, lambda tr: not title_blocked(tr.title, impostazioni) and not track_too_long(tr.length, impostazioni)
        )
        if not risultati:
            await interaction.followup.send(t("music_nessun_risultato", lingua), ephemeral=True)
            return

        async def avvia(inter: discord.Interaction, scelto: Risultato) -> None:
            if not await musica.controlli_base(inter):
                return
            await inter.response.defer(ephemeral=True)
            await musica.accoda(inter.guild, inter.user, scelto.link, inter.followup.send, interaction=inter)

        vista = CercaView(utente_id, risultati, lingua, avvia)
        vista.messaggio = await interaction.followup.send(
            t("music_cerca_intestazione", lingua, testo=truncate_title(testo, 100)),
            view=vista, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE, wait=True,
        )

    # ------------------------------ testi e karaoke ------------------------------
    async def _testi_del_brano(self, interaction: discord.Interaction, player):
        """I testi del brano in corso, o None con la risposta già partita (dopo un `defer`)."""
        corrente = player.current
        try:
            testi = await cerca_testi(corrente.title, getattr(corrente, "author", "") or "", int(corrente.length or 0))
        except ServizioNonRisponde:
            await interaction.followup.send(await testo_per(interaction, "music_testo_servizio_giu"), ephemeral=True)
            return None
        if testi is None:
            await interaction.followup.send(await testo_per(interaction, "music_testo_non_trovato"), ephemeral=True)
            return None
        return testi

    async def _player_per_testi(self, interaction: discord.Interaction):
        musica = self._musica()
        player = await musica._giocatore_attivo(interaction) if musica else None
        if player is None:
            return None
        if getattr(player, "current", None) is None:
            await interaction.response.send_message(
                await testo_per(interaction, "player_non_nessuna_traccia_in_riproduzione"), ephemeral=True
            )
            return None
        if str(getattr(player.current, "source", "") or "").lower() == "local":  # MUS-018: niente titoli ai servizi esterni
            await interaction.response.send_message(await testo_per(interaction, "music_testo_anteprima"), ephemeral=True)
            return None
        guild_id, utente_id = interaction.guild.id, interaction.user.id
        resta = self.pausa_testi.resta(guild_id, utente_id)
        if resta > 0:
            await interaction.response.send_message(
                await testo_per(interaction, "music_cerca_riprova", secondi=int(resta) + 1), ephemeral=True
            )
            return None
        self.pausa_testi.segna(guild_id, utente_id)  # prima del primo await lento
        return player

    @comando_di_gruppo("music", nome="testo", descrizione="Mostra il testo del brano in corso.", sottogruppo=SG_BRANO)
    async def brano_testo(self, interaction: discord.Interaction) -> None:
        # MUS-046: testi da LRCLIB; li vede solo chi li chiede, troncati
        player = await self._player_per_testi(interaction)
        if player is None:
            return
        await interaction.response.defer(ephemeral=True)
        testi = await self._testi_del_brano(interaction, player)
        if testi is None:
            return
        grezzo = testi.semplice.strip() or "\n".join(r[1] for r in leggi_lrc(testi.sincronizzato) if r[1])
        embed = discord.Embed(
            title=truncate_title(f"{testi.titolo} - {testi.artista}".strip(" -"), 250) or None,
            description=tronca_testo(grezzo),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="LRCLIB")
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=NESSUNA_MENZIONE)

    @comando_di_gruppo(
        "music", nome="karaoke", descrizione="Mostra le righe del brano mentre suona, a tempo.", sottogruppo=SG_BRANO
    )
    async def brano_karaoke(self, interaction: discord.Interaction) -> None:
        # MUS-046: un messaggio aggiornato (al massimo ogni 2,5 secondi) finché dura il brano
        guild_id = interaction.guild.id if interaction.guild else 0
        attivo = self.karaoke.get(guild_id)
        if attivo is not None and not attivo.done():
            await interaction.response.send_message(await testo_per(interaction, "music_karaoke_gia_attivo"), ephemeral=True)
            return
        player = await self._player_per_testi(interaction)
        if player is None:
            return
        await interaction.response.defer()
        testi = await self._testi_del_brano(interaction, player)
        if testi is None:
            return
        righe = leggi_lrc(testi.sincronizzato)
        if not righe:
            chiave = "music_karaoke_solo_semplice" if testi.semplice.strip() else "music_testo_non_trovato"
            await interaction.followup.send(await testo_per(interaction, chiave), ephemeral=True)
            return
        if self.karaoke.get(guild_id) is not None and not self.karaoke[guild_id].done():  # due richieste insieme
            await interaction.followup.send(await testo_per(interaction, "music_karaoke_gia_attivo"), ephemeral=True)
            return
        intestazione = await testo_per(
            interaction, "music_karaoke_titolo", pubblica=True, titolo=truncate_title(player.current.title, 150)
        )
        messaggio = await interaction.followup.send(
            f"{intestazione}\n♪", allowed_mentions=NESSUNA_MENZIONE, wait=True
        )
        fine = await testo_per(interaction, "music_karaoke_finito", pubblica=True)
        compito = asyncio.create_task(self._segui(guild_id, player, player.current, righe, messaggio, intestazione, fine))
        self.karaoke[guild_id] = compito

    async def _segui(self, guild_id, player, brano, righe, messaggio, intestazione: str, fine: str) -> None:
        """Aggiorna il messaggio quando cambia la riga. Si ferma con il brano, con stop o dopo il tetto di durata."""
        partito = time.monotonic()
        ultimo = None
        try:
            while time.monotonic() - partito < KARAOKE_DURATA_MAX:
                await asyncio.sleep(KARAOKE_INTERVALLO)
                if getattr(player, "current", None) is not brano or not getattr(player, "connected", True):
                    break
                indice = indice_riga(righe, int(getattr(player, "position", 0) or 0))
                if indice == ultimo:
                    continue
                ultimo = indice
                await messaggio.edit(
                    content=f"{intestazione}\n{testo_karaoke(righe, indice)}"[:1900], allowed_mentions=NESSUNA_MENZIONE
                )
        except asyncio.CancelledError:
            raise
        except discord.HTTPException:
            logger.info("Karaoke fermato: il messaggio non si può più modificare.")
        finally:
            if self.karaoke.get(guild_id) is asyncio.current_task():
                self.karaoke.pop(guild_id, None)
            try:
                await messaggio.edit(content=f"{intestazione}\n{fine}", allowed_mentions=NESSUNA_MENZIONE)
            except (discord.HTTPException, RuntimeError):
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicControlloCog(bot))
