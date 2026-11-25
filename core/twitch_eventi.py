"""
core/twitch_eventi.py
=====================
Crea gli eventi Discord dal calendario di un canale Twitch (ALR-013), per gli avvisi che hanno l'opzione
accesa. Una richiesta al calendario per avviso ogni 30 minuti (minimo 10), al massimo 5 puntate per avviso
e mai oltre i 100 eventi del server. Serve il permesso «Gestisci eventi». Titoli ripuliti e tagliati.
Funzioni coperte: SPEC §10.1 (#129 ALR-013)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

from core.alert_frequenze_logic import intervallo
from core.alert_messaggio_logic import pulisci_esterno
from core.bot_ready import attendi_bot_pronto
from core.repositories.twitch_eventi_repo import twitch_eventi_repo
from core.giro_periodico import giro_periodico

logger = logging.getLogger("iyokai.twitch_eventi")

MAX_PUNTATE_PER_AVVISO = 5
MAX_EVENTI_SERVER = 100  # limite di Discord
DURATA_PREDEFINITA = timedelta(hours=2)
MAX_ANTICIPO = timedelta(days=14)


def _data(testo: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat((testo or "").replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def puo_creare_eventi(guild: discord.Guild) -> bool:
    me = guild.me
    return me is not None and me.guild_permissions.manage_events and len(guild.scheduled_events) < MAX_EVENTI_SERVER


async def crea_eventi_del_canale(guild: discord.Guild, sub_id: int, login: str, segmenti: list, adesso: datetime) -> int:
    """Crea gli eventi mancanti per le prossime puntate di un canale; restituisce quanti ne ha creati."""
    fatti = await twitch_eventi_repo.segmenti_fatti(guild.id, sub_id)
    creati = 0
    for seg in segmenti:
        if creati >= MAX_PUNTATE_PER_AVVISO:
            break
        inizio = _data(seg.inizio)
        if seg.cancellata or seg.id in fatti or inizio is None or inizio <= adesso or inizio - adesso > MAX_ANTICIPO:
            continue
        if not puo_creare_eventi(guild):
            break
        fine = _data(seg.fine) or inizio + DURATA_PREDEFINITA
        if fine <= inizio:
            fine = inizio + DURATA_PREDEFINITA
        titolo = pulisci_esterno(seg.titolo, 100) or f"Diretta di {login}"
        try:
            evento = await guild.create_scheduled_event(
                name=titolo[:100], start_time=inizio, end_time=fine, entity_type=discord.EntityType.external,
                location=f"https://twitch.tv/{login}"[:100], privacy_level=discord.PrivacyLevel.guild_only,
                description=(f"🎮 {pulisci_esterno(seg.categoria, 100)}" if seg.categoria else None),
                reason="Calendario Twitch (avvisi)",
            )
        except discord.HTTPException:
            logger.warning("Evento dal calendario Twitch non creato (server %s)", guild.id)
            break
        await twitch_eventi_repo.segna(guild.id, sub_id, seg.id, evento.id, inizio)
        creati += 1
    return creati


class TwitchEventiService:
    def __init__(self) -> None:
        self._loop_task: tasks.Loop | None = None

    async def tick(self, bot: commands.Bot) -> None:
        from core.feed_alert_gate import modulo_alert_attivo
        from core.twitch_watcher import twitch_watcher

        avvisi = await twitch_eventi_repo.avvisi_con_eventi()
        if not avvisi:
            return
        await twitch_eventi_repo.pulisci_vecchi()
        calendari: dict[str, list] = {}  # un canale seguito da più server: una sola richiesta
        for a in avvisi:
            guild = bot.get_guild(a.guild_id)
            if guild is None or not await modulo_alert_attivo(a.guild_id) or not puo_creare_eventi(guild):
                continue
            login = a.twitch_login.lower()
            if login not in calendari:
                calendari[login] = await twitch_watcher.calendario(login)
            await crea_eventi_del_canale(guild, a.sub_id, login, calendari[login], datetime.now(timezone.utc))

    def start(self, bot: commands.Bot) -> None:
        if self._loop_task is not None:
            return

        @giro_periodico(seconds=intervallo("eventi"))
        async def _loop():
            try:
                await self.tick(bot)
            except Exception:
                logger.exception("Errore nel giro degli eventi dal calendario Twitch")

        @_loop.before_loop
        async def _before():
            await attendi_bot_pronto(bot)

        self._loop_task = _loop
        _loop.start()

    def stop(self) -> None:
        if self._loop_task is not None:
            self._loop_task.cancel()
            self._loop_task = None


twitch_eventi = TwitchEventiService()
