"""
cogs/utility/poll.py
=======================
Poll (SPEC.md §14.15 — "usare il Poll nativo di Discord", come
indicato dallo schema stesso). Nessuna logica propria da estrarre:
voto, conteggio, chiusura automatica e visualizzazione dei risultati
sono TUTTI gestiti da Discord — questo cog è solo un'interfaccia
comando sopra discord.Poll, niente storage, niente stato nostro.
Senza opzioni diventa un sì/no rapido; a richiesta apre un thread di
discussione sul sondaggio.
Il bot segue solo i sondaggi programmati (`inizia_tra`) e quelli con chiusura a N voti (`chiudi_a_voti`, conta i voti
con gli eventi dei voti e chiude con la fine del sondaggio).
Funzioni coperte: SPEC §14.15; catalogo UTL-087, UTL-095, UTL-090, UTL-092 (D69, B23).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core import sondaggi_logic
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.database import db
from core.duration_logic import parse_duration
from core.i18n import testo_per
from core.premium import PremiumModule, registry
from core.repositories.sondaggi_nativi_repo import sondaggi_nativi_repo
from core.scheduler import scheduler

logger = logging.getLogger("iyokai.poll")
AZIONE_APRI_NATIVO = "sondaggio_nativo_apri"
AZIONE_FINE_NATIVO = "sondaggio_nativo_fine"

MODULE_POLL = "poll"

# Limiti dei sondaggi di Discord: 300 caratteri per la domanda, 55 per
# ogni risposta, 10 risposte. Dichiarati sulle opzioni del comando, è
# Discord stesso a rifiutare un testo troppo lungo con un suo messaggio.
TestoDomanda = app_commands.Range[str, 1, 300]
TestoRisposta = app_commands.Range[str, 1, 55]


class PollCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "sondaggi",
        nome="crea",
        descrizione="Crea un sondaggio (fino a 10 opzioni).",
    )
    @app_commands.describe(
        question="La domanda del sondaggio (massimo 300 caratteri)",
        option1="Prima opzione (vuota con la seconda = sì/no)",
        option2="Seconda opzione (massimo 55 caratteri)",
        option3="Terza opzione (facoltativa)",
        option4="Quarta opzione (facoltativa)",
        option5="Quinta opzione (facoltativa)",
        option6="Sesta opzione (facoltativa)",
        option7="Settima opzione (facoltativa)",
        option8="Ottava opzione (facoltativa)",
        option9="Nona opzione (facoltativa)",
        option10="Decima opzione (facoltativa)",
        duration_hours="Durata in ore (default 24, massimo 768 = 32 giorni)",
        multiple="Permetti di votare più di un'opzione",
        discussione="Apri un thread per discutere il sondaggio",
        inizia_tra="Si pubblica più tardi: 30m, 12h, 7d (da 1 minuto a 30 giorni)",
        chiudi_a_voti="Si chiude da solo dopo tanti voti (massimo 100000)",
    )
    async def poll(
        self,
        interaction: discord.Interaction,
        question: TestoDomanda,
        option1: TestoRisposta | None = None,
        option2: TestoRisposta | None = None,
        option3: TestoRisposta | None = None,
        option4: TestoRisposta | None = None,
        option5: TestoRisposta | None = None,
        option6: TestoRisposta | None = None,
        option7: TestoRisposta | None = None,
        option8: TestoRisposta | None = None,
        option9: TestoRisposta | None = None,
        option10: TestoRisposta | None = None,
        duration_hours: app_commands.Range[int, 1, 768] = 24,
        multiple: bool = False,
        discussione: bool = False,
        inizia_tra: app_commands.Range[str, 2, 6] | None = None,
        chiudi_a_voti: app_commands.Range[int, 1, sondaggi_logic.MAX_VOTANTI_CHIUSURA] | None = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                await testo_per(interaction, "guild_only_command"), ephemeral=True
            )
            return

        if not await db.is_module_active_for_guild(guild.id, MODULE_POLL):
            await interaction.response.send_message(
                await testo_per(interaction, "ping_questo_modulo_non_attivo_su"),
                ephemeral=True,
            )
            return

        opzioni = [
            o
            for o in (
                option1, option2, option3, option4, option5,
                option6, option7, option8, option9, option10,
            )
            if o is not None
        ]
        if not opzioni:
            opzioni = ["Sì", "No"]
        elif len(opzioni) == 1:
            await interaction.response.send_message(
                await testo_per(interaction, "poll_servono_almeno_due_opzioni_oppure"), ephemeral=True
            )
            return

        if inizia_tra:
            await self._programma(interaction, question, opzioni, duration_hours, multiple, discussione, inizia_tra, chiudi_a_voti)
            return

        sondaggio = discord.Poll(
            question=question,
            duration=timedelta(hours=duration_hours),
            multiple=multiple,
        )
        for opzione in opzioni:
            sondaggio.add_answer(text=opzione)

        await interaction.response.send_message(poll=sondaggio)
        if chiudi_a_voti:
            await self._segui(interaction, question, opzioni, duration_hours, multiple, discussione, chiudi_a_voti)
        if discussione and not interaction.channel.permissions_for(interaction.user).create_public_threads:
            # Il thread lo apre il bot: non lo fa per chi nel canale non potrebbe aprirlo da solo.
            await interaction.followup.send(
                await testo_per(interaction, "poll_sondaggio_pubblicato_ma_niente_thread"),
                ephemeral=True,
            )
        elif discussione:
            try:
                messaggio = await interaction.original_response()
                await messaggio.create_thread(name=question[:100], auto_archive_duration=1440)
            except discord.HTTPException:
                await interaction.followup.send(
                    await testo_per(interaction, "poll_sondaggio_pubblicato_ma_non_ho"), ephemeral=True
                )

    async def _segui(self, interaction, question, opzioni, ore, multipla, discussione, chiudi_a_voti) -> None:
        """Salva il sondaggio appena pubblicato per contare i voti, e prepara la pulizia alla scadenza."""
        try:
            messaggio = await interaction.original_response()
            nid = await sondaggi_nativi_repo.crea(
                interaction.guild.id, interaction.channel.id, interaction.user.id, question, opzioni, multipla=multipla,
                durata_ore=ore, discussione=discussione, chiudi_a_voti=chiudi_a_voti, stato="aperto")
            await sondaggi_nativi_repo.imposta_messaggio(nid, messaggio.id)
            fine = datetime.now(timezone.utc) + timedelta(hours=ore, minutes=1)
            await scheduler.schedule(interaction.guild.id, interaction.user.id, AZIONE_FINE_NATIVO, fine, {"id": nid})
        except discord.HTTPException:
            logger.warning("Sondaggio nativo: chiusura a voti non attivata", exc_info=True)

    async def _programma(self, interaction, question, opzioni, ore, multipla, discussione, inizia_tra, chiudi_a_voti) -> None:
        try:
            attesa = parse_duration(inizia_tra)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        if not sondaggi_logic.inizio_valido(attesa):
            await interaction.response.send_message(await testo_per(interaction, "sb_inizio_fuori"), ephemeral=True)
            return
        canale = interaction.channel
        mio = canale.permissions_for(interaction.guild.me)
        suo = canale.permissions_for(interaction.user)
        if not (mio.view_channel and mio.send_messages and suo.send_messages):
            await interaction.response.send_message(await testo_per(interaction, "sb_canale_non_ammesso"), ephemeral=True)
            return
        inizio = datetime.now(timezone.utc) + timedelta(seconds=attesa)
        nid = await sondaggi_nativi_repo.crea(
            interaction.guild.id, canale.id, interaction.user.id, question, opzioni, multipla=multipla, durata_ore=ore,
            discussione=discussione, chiudi_a_voti=chiudi_a_voti, inizia_il=inizio)
        await scheduler.schedule(interaction.guild.id, interaction.user.id, AZIONE_APRI_NATIVO, inizio, {"id": nid})
        await interaction.response.send_message(
            await testo_per(interaction, "sb_programmato_nativo", quando=discord.utils.format_dt(inizio, "R")), ephemeral=True)

    async def cog_load(self) -> None:
        await super().cog_load()
        scheduler.register_handler(AZIONE_APRI_NATIVO, self.alla_apertura)
        scheduler.register_handler(AZIONE_FINE_NATIVO, self.alla_fine)

    async def alla_apertura(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Scheduler: pubblica il sondaggio programmato (una volta sola)."""
        r = await sondaggi_nativi_repo.apri(int(payload["id"]))
        if r is None:
            return
        canale = self.bot.get_channel(r["channel_id"])
        if canale is None:
            await sondaggi_nativi_repo.elimina(r["id"])
            return
        sondaggio = discord.Poll(question=r["domanda"], duration=timedelta(hours=r["durata_ore"]), multiple=r["multipla"])
        for opzione in r["opzioni"]:
            sondaggio.add_answer(text=opzione)
        messaggio = None
        try:
            messaggio = await canale.send(poll=sondaggio)
            if r["discussione"]:
                await messaggio.create_thread(name=r["domanda"][:100], auto_archive_duration=1440)
        except discord.HTTPException:
            logger.warning("Sondaggio nativo %s: pubblicazione o thread non riusciti", r["id"], exc_info=True)
            if messaggio is None:
                await sondaggi_nativi_repo.elimina(r["id"])
            return
        await sondaggi_nativi_repo.imposta_messaggio(r["id"], messaggio.id)
        fine = datetime.now(timezone.utc) + timedelta(hours=r["durata_ore"], minutes=1)
        await scheduler.schedule(guild_id, user_id, AZIONE_FINE_NATIVO, fine, {"id": r["id"]})

    async def alla_fine(self, guild_id: int, user_id: int, payload: dict) -> None:
        """Scheduler: il sondaggio è scaduto da solo, la riga non serve più."""
        await sondaggi_nativi_repo.elimina(int(payload["id"]))

    @commands.Cog.listener()
    async def on_raw_poll_vote_add(self, payload: discord.RawPollVoteActionEvent) -> None:
        await self._voto(payload, 1)

    @commands.Cog.listener()
    async def on_raw_poll_vote_remove(self, payload: discord.RawPollVoteActionEvent) -> None:
        await self._voto(payload, -1)

    async def _voto(self, payload: discord.RawPollVoteActionEvent, delta: int) -> None:
        try:
            esito = await sondaggi_nativi_repo.conta_voto(payload.message_id, delta)
            if esito is not None and esito[1]:
                await self._chiudi_se_votanti(esito[0], payload.channel_id, payload.message_id)
        except Exception:
            logger.exception("Sondaggio nativo: chiusura a voti fallita (messaggio %s)", payload.message_id)

    async def _chiudi_se_votanti(self, nativo_id: int, channel_id: int, message_id: int) -> None:
        """Chiude il sondaggio se i VOTANTI (non i voti) hanno raggiunto la soglia. Chiude una volta sola."""
        r = await sondaggi_nativi_repo.prendi(nativo_id)
        canale = self.bot.get_channel(channel_id)
        if r is None or r["stato"] != "aperto" or canale is None:
            return
        if r["multipla"]:
            messaggio = await canale.fetch_message(message_id)
            if await self._votanti(messaggio.poll, r["chiudi_a_voti"]) < r["chiudi_a_voti"]:
                return
        if not await sondaggi_nativi_repo.chiudi(nativo_id):
            return
        await canale.get_partial_message(message_id).end_poll()
        await sondaggi_nativi_repo.elimina(nativo_id)

    @staticmethod
    async def _votanti(sondaggio: discord.Poll | None, fino_a: int) -> int:
        """Persone diverse che hanno votato (si ferma a `fino_a`). Con più scelte una persona dà più voti."""
        if sondaggio is None:
            return 0
        persone: set[int] = set()
        for risposta in sondaggio.answers:
            if risposta.vote_count == 0:
                continue
            async for utente in risposta.voters():
                persone.add(utente.id)
                if len(persone) >= fino_a:
                    return len(persone)
        return len(persone)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Dopo un riavvio i voti arrivati a bot spento si rileggono dal sondaggio."""
        try:
            for r in await sondaggi_nativi_repo.aperti_con_soglia():
                await self._riallinea(r)
        except Exception:
            logger.exception("Sondaggi nativi: riallineamento dei voti fallito")

    async def _riallinea(self, r) -> None:
        canale = self.bot.get_channel(r["channel_id"])
        if canale is None:
            return
        try:
            messaggio = await canale.fetch_message(r["message_id"])
        except discord.NotFound:
            await sondaggi_nativi_repo.elimina(r["id"])
            return
        except discord.HTTPException:
            logger.warning("Sondaggio nativo %s: messaggio non letto", r["id"], exc_info=True)
            return
        sondaggio = messaggio.poll
        if sondaggio is None or sondaggio.is_finalised():
            await sondaggi_nativi_repo.elimina(r["id"])
            return
        # Voti letti da Discord; con più scelte la soglia si verifica sui votanti veri in _chiudi_se_votanti.
        if await sondaggi_nativi_repo.riallinea(r["id"], sondaggio.total_votes):
            try:
                await self._chiudi_se_votanti(r["id"], r["channel_id"], r["message_id"])
            except discord.HTTPException:
                logger.warning("Sondaggio nativo %s: chiusura non riuscita", r["id"], exc_info=True)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        try:
            await sondaggi_nativi_repo.elimina_del_canale(channel.guild.id, channel.id)
        except Exception:
            logger.exception("Sondaggi nativi: pulizia del canale %s fallita", channel.id)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_POLL,
            display_name="Poll",
            category="community",
            description="Sondaggi tramite il sistema Poll nativo di Discord.",
            premium_capable=False,
        )
    )
    await bot.add_cog(PollCog(bot))
