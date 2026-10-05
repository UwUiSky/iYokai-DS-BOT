"""
core/guild_clan_voice_worker.py
===================================
Servizio periodico che applica i tick vocali dei membri di clan
(SPEC.md §15.14) — stesso pattern di feed_watcher.py/leveling
(_process_guild_voice_xp): tasks.loop avviato una volta da main.py,
non un Cog.

Tick al MINUTO (confermato esplicitamente dall'utente — non ai 2
minuti, quella finestra è solo manutenzione/reset giornaliero
23:59->00:01, non un tick vero). Iterando i canali vocali live dei
server, non c'è bisogno di on_voice_state_update per sapere chi è
dove in questo istante — lo stato PRECEDENTE (canale, decadimento,
tetto) vive nel database tramite core/repositories/clan_voice_
activity_repo.py, già committato.
Valgono le stesse regole anti-farm dell'XP vocale normale
(core.leveling_logic.is_eligible_for_voice_xp).
Funzioni coperte: SPEC §15.14; REVIEW.md LC-8 (errori isolati per server
nel giro), SEC-21 (gli utenti in blacklist non maturano nulla).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.guild_clan_boost_logic import compute_boosted_reward, is_boost_active
from core.guild_iteration import for_each_guild_safely
from core.leveling_logic import is_eligible_for_voice_xp
from core.repositories.blacklist_repo import blacklist_repo
from core.repositories.clan_voice_activity_repo import clan_voice_activity_repo
from core.repositories.guild_clan_repo import REASON_VOICE_TICK, guild_clan_repo

logger = logging.getLogger("iyokai.guild_clan_voice_worker")

TICK_SECONDS = 60


class GuildClanVoiceWorker:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, bot: commands.Bot, now: datetime | None = None) -> None:
        adesso = now or datetime.now(timezone.utc)
        oggi: date = adesso.date()

        trovati_in_vocale: set[tuple[int, int]] = set()

        async def _per_server(guild) -> None:
            id_canale_afk = guild.afk_channel.id if guild.afk_channel else None
            for canale in guild.voice_channels:
                persone = [m for m in canale.members if not m.bot]
                for membro in persone:
                    # SEC-21: chi è in blacklist non porta XP, coin
                    # né ore vocali al clan (controllo in cache).
                    if await blacklist_repo.is_user_blacklisted(membro.id):
                        continue

                    # Stesse regole anti-farm dell'XP vocale normale:
                    # niente canale AFK, niente utente assordato, e
                    # almeno un'altra persona non mutata nel canale. Chi
                    # non le rispetta vale come "non in vocale": nessun
                    # guadagno, nessuna ora accumulata.
                    altri_non_mutati = sum(
                        1 for altro in persone
                        if altro.id != membro.id and not altro.voice.self_mute
                    )
                    if not is_eligible_for_voice_xp(
                        is_self_deaf=membro.voice.self_deaf,
                        is_afk_channel=canale.id == id_canale_afk,
                        other_members_not_self_muted=altri_non_mutati,
                    ):
                        continue

                    clan = await guild_clan_repo.get_member_clan_in_guild(guild.id, membro.id)
                    if clan is None or not clan.officialized:
                        # Non ufficializzato = ancora in prova, non
                        # matura ancora XP/coin di gilda: l'utente
                        # deve prima colmare il deficit di creazione.
                        continue

                    trovati_in_vocale.add((clan.id, membro.id))

                    xp, coin = await clan_voice_activity_repo.apply_tick(
                        clan.id, membro.id, canale.id, oggi
                    )
                    # Le ore vocali ACCUMULATE dalla gilda (requisito
                    # per lo sblocco canali extra, SPEC.md §15.14)
                    # contano la presenza in sé — a differenza di
                    # XP/coin non si azzerano per decadimento o tetto
                    # giornaliero, quindi il conteggio va SEMPRE, non
                    # solo quando xp/coin > 0.
                    await guild_clan_repo.add_voice_ticks(clan.id, 1)

                    if xp > 0 or coin > 0:
                        # I boost (SPEC.md §15.14) moltiplicano solo
                        # la ricompensa già calcolata — mai le ore
                        # accumulate sopra, che restano un conteggio
                        # di presenza indipendente dal guadagno.
                        membro_clan = await guild_clan_repo.get_member(clan.id, membro.id)
                        individuale_attivo = is_boost_active(
                            membro_clan.boost_expires_at if membro_clan else None, adesso
                        )
                        gilda_attivo = is_boost_active(clan.guild_boost_expires_at, adesso)
                        xp, coin = compute_boosted_reward(
                            xp, coin, individual_active=individuale_attivo, guild_active=gilda_attivo
                        )

                    if xp > 0:
                        await guild_clan_repo.add_xp(clan.id, xp)
                    if coin > 0:
                        await guild_clan_repo.apply_treasury_delta(
                            clan.id, coin, reason=REASON_VOICE_TICK
                        )

        # LC-8: un server problematico non blocca gli altri.
        falliti = await for_each_guild_safely(
            bot.guilds, _per_server, nome_worker="Guild clan voice worker"
        )
        if falliti:
            # Chi stava in un server fallito non è stato ritrovato: la
            # pulizia qui sotto lo scambierebbe per uscito dal vocale e
            # ne azzererebbe lo stato. Si rifà al prossimo giro.
            return

        # Chi risultava "in vocale" al tick precedente ma non è stato
        # ritrovato in NESSUN canale in questo giro è uscito dal
        # vocale nel frattempo — va ripulito, altrimenti al rientro
        # (magari ore dopo) verrebbe trattato come se non avesse mai
        # smesso, con un decadimento già a metà strada invece che da
        # zero.
        for clan_id, user_id in await clan_voice_activity_repo.get_tracked_as_in_voice():
            if (clan_id, user_id) not in trovati_in_vocale:
                await clan_voice_activity_repo.clear_activity(clan_id, user_id)

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @tasks.loop(seconds=TICK_SECONDS)
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel tick del guild clan voice worker")

        @_loop.before_loop
        async def _before():
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()
        logger.info("Guild clan voice worker avviato (controllo ogni %ds).", TICK_SECONDS)


guild_clan_voice_worker = GuildClanVoiceWorker()
