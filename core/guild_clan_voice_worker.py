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
Chi è escluso dall'XP (canale, categoria o ruolo, `/level impostazioni
escludi`) non matura nulla nemmeno per la gilda: stessa regola dell'XP
testuale dei clan.
Le letture e le scritture sono raggruppate per server e per clan
(M 9.18, PERF-4): il numero di query non cresce con le persone in vocale.
Funzioni coperte: SPEC §15.14; REVIEW.md LC-8 (errori isolati per server
nel giro), SEC-21 (gli utenti in blacklist non maturano nulla).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from discord.ext import commands, tasks

from core.bot_ready import attendi_bot_pronto
from core.guild_clan_boost_logic import Beneficio, benefici_attivi, compute_boosted_reward
from core.guild_iteration import for_each_guild_safely
from core.leveling_logic import ConfigLivelli, id_canali_per_le_regole, is_eligible_for_voice_xp
from core.repositories.blacklist_repo import blacklist_repo
from core.repositories.clan_voice_activity_repo import clan_voice_activity_repo
from core.repositories.guild_clan_repo import REASON_VOICE_TICK, guild_clan_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo

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
            try:
                regole = await leveling_settings_repo.get_config(guild.id)
            except Exception:
                logger.warning("Impostazioni dei livelli non lette per %s.", guild.id)
                regole = ConfigLivelli()
            candidati: list[tuple[object, object]] = []  # (membro, canale)
            for canale in guild.voice_channels:
                persone = [m for m in canale.members if not m.bot]
                for membro in persone:
                    # SEC-21: chi è in blacklist non porta XP, coin
                    # né ore vocali al clan (controllo in cache).
                    if await blacklist_repo.is_user_blacklisted(membro.id):
                        continue

                    # NF-15: canali, categorie e ruoli senza XP valgono come
                    # "non in vocale" anche per la gilda.
                    if regole.e_escluso(
                        id_canali_per_le_regole(canale), [r.id for r in getattr(membro, "roles", [])]
                    ):
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
                    candidati.append((membro, canale))
            if candidati:
                await self._accredita_server(guild.id, candidati, oggi, adesso, trovati_in_vocale)

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
        usciti = [
            coppia
            for coppia in await clan_voice_activity_repo.get_tracked_as_in_voice()
            if coppia not in trovati_in_vocale
        ]
        await clan_voice_activity_repo.clear_activities(usciti)

    @staticmethod
    async def _accredita_server(guild_id, candidati, oggi: date, adesso: datetime, trovati: set) -> None:
        """
        Tick e guadagni di un server con query raggruppate (M 9.18, PERF-4):
        una lettura dei clan, una transazione per i tick, poi tre scritture
        per clan (ore, XP, tesoreria) invece di sei per persona.
        """
        membri = await guild_clan_repo.get_membri_in_gilda(guild_id, [m.id for m, _ in candidati])
        voci, schede = [], []
        for membro, canale in candidati:
            clan, scheda = membri.get(membro.id, (None, None))
            if clan is None or not clan.officialized:
                # Non ufficializzato = ancora in prova, non matura ancora
                # XP/coin di gilda: prima va colmato il deficit di creazione.
                continue
            trovati.add((clan.id, membro.id))
            voci.append((clan.id, membro.id, canale.id))
            schede.append((clan, scheda))

        per_clan: dict[int, list[int]] = {}  # clan_id -> [tick, xp, coin]
        for (clan, scheda), (xp, coin) in zip(schede, await clan_voice_activity_repo.apply_ticks(voci, oggi)):
            if xp > 0 or coin > 0:
                # I boost (SPEC.md §15.14) moltiplicano solo la ricompensa
                # già calcolata, mai le ore accumulate.
                individuali = benefici_attivi(
                    scheda.boost_exp_expires_at, scheda.boost_coin_expires_at, adesso
                )
                di_gilda = benefici_attivi(
                    clan.guild_boost_exp_expires_at, clan.guild_boost_coin_expires_at, adesso
                )
                xp, coin = compute_boosted_reward(
                    xp, coin,
                    individuale_exp=Beneficio.EXP in individuali,
                    individuale_coin=Beneficio.COIN in individuali,
                    gilda_exp=Beneficio.EXP in di_gilda,
                    gilda_coin=Beneficio.COIN in di_gilda,
                )
            somme = per_clan.setdefault(clan.id, [0, 0, 0])
            somme[0] += 1
            somme[1] += xp
            somme[2] += coin

        for clan_id, (tick, xp, coin) in per_clan.items():
            # Le ore vocali della gilda (sblocco canali extra) contano la
            # presenza: salgono SEMPRE, anche con XP e coin a zero.
            await guild_clan_repo.add_voice_ticks(clan_id, tick)
            if xp > 0:
                await guild_clan_repo.add_xp(clan_id, xp)
            if coin > 0:
                await guild_clan_repo.apply_treasury_delta(clan_id, coin, reason=REASON_VOICE_TICK)

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
