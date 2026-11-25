"""
core/giveaway_worker.py
===========================
Servizio periodico che fa partire i giveaway programmati e estrae i
vincitori di quelli scaduti, con i biglietti extra (SPEC.md §15.5, §23.6) — stesso pattern di core/feed_watcher.py e core/
monthly_winners_announcer.py: tasks.loop avviato una volta da
main.py, non un Cog.

Tick ogni 30 secondi: abbastanza reattivo perché un giveaway di
"1 minuto" (durata minima) non resti scaduto per troppo a lungo
prima dell'estrazione, senza sovraccaricare inutilmente per giveaway
che durano ore o giorni. L'annuncio va dove il giveaway è stato
lanciato: canale di testo, thread, post di un forum o chat vocale.
Funzioni coperte: SPEC §15.5, §23.6 (NF-28)
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.channel_access import PERMESSI_DI_SCRITTURA, motivo_se_il_bot_non_puo
from core.giveaway_fine import concludi
from core.giveaway_immagine import file_annuncio
from core.giveaway_logic import embed_annuncio, pick_winners_pesati
from core.i18n import lingua_risposta
from core.repositories.giveaway_repo import giveaway_repo
from core.ui_base import BaseView
from core.giro_periodico import giro_periodico

logger = logging.getLogger("iyokai.giveaway_worker")

TICK_SECONDS = 30
MAX_TENTATIVI_FINE = 20  # circa 10 minuti di tentativi (un giro ogni 30 secondi), poi «fallito»


async def _canale_del_giveaway(
    guild: discord.Guild | None, channel_id: int, *, solleva_se_discord_non_risponde: bool = False
) -> discord.abc.Messageable | None:
    """
    Il posto dove è stato lanciato il giveaway: un canale di testo, un
    thread, il post di un forum o la chat di un canale vocale. Un thread
    archiviato non è in memoria, quindi si chiede a Discord. None se il
    canale non esiste più o non è un posto dove si può scrivere.
    """
    if guild is None:
        return None
    canale = guild.get_channel_or_thread(channel_id)
    if canale is None:
        try:
            canale = await guild.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden):
            return None  # il canale non c'è più o non si vede: inutile riprovare
        except discord.HTTPException:
            # Discord giù o limite di richieste: il worker lascia salire l'errore e riprova al giro dopo.
            if solleva_se_discord_non_risponde:
                raise
            return None
    return canale if isinstance(canale, discord.abc.Messageable) else None


def _vista_riepilogo(giveaway_id: int) -> BaseView:
    """La vista del messaggio finale: solo il bottone «Riepilogo» (dinamico, vale anche dopo un riavvio)."""
    from cogs.utility.giveaway_extra import BottoneRiepilogo  # qui dentro: il cog importa questo modulo

    vista = BaseView(timeout=None)
    vista.add_item(BottoneRiepilogo(giveaway_id))
    return vista


class GiveawayWorker:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, bot: commands.Bot, now: datetime | None = None) -> None:
        """
        Un giro: fa partire i programmati, prende in carico i scaduti e porta avanti la fine di ognuno.
        La fine è a stati (estrazione, annuncio, fatto): un errore non perde il premio, il giro dopo
        riprende da dove era. Ogni giveaway ha il suo try: uno rotto non ferma gli altri.
        """
        adesso = now or datetime.now(timezone.utc)

        for programmato in await giveaway_repo.get_giveaways_to_start(adesso):
            try:
                await self._avvia(bot, programmato.id, adesso)
            except Exception:
                logger.exception("Giveaway %s non partito", programmato.id)

        for scaduto in await giveaway_repo.get_due_giveaways(adesso):
            try:
                await giveaway_repo.avvia_chiusura(scaduto.id)
            except Exception:
                logger.exception("Giveaway %s: chiusura non avviata", scaduto.id)

        for giveaway, _fase in await giveaway_repo.in_chiusura():
            try:
                async with giveaway_repo.prendi_fine(giveaway.id) as fase:
                    if fase is None:
                        continue  # un altro giro lo sta facendo, o è già finito: un solo annuncio
                    await self._chiudi(bot, giveaway, fase)
            except Exception as errore:
                await self._tentativo_fallito(bot, giveaway, errore)

    async def _chiudi(self, bot: commands.Bot, giveaway, fase: str) -> None:
        """Porta avanti la fine: estrazione (se serve), annuncio, poi «fatto». Regge una seconda esecuzione."""
        if fase == "estrazione":
            partecipanti = await giveaway_repo.get_weighted_entries(giveaway.id)
            vincitori = pick_winners_pesati(partecipanti, giveaway.winners_count, random.Random())
            # I vincitori e il passaggio all'annuncio in una transazione: mai estratti due volte.
            await giveaway_repo.segna_vincitori(giveaway.id, vincitori, fase_successiva="annuncio")
        else:
            vincitori = await giveaway_repo.get_vincitori(giveaway.id)

        guild = bot.get_guild(giveaway.guild_id)
        canale = await _canale_del_giveaway(guild, giveaway.channel_id, solleva_se_discord_non_risponde=True)
        if canale is None:
            # Il canale non c'è più: nessuno a cui annunciare. I vincitori sono scelti e salvati.
            logger.warning(
                "Canale %s non raggiungibile per la fine del giveaway %s.", giveaway.channel_id, giveaway.id
            )
            await giveaway_repo.passa_a_fase(giveaway.id, "fatto")
            return

        opzioni = await giveaway_repo.get_opzioni(giveaway.guild_id)
        lingua = await lingua_risposta(giveaway.guild_id, pubblica=True)
        await concludi(
            canale, guild, giveaway, vincitori, opzioni, lingua, vista=_vista_riepilogo(giveaway.id),
            solleva_se_discord_non_risponde=True,
        )
        await giveaway_repo.passa_a_fase(giveaway.id, "fatto")

    async def _tentativo_fallito(self, bot: commands.Bot, giveaway, errore: Exception) -> None:
        """Un tentativo andato male: si riprova al giro dopo; dopo troppi si smette e si avvisa l'owner."""
        tentativi = await giveaway_repo.conta_tentativo_fine(giveaway.id)
        if tentativi < MAX_TENTATIVI_FINE:
            logger.warning("Fine del giveaway %s fallita (tentativo %d): riprovo.", giveaway.id, tentativi, exc_info=errore)
            return
        logger.error("Fine del giveaway %s fallita %d volte: mi fermo.", giveaway.id, tentativi, exc_info=errore)
        await giveaway_repo.passa_a_fase(giveaway.id, "fallito")
        from core.avvisi_owner import avvisi_owner

        avvisi_owner.caduto(bot, f"giveaway:{giveaway.id}", f"fine non riuscita dopo {tentativi} tentativi")

    async def _avvia(self, bot: commands.Bot, giveaway_id: int, adesso: datetime) -> None:
        """
        Pubblica un giveaway programmato. Prima lo si reclama (una scrittura
        sola: due giri insieme non lo mandano due volte), poi si scrive nel
        canale. Se il canale non c'è più, il bot non ha i permessi o l'invio
        fallisce, il giveaway resta programmato con il motivo dell'errore
        (lo staff lo vede in /admin-giveaway programmati): niente tentativi
        all'infinito e niente giveaway "finito" mai partito.
        """
        from cogs.leveling.leveling import LevelingCog  # qui dentro: il cog importa questo modulo

        giveaway = await giveaway_repo.claim_start(giveaway_id, adesso)
        if giveaway is None:
            return
        guild = bot.get_guild(giveaway.guild_id)
        canale = await _canale_del_giveaway(guild, giveaway.channel_id)
        if canale is None:
            await self._errore_di_partenza(
                giveaway, f"canale {giveaway.channel_id} non raggiungibile"
            )
            return
        motivo = motivo_se_il_bot_non_puo(
            canale, getattr(guild, "me", None), PERMESSI_DI_SCRITTURA
        )
        if motivo is not None:
            await self._errore_di_partenza(giveaway, motivo)
            return
        opzioni = await giveaway_repo.get_opzioni(giveaway.guild_id)
        lingua = await lingua_risposta(giveaway.guild_id, pubblica=True)
        try:
            file = await file_annuncio(giveaway.immagine_id)
            messaggio = await canale.send(
                embed=embed_annuncio(giveaway, opzioni, lingua),
                view=LevelingCog.GiveawayEnterView(giveaway.id, opzioni),
                **({"file": file} if file is not None else {}),
            )
        except discord.HTTPException as errore:
            await self._errore_di_partenza(giveaway, f"invio non riuscito ({errore.status})")
            return
        await giveaway_repo.set_message_id(giveaway.id, messaggio.id)

    async def _errore_di_partenza(self, giveaway, motivo: str) -> None:
        """Il programmato non è partito: non si chiude come finito, si segna l'errore."""
        logger.warning("Giveaway programmato %s non partito: %s.", giveaway.id, motivo)
        await giveaway_repo.segna_errore(giveaway.id, motivo)

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @giro_periodico(seconds=TICK_SECONDS, subito=True)
        async def _loop():
            await self.tick(bot)  # un errore lo gestisce il GiroPeriodico (pausa crescente e nuovo tentativo)

        @_loop.before_loop
        async def _before():
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Giveaway worker avviato (controllo ogni %ds).", TICK_SECONDS)


giveaway_worker = GiveawayWorker()
