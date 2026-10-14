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
from core.giveaway_logic import descrizione_giveaway, pick_winners_pesati, titolo_giveaway
from core.repositories.giveaway_repo import giveaway_repo

logger = logging.getLogger("iyokai.giveaway_worker")

TICK_SECONDS = 30


async def _canale_del_giveaway(
    guild: discord.Guild | None, channel_id: int
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
        except discord.HTTPException:
            return None
    return canale if isinstance(canale, discord.abc.Messageable) else None


class GiveawayWorker:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, bot: commands.Bot, now: datetime | None = None) -> None:
        adesso = now or datetime.now(timezone.utc)

        for programmato in await giveaway_repo.get_giveaways_to_start(adesso):
            try:
                await self._avvia(bot, programmato.id, adesso)
            except Exception:
                logger.exception("Giveaway %s non partito", programmato.id)

        for giveaway in await giveaway_repo.get_due_giveaways(adesso):
            # Segnato concluso SUBITO, prima di qualunque operazione
            # che potrebbe fallire (canale sparito, ecc.) — un
            # giveaway scaduto non deve restare "dovuto" per sempre
            # e essere ritentato ad ogni tick. Chi non riesce a segnarlo
            # (un altro giro l'ha già fatto) non annuncia: un solo annuncio.
            if not await giveaway_repo.mark_ended(giveaway.id):
                continue

            partecipanti = await giveaway_repo.get_weighted_entries(giveaway.id)
            vincitori = pick_winners_pesati(partecipanti, giveaway.winners_count, random.Random())

            guild = bot.get_guild(giveaway.guild_id)
            canale = await _canale_del_giveaway(guild, giveaway.channel_id)
            if canale is None:
                logger.warning(
                    "Canale %s non raggiungibile per la fine del giveaway %s.",
                    giveaway.channel_id,
                    giveaway.id,
                )
                continue

            if not vincitori:
                testo = f"🎉 Il giveaway per **{giveaway.prize}** è terminato, ma nessuno ha partecipato."
            else:
                menzioni = ", ".join(f"<@{uid}>" for uid in vincitori)
                testo = f"🎉 Congratulazioni {menzioni}! Avete vinto **{giveaway.prize}**!"

            try:
                await canale.send(testo)
            except discord.HTTPException:
                logger.warning(
                    "Impossibile annunciare la fine del giveaway %s nel canale %s.",
                    giveaway.id,
                    giveaway.channel_id,
                )

    async def _avvia(self, bot: commands.Bot, giveaway_id: int, adesso: datetime) -> None:
        """
        Pubblica un giveaway programmato. Prima lo si reclama (una scrittura
        sola: due giri insieme non lo mandano due volte), poi si scrive nel
        canale. Se il canale non c'è più, il bot non ha i permessi o l'invio
        fallisce, il giveaway resta programmato con il motivo dell'errore
        (lo staff lo vede in /economia giveaway-programmati): niente tentativi
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
        io = getattr(guild, "me", None)
        if io is not None:
            permessi = canale.permissions_for(io) if hasattr(canale, "permissions_for") else None
            if permessi is not None and not (
                permessi.view_channel and permessi.send_messages and permessi.embed_links
            ):
                await self._errore_di_partenza(
                    giveaway, "il bot non può vedere o scrivere con gli embed in quel canale"
                )
                return
        embed = discord.Embed(
            title=titolo_giveaway(giveaway.prize),
            description=descrizione_giveaway(giveaway),
            color=discord.Color.blurple(),
        )
        try:
            messaggio = await canale.send(embed=embed, view=LevelingCog.GiveawayEnterView(giveaway.id))
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

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel tick del giveaway worker")

        @_loop.before_loop
        async def _before():
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Giveaway worker avviato (controllo ogni %ds).", TICK_SECONDS)


giveaway_worker = GiveawayWorker()
