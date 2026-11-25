"""
cogs/fun/soundboard.py
======================
Effetti sonori in vocale: un suono della soundboard (del server o
predefinito di Discord) suonato da un bot musicale nel canale di chi lo
chiede. Se il canale ha già un bot musicale si usa quello (la musica non
si ferma); se no entra il primo libero, suona e poi esce. Pausa per utente.
Il comando sta nel gruppo music (il gruppo fun ha già 25 figli). Il suono in corso si ferma con `/music suono-ferma`
o col bottone sotto «suono partito»: chi l'ha avviato, staff e DJ, o chiunque sia nel canale se chi l'ha avviato non c'è
più. Un admin può limitare ogni suono a certi ruoli o vietarlo ad altri con `/admin-musica suono-ruoli` (massimo 20 ruoli per suono).
Funzioni coperte: SPEC §23 (NF-35, FUN-076, FUN-078)
Dipende da: cogs/music/player.py (worker, nodo, ingresso nel canale),
core/music_sound_logic.py, core/suoni_ruoli_logic.py.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.command_access import Livello, autocomplete_protetto, richiedi
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.i18n import testo_per
from core.ui_base import BaseView
from core.music_settings_logic import channel_not_allowed, load_music_settings
from core.music_sound_logic import ATTESA_USCITA, PausaUtente, Suono, SuoniInCorso, puo_fermare_suono, scelte, trova
from core.repositories.suoni_ruoli_repo import suoni_ruoli_repo
from core.suoni_ruoli_logic import MAX_RUOLI_PER_SUONO, MODI, RUOLO_BLOCCO, puo_suonare

logger = logging.getLogger("iyokai.music.suoni")

MSG_NESSUN_NODO = "Nessun nodo audio è collegato per il music bot libero. Riprova tra poco."
RIPRISTINA_SORDO_DOPO = 6.0  # secondi


class FermaSuonoView(BaseView):
    """Il bottone sotto «suono partito»: vale quanto dura il suono. Chi preme si controlla di nuovo ogni volta."""

    def __init__(self, cog: "SoundboardCog", canale_id: int) -> None:
        super().__init__(timeout=ATTESA_USCITA)
        self.cog = cog
        self.canale_id = canale_id

    @discord.ui.button(label="Ferma il suono", style=discord.ButtonStyle.secondary, emoji="⏹️")
    async def ferma(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        chiave = await self.cog.ferma_suono(interaction, self.canale_id)
        await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)


class SoundboardCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.pausa = PausaUtente()
        self._predefiniti: list = []
        self._task: set[asyncio.Task] = set()
        # Uscita programmata del bot entrato solo per i suoni, per (server, canale).
        self._uscite: dict[tuple[int, int], asyncio.Task] = {}
        # Ritorno "sordo" programmato del bot musicale, per (server, canale).
        self._sordi: dict[tuple[int, int], asyncio.Task] = {}
        # Il suono appena partito per (server, canale): chi l'ha avviato e se il bot è entrato solo per quello.
        self._in_corso = SuoniInCorso()
        # Il bot che l'ha suonato, per fermarlo uscendo dal canale.
        self._worker_suono: dict[tuple[int, int], tuple] = {}

    async def cog_unload(self) -> None:
        await super().cog_unload()
        for task in list(self._task):
            task.cancel()

    def _in_background(self, coroutine) -> asyncio.Task:
        task = asyncio.create_task(coroutine)
        self._task.add(task)
        task.add_done_callback(self._task.discard)
        return task

    def _programma_uscita(self, musica, flotta, worker_guild, guild_id: int, canale_id: int) -> None:
        """
        Un suono nuovo nel canale del bot temporaneo sposta in avanti la sua
        uscita: quella vecchia non lo taglia a metà.
        """
        chiave = (guild_id, canale_id)
        vecchia = self._uscite.pop(chiave, None)
        if vecchia is not None:
            vecchia.cancel()
        task = self._in_background(
            _esci_se_inattivo(
                flotta, worker_guild, guild_id, canale_id, lock=musica.blocco_canale(guild_id, canale_id)
            )
        )
        self._uscite[chiave] = task

        def _togli(t: asyncio.Task) -> None:
            if self._uscite.get(chiave) is t:
                self._uscite.pop(chiave, None)

        task.add_done_callback(_togli)

    def _programma_sordo(self, worker_guild, chiave: tuple[int, int]) -> None:
        """
        Un solo ritorno "sordo" per bot: un suono nuovo lo sposta in avanti,
        così quello del suono di prima non riassorda il bot a metà del secondo.
        """
        task = self._in_background(_torna_sordo(worker_guild, RIPRISTINA_SORDO_DOPO))
        self._sordi[chiave] = task

        def _togli(t: asyncio.Task) -> None:
            if self._sordi.get(chiave) is t:
                self._sordi.pop(chiave, None)

        task.add_done_callback(_togli)

    async def _suoni(self, guild: discord.Guild) -> dict[str, tuple[Suono, object]]:
        """Valore -> (Suono, oggetto discord.py). I predefiniti si leggono una volta sola."""
        if not self._predefiniti:
            try:
                self._predefiniti = list(await self.bot.fetch_soundboard_default_sounds())
            except discord.HTTPException:
                logger.warning("Suoni predefiniti di Discord non letti.")
        tutti: dict[str, tuple[Suono, object]] = {}
        for s in getattr(guild, "soundboard_sounds", []) or []:
            if getattr(s, "available", True):
                suono = Suono(s.id, s.name, True, str(s.emoji) if s.emoji else None)
                tutti[suono.valore] = (suono, s)
        for s in self._predefiniti:
            suono = Suono(s.id, s.name, False, str(s.emoji) if getattr(s, "emoji", None) else None)
            tutti[suono.valore] = (suono, s)
        return tutti

    async def _nomi(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []
        suoni = [s for s, _ in (await self._suoni(interaction.guild)).values()]
        return [app_commands.Choice(name=e, value=v) for e, v in scelte(suoni, current)]

    @comando_di_gruppo("music", nome="suono", descrizione="Fa partire un effetto sonoro nel tuo canale vocale.")
    @app_commands.describe(nome="Il suono: della soundboard del server o di Discord")
    @app_commands.autocomplete(nome=_nomi)
    async def suono(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, 100]) -> None:
        musica = self.bot.get_cog("MusicCog")
        if musica is None:
            await interaction.response.send_message(await testo_per(interaction, "soundboard_la_musica_non_disponibile_ora"), ephemeral=True)
            return
        if not await musica.controlli_base(interaction):
            return
        guild = interaction.guild
        resta = self.pausa.resta(guild.id, interaction.user.id)
        if resta > 0:
            await interaction.response.send_message(
                await testo_per(interaction, "soundboard_aspetta_ancora_secondi_prima_del", v1=int(resta) + 1), ephemeral=True
            )
            return
        canale_id = interaction.user.voice.channel.id
        rifiuto = channel_not_allowed(canale_id, await load_music_settings(db, guild.id))
        if rifiuto:
            await interaction.response.send_message(rifiuto, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        disponibili = await self._suoni(guild)
        trovato = trova([s for s, _ in disponibili.values()], nome)
        if trovato is None:
            await interaction.followup.send(await testo_per(interaction, "soundboard_suono_non_trovato_sceglilo_dall"), ephemeral=True)
            return
        regole = await suoni_ruoli_repo.regole(guild.id, trovato.valore)
        utente = interaction.user
        ruoli = {r.id for r in getattr(utente, "roles", ())}
        admin = bool(getattr(getattr(utente, "guild_permissions", None), "administrator", False))
        if not puo_suonare(regole, ruoli, admin):
            await interaction.followup.send(await testo_per(interaction, "soundboard_ruolo_non_ammesso"), ephemeral=True)
            return
        oggetto = disponibili[trovato.valore][1]
        self.pausa.segna(guild.id, interaction.user.id)
        testo = await self.suona(musica, interaction, canale_id, oggetto)
        vista = FermaSuonoView(self, canale_id) if self._in_corso.attivo(guild.id, canale_id) else None
        if vista is not None:
            await interaction.followup.send(testo.replace("{nome}", trovato.nome), view=vista, ephemeral=True)
        else:
            await interaction.followup.send(testo.replace("{nome}", trovato.nome), ephemeral=True)

    @comando_di_gruppo("music", nome="suono-ferma", descrizione="Ferma il suono appena partito nel tuo canale vocale.")
    async def suono_ferma(self, interaction: discord.Interaction) -> None:
        musica = self.bot.get_cog("MusicCog")
        if musica is None:
            await interaction.response.send_message(await testo_per(interaction, "soundboard_la_musica_non_disponibile_ora"), ephemeral=True)
            return
        if not await musica.controlli_base(interaction):
            return
        chiave = await self.ferma_suono(interaction, interaction.user.voice.channel.id)
        await interaction.response.send_message(await testo_per(interaction, chiave), ephemeral=True)

    async def ferma_suono(self, interaction: discord.Interaction, canale_id: int) -> str:
        """
        FUN-078: ferma il suono in corso nel canale. Restituisce la chiave del messaggio. Discord non ha un comando per
        interrompere un suono della soundboard: se il bot è entrato solo per il suono esce dal canale (e il suono si
        interrompe con lui); se sta suonando musica non si tocca, e si dice chiaro.
        """
        guild = interaction.guild
        musica = self.bot.get_cog("MusicCog")
        suono = self._in_corso.attivo(guild.id, canale_id)
        if suono is None or musica is None:
            return "suono_nessuno_in_corso"
        utente = interaction.user
        canale_utente = getattr(getattr(utente, "voice", None), "channel", None)
        canale_suono = guild.get_channel(canale_id)
        umani = musica.ascoltatori_umani(canale_suono) if canale_suono is not None else []
        if canale_utente is not None and canale_utente.id != canale_id:
            return "suono_altro_canale"  # chi sta in un altro canale non ferma questo (nemmeno lo staff)
        privilegiato = await musica.privilegi(interaction)
        if not puo_fermare_suono(privilegiato, suono.avviato_da, utente.id, umani):
            return "suono_non_tuo"
        if not suono.da_solo:
            return "suono_con_musica"  # il bot sta suonando musica: uscire la fermerebbe
        worker_guild = self._worker_suono.get((guild.id, canale_id))
        player = worker_guild.voice_client if worker_guild is not None else None
        if player is None:
            self._in_corso.togli(guild.id, canale_id)
            return "suono_nessuno_in_corso"
        async with musica.blocco_canale(guild.id, canale_id):
            if getattr(player, "playing", False) or not getattr(player.queue, "is_empty", True):
                return "suono_con_musica"  # nel frattempo è partita della musica
            uscita = self._uscite.pop((guild.id, canale_id), None)
            if uscita is not None:
                uscita.cancel()
            try:
                await player.disconnect()
            finally:
                await self.bot.music_fleet.release_session(guild.id, canale_id)
        self._in_corso.togli(guild.id, canale_id)
        return "suono_fermato"

    @autocomplete_protetto(Livello.ADMIN)
    async def _nomi_admin(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return await self._nomi(interaction, current)

    @comando_di_gruppo("admin-musica", nome="suono-ruoli", descrizione="Chi può usare un suono: ruoli consentiti o vietati.")
    @app_commands.describe(
        suono="Il suono", modo="Cosa fare", ruolo="Il ruolo (non serve per «Mostra»)",
    )
    @app_commands.autocomplete(suono=_nomi_admin)
    @app_commands.choices(
        modo=[
            app_commands.Choice(name="Consenti a questo ruolo", value="consenti"),
            app_commands.Choice(name="Vieta a questo ruolo", value="vieta"),
            app_commands.Choice(name="Togli il ruolo dall'elenco", value="togli"),
            app_commands.Choice(name="Mostra l'elenco", value="mostra"),
        ]
    )
    @richiedi(Livello.ADMIN)
    async def suono_ruoli(
        self, interaction: discord.Interaction, suono: app_commands.Range[str, 1, 100],
        modo: app_commands.Choice[str], ruolo: discord.Role | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(await testo_per(interaction, "guild_only_command"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        trovato = trova([s for s, _ in (await self._suoni(guild)).values()], suono)
        if trovato is None:
            await interaction.followup.send(await testo_per(interaction, "soundboard_suono_non_trovato_sceglilo_dall"), ephemeral=True)
            return
        scelta = modo.value
        if scelta != "mostra" and ruolo is None:
            await interaction.followup.send(await testo_per(interaction, "soundboard_serve_un_ruolo"), ephemeral=True)
            return
        if scelta in MODI and ruolo.is_default():
            await interaction.followup.send(await testo_per(interaction, "soundboard_non_everyone"), ephemeral=True)
            return
        nessuna_menzione = discord.AllowedMentions.none()
        if scelta in MODI:
            if await suoni_ruoli_repo.imposta(guild.id, trovato.valore, ruolo.id, scelta) == "tetto":
                await interaction.followup.send(await testo_per(interaction, "soundboard_ruoli_tetto", massimo=MAX_RUOLI_PER_SUONO), ephemeral=True)
                return
            chiave = "soundboard_ruolo_consentito" if scelta == "consenti" else "soundboard_ruolo_vietato"
            testo = await testo_per(interaction, chiave, suono=trovato.nome, ruolo=ruolo.mention)
        elif scelta == "togli":
            tolto = await suoni_ruoli_repo.togli(guild.id, trovato.valore, ruolo.id)
            chiave = "soundboard_ruolo_tolto" if tolto else "soundboard_ruolo_non_in_elenco"
            testo = await testo_per(interaction, chiave, suono=trovato.nome, ruolo=ruolo.mention)
        else:
            regole = await suoni_ruoli_repo.regole(guild.id, trovato.valore)
            bloccato = any(r == RUOLO_BLOCCO for r, _ in regole)
            regole = [(r, m) for r, m in regole if r != RUOLO_BLOCCO]
            if not regole and not bloccato:
                testo = await testo_per(interaction, "soundboard_ruoli_vuoto", suono=trovato.nome)
            elif not regole:
                testo = await testo_per(interaction, "soundboard_ruoli_bloccato", suono=trovato.nome)
            else:
                si = await testo_per(interaction, "soundboard_elenco_consentiti")
                no = await testo_per(interaction, "soundboard_elenco_vietati")
                righe = [f"{si if m == 'consenti' else no}: <@&{r}>" for r, m in regole]
                testo = await testo_per(interaction, "soundboard_ruoli_elenco", suono=trovato.nome, elenco="\n".join(righe))
                if bloccato:
                    testo += "\n" + await testo_per(interaction, "soundboard_ruoli_bloccato_nota")
        await interaction.followup.send(testo[:2000], ephemeral=True, allowed_mentions=nessuna_menzione)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """Un ruolo cancellato esce da tutte le regole dei suoni."""
        await suoni_ruoli_repo.togli_ruolo(role.guild.id, role.id)

    async def suona(self, musica, interaction: discord.Interaction, canale_id: int, oggetto) -> str:
        """Manda il suono dal bot musicale del canale (o dal primo libero). Restituisce il testo."""
        guild_id = interaction.guild.id
        flotta = self.bot.music_fleet
        worker_bot, worker_guild, errore = await musica.trova_worker(
            guild_id, auto_assign=True, interaction=interaction
        )
        if errore:
            return errore
        async with musica.blocco_canale(guild_id, canale_id):
            player = worker_guild.voice_client
            temporaneo = False
            if player is None:
                nodo = _nodo_del_bot(self.bot, worker_bot)
                canale_worker = worker_guild.get_channel(canale_id)
                if nodo is None or canale_worker is None:
                    await musica.rilascia_se_libero(worker_guild, guild_id, canale_id)
                    return MSG_NESSUN_NODO if nodo is None else "Il music bot non vede il tuo canale."
                # Un bot "sordo" non può mandare suoni: qui si entra con l'audio acceso.
                player, errore = await musica.entra_in_canale(canale_worker, nodo, sordo=False)
                if errore:
                    await musica.rilascia_se_libero(worker_guild, guild_id, canale_id)
                    return errore
                temporaneo = True
            canale = player.channel
            chiave = (guild_id, canale_id)
            # Un ritorno "sordo" ancora in attesa (suono di poco fa) si annulla
            # prima di suonare: il bot era sordo e lo ridiventerà dopo QUESTO suono.
            in_attesa = self._sordi.pop(chiave, None)
            if in_attesa is not None:
                in_attesa.cancel()
            era_sordo = bool(getattr(getattr(worker_guild.me, "voice", None), "self_deaf", False))
            riassorda = era_sordo or in_attesa is not None
            try:
                if era_sordo:
                    await worker_guild.change_voice_state(channel=canale, self_deaf=False)
                await canale.send_sound(oggetto)
                da_solo = temporaneo or (guild_id, canale_id) in self._uscite
                self._in_corso.segna(guild_id, canale_id, interaction.user.id, da_solo)
                self._worker_suono[chiave] = worker_guild
            except discord.Forbidden:
                return "Il music bot non ha il permesso di usare la soundboard in questo canale."
            except discord.HTTPException:
                logger.warning("Invio del suono non riuscito nel server %s.", guild_id)
                return "Non sono riuscito a far partire il suono. Riprova tra poco."
            finally:
                if riassorda:
                    self._programma_sordo(worker_guild, chiave)
                if temporaneo or (guild_id, canale_id) in self._uscite:
                    self._programma_uscita(musica, flotta, worker_guild, guild_id, canale_id)
        return "🔊 Suono **{nome}** partito."


def _nodo_del_bot(bot, worker_bot):
    from cogs.music.player import chiave_del_bot

    gestore = getattr(bot, "music_nodes", None)
    return gestore.node_for(chiave_del_bot(worker_bot)) if gestore else None


async def _torna_sordo(worker_guild, attesa: float) -> None:
    await asyncio.sleep(attesa)
    voce = getattr(getattr(worker_guild, "me", None), "voice", None)
    if voce is not None and voce.channel is not None:
        try:
            await worker_guild.change_voice_state(channel=voce.channel, self_deaf=True)
        except discord.HTTPException:
            pass


async def _esci_se_inattivo(flotta, worker_guild, guild_id: int, canale_id: int,
                            attesa: float = ATTESA_USCITA, lock: asyncio.Lock | None = None) -> None:
    """
    Il bot entrato solo per il suono esce, a meno che nel frattempo qualcuno
    abbia messo musica (allora resta e torna "sordo", come con /music play). Il controllo si fa con il lock del canale di
    MusicCog: un /music play a metà (ricerca in corso) non trova il player
    scollegato sotto di sé.
    """
    await asyncio.sleep(attesa)
    async with lock if lock is not None else contextlib.nullcontext():
        player = worker_guild.voice_client
        if player is None:
            return
        if getattr(player, "playing", False) or not getattr(player.queue, "is_empty", True):
            # Resta per la musica messa nel frattempo: torna "sordo" (MUS-056).
            await _torna_sordo(worker_guild, 0)
            return
        try:
            await player.disconnect()
        finally:
            await flotta.release_session(guild_id, canale_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SoundboardCog(bot))
