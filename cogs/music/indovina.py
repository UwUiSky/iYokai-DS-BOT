"""
cogs/music/indovina.py
======================
`/giochi indovina-canzone`: gioco «indovina la canzone» (MUS-019). Il bot musicale suona un estratto breve di un brano
della playlist dell'owner (i file locali sono esclusi) e chi scrive per primo il titolo nel canale prende un punto.
Una partita per server alla volta, da 1 a 10 giri, nessun punteggio salvato.
Funzioni coperte: SPEC §9 (catalogo MUS-019)
Dipende da: cogs/music/player.py (MusicCog.accoda), core/music_indovina_logic.py, core/repositories/main_radio_repo.py
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field

import discord
from discord import app_commands
from discord.ext import commands

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.i18n import lingua_risposta, t, testo_per
from core.music_indovina_logic import (
    ESTRATTO_SECONDI,
    MAX_PARTITE_INSIEME,
    MAX_ROUND,
    PAUSA_TRA_PARTITE_SECONDI,
    PAUSA_TRA_ROUND_SECONDI,
    ROUND_PREDEFINITO,
    TEMPO_ROUND_SECONDI,
    Partita,
    in_gioco,  # noqa: F401  (usato anche dai test del cog)
    inizio_estratto_ms,
    numero_di_round,
    partite_in_corso,
    segna_in_gioco,
    togli_in_gioco,
)
from core.music_logic import local_path_from_identifier, truncate_title
from core.repositories.main_radio_repo import main_radio_repo

logger = logging.getLogger("iyokai.music.indovina")

_NESSUNA_MENZIONE = discord.AllowedMentions.none()


@dataclass
class _Contesto:
    partita: Partita
    canale_testo: discord.abc.Messageable
    evento: asyncio.Event = field(default_factory=asyncio.Event)
    vincitore: int | None = None
    task: asyncio.Task | None = None


def _titolo_da_mostrare(label: str) -> str:
    return discord.utils.escape_markdown(truncate_title(label, 150))


class MusicIndovinaCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._partite: dict[int, _Contesto] = {}
        self._ultima_fine: dict[int, float] = {}
        self._pulizie: set[asyncio.Task] = set()

    async def cog_unload(self) -> None:
        for guild_id, contesto in list(self._partite.items()):
            if contesto.task is not None:
                contesto.task.cancel()
            togli_in_gioco(guild_id)
        self._partite.clear()

    # ------------------------------------------------------------------ comando
    @comando_di_gruppo("giochi", nome="indovina-canzone", descrizione="Indovina la canzone da un breve estratto, in vocale.")
    @app_commands.describe(giri="Quanti brani (1-10)", ferma="Ferma la partita in corso")
    async def indovina(
        self, interaction: discord.Interaction, giri: app_commands.Range[int, 1, MAX_ROUND] = ROUND_PREDEFINITO,
        ferma: bool = False,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        if ferma:
            await self._ferma(interaction)
            return
        musica = self.bot.get_cog("MusicCog")
        if musica is None or not await musica.controlli_base(interaction):
            return
        rifiuto = await self._motivo_di_rifiuto(interaction, musica)
        if rifiuto is not None:
            await interaction.response.send_message(await testo_per(interaction, rifiuto[0], **rifiuto[1]), ephemeral=True)
            return
        brani = [
            b for b in await main_radio_repo.list_tracks()
            if local_path_from_identifier(b.identifier) is None and b.label.strip()
        ]
        n = numero_di_round(giri, len(brani))
        if n == 0:
            await interaction.response.send_message(await testo_per(interaction, "indovina_nessun_brano"), ephemeral=True)
            return
        if guild.id in self._partite:  # ricontrollo dopo l'await: due comandi insieme
            await interaction.response.send_message(await testo_per(interaction, "indovina_gia_in_corso"), ephemeral=True)
            return
        lingua = await lingua_risposta(guild.id, pubblica=True)
        partita = Partita(guild.id, interaction.channel_id, interaction.user.id, n)
        contesto = _Contesto(partita, interaction.channel)
        self._partite[guild.id] = contesto  # prima di ogni altro await
        segna_in_gioco(guild.id)
        contesto.task = asyncio.create_task(
            self._gioca(contesto, musica, interaction.user, random.sample(brani, n), lingua)
        )
        # La pulizia parte comunque, anche se il compito e' annullato prima di cominciare.
        canale_vocale_id = interaction.user.voice.channel.id
        contesto.task.add_done_callback(lambda _t: self._avvia_pulizia(guild.id, canale_vocale_id))
        await interaction.response.send_message(
            t("indovina_inizio", lingua, n=n, secondi=ESTRATTO_SECONDI, tempo=TEMPO_ROUND_SECONDI),
            allowed_mentions=_NESSUNA_MENZIONE,
        )

    async def _motivo_di_rifiuto(self, interaction: discord.Interaction, musica) -> tuple[str, dict] | None:
        guild = interaction.guild
        if guild.id in self._partite:
            return "indovina_gia_in_corso", {}
        resta = PAUSA_TRA_PARTITE_SECONDI - (time.monotonic() - self._ultima_fine.get(guild.id, -1e9))
        if resta > 0:
            return "indovina_attendi", {"secondi": int(resta) + 1}
        if partite_in_corso() >= MAX_PARTITE_INSIEME:
            return "indovina_troppe_partite", {}
        canale = getattr(interaction.channel, "permissions_for", None)
        if canale is None or not (canale(guild.me).send_messages and canale(guild.me).view_channel):
            return "indovina_senza_permessi", {}
        sessione = await self.bot.music_fleet.get_worker_for_channel(guild.id, interaction.user.voice.channel.id)
        if sessione is not None:
            return "indovina_musica_in_corso", {}
        return None

    async def _ferma(self, interaction: discord.Interaction) -> None:
        contesto = self._partite.get(interaction.guild.id)
        if contesto is None:
            await interaction.response.send_message(await testo_per(interaction, "indovina_nessuna_partita"), ephemeral=True)
            return
        permessi = getattr(interaction.user, "guild_permissions", None)
        if interaction.user.id != contesto.partita.host_id and not (permessi and permessi.manage_guild):
            await interaction.response.send_message(await testo_per(interaction, "indovina_solo_chi_ha_avviato"), ephemeral=True)
            return
        if contesto.task is not None:
            contesto.task.cancel()
        await interaction.response.send_message(await testo_per(interaction, "indovina_fermata", pubblica=True))

    # ------------------------------------------------------------------ risposte
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        contesto = self._partite.get(message.guild.id)
        if contesto is None or message.channel.id != contesto.partita.canale_testo_id:
            return
        if contesto.partita.prova(message.author.id, message.content):
            contesto.vincitore = message.author.id
            contesto.evento.set()

    # ------------------------------------------------------------------ partita
    async def _player_del_canale(self, guild_id: int, canale_id: int):
        sessione = await self.bot.music_fleet.get_worker_for_channel(guild_id, canale_id)
        if sessione is None:
            return None
        guild_worker = sessione[1].get_guild(guild_id)
        return getattr(guild_worker, "voice_client", None)

    async def _gioca(self, contesto: _Contesto, musica, host: discord.Member, brani: list, lingua: str) -> None:
        partita, guild_id = contesto.partita, host.guild.id
        canale_vocale_id = host.voice.channel.id if host.voice and host.voice.channel else 0
        try:
            for i, brano in enumerate(brani):
                if not await self._giro(contesto, musica, host, brano, canale_vocale_id, lingua):
                    await self._manda(contesto, t("indovina_interrotta", lingua))
                    break
                if i < len(brani) - 1:
                    await asyncio.sleep(PAUSA_TRA_ROUND_SECONDI)
            await self._manda(contesto, self._testo_finale(partita, lingua))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Partita di «indovina la canzone» interrotta da un errore.")
            await self._manda(contesto, t("indovina_interrotta", lingua))
        finally:
            partita.chiudi_round()

    async def _giro(self, contesto: _Contesto, musica, host, brano, canale_vocale_id: int, lingua: str) -> bool:
        """Un giro. False se il bot non riesce a suonare (la partita finisce)."""
        partita = contesto.partita
        await self._manda(contesto, t("indovina_giro", lingua, k=partita.round_corrente + 1, n=partita.round_totali))
        errori: list[str] = []

        async def tace(testo: str) -> None:  # i messaggi di accoda rivelerebbero il titolo
            errori.append(testo)

        async def cerca(nodo, _nodo_locale):
            return await musica._cerca_su(brano.identifier, nodo), nodo

        canale = await musica.accoda(
            host.guild, host, brano.identifier, tace, cerca=cerca, gratis=True,
        )
        if canale is None:
            return False
        player = await self._player_del_canale(host.guild.id, canale)
        if player is None or player.current is None:
            return False
        inizio = inizio_estratto_ms(getattr(player.current, "length", 0) or brano.duration_ms)
        if inizio and getattr(player.current, "is_seekable", True):
            await player.seek(inizio)
        contesto.evento.clear()
        contesto.vincitore = None
        partita.apri_round(brano.label)
        try:
            await asyncio.wait_for(contesto.evento.wait(), ESTRATTO_SECONDI)
        except asyncio.TimeoutError:
            await self._ferma_audio(player)  # l'estratto finisce, resta il tempo per rispondere
            try:
                await asyncio.wait_for(contesto.evento.wait(), TEMPO_ROUND_SECONDI - ESTRATTO_SECONDI)
            except asyncio.TimeoutError:
                pass
        partita.chiudi_round()
        await self._ferma_audio(player)
        titolo = _titolo_da_mostrare(brano.label)
        if contesto.vincitore is not None:
            await self._manda(contesto, t("indovina_giusto", lingua, utente=f"<@{contesto.vincitore}>", titolo=titolo))
        else:
            await self._manda(contesto, t("indovina_tempo_scaduto", lingua, titolo=titolo))
        return True

    @staticmethod
    async def _ferma_audio(player) -> None:
        try:
            await player.skip(force=True)
        except Exception:
            logger.debug("Estratto non fermato.", exc_info=True)

    async def _manda(self, contesto: _Contesto, testo: str) -> None:
        try:
            await contesto.canale_testo.send(testo[:2000], allowed_mentions=_NESSUNA_MENZIONE)
        except discord.HTTPException:
            logger.info("Messaggio del gioco non inviato.")

    @staticmethod
    def _testo_finale(partita: Partita, lingua: str) -> str:
        classifica = partita.classifica()
        if not classifica:
            return t("indovina_fine_nessuno", lingua)
        medaglie = ("🥇", "🥈", "🥉")
        righe = [
            f"{medaglie[i] if i < 3 else '▫️'} <@{uid}>: {punti}" for i, (uid, punti) in enumerate(classifica)
        ]
        return t("indovina_fine", lingua, classifica="\n".join(righe))

    def _avvia_pulizia(self, guild_id: int, canale_vocale_id: int) -> None:
        pulizia = asyncio.create_task(self._pulisci(guild_id, canale_vocale_id))
        self._pulizie.add(pulizia)
        pulizia.add_done_callback(self._pulizie.discard)

    async def _pulisci(self, guild_id: int, canale_vocale_id: int) -> None:
        """Fine partita (anche annullata): il bot esce dal canale e lo slot si libera."""
        self._partite.pop(guild_id, None)
        self._ultima_fine[guild_id] = time.monotonic()
        try:
            player = await self._player_del_canale(guild_id, canale_vocale_id)
            if player is not None:
                await player.disconnect()
            await self.bot.music_fleet.release_session(guild_id, canale_vocale_id)
        except Exception:
            logger.exception("Pulizia a fine partita non riuscita.")
        finally:
            togli_in_gioco(guild_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicIndovinaCog(bot))
