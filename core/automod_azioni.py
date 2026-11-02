"""
core/automod_azioni.py
======================
Esegue le azioni di una regola AutoMod, una funzione corta per tipo, nell'ordine fisso di D63 (cancella, DM,
sanzione, ruolo e nickname, canale, avviso, staff). Scudo dei protetti su ogni azione invasiva; se Discord
risponde 403 l'azione si sospende per 10 minuti nel server e lo staff è avvisato una volta sola.
Funzione pubblica per gli altri filoni: `esegui_azioni(azioni, Bersaglio(...))`.
Funzioni coperte: SPEC §6 (AMD-040, 042-046, 048-053, 055, 056), D63
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import discord

from core import bot_roles
from core.automod_regole_logic import (
    AZIONI_SULL_UTENTE,
    MAX_MOTIVO,
    Azione,
    espandi_segnaposto,
    ordina_azioni,
)
from core.bounded_cache import BoundedCache
from core.scheduler import scheduler

logger = logging.getLogger("iyokai.automod.azioni")

SOSPENSIONE_S = 600  # una azione che fallisce per permessi riposa 10 minuti
ULTIMI_PER_UTENTE = 50
ULTIMI_VITA_S = 3600
MAX_GIORNI_BLOCCO = 14
PAUSA_AVVISO_S = 30
PAUSA_PING_S = 60
PAUSA_DM_STAFF_S = 300

AZIONE_RUOLO_FINE = "automod_ruolo_fine"
AZIONE_SLOWMODE_FINE = "automod_slowmode_fine"
AZIONE_PERMESSI_FINE = "automod_permessi_fine"

# Nome nel log: quello di prima per le azioni che già esistevano.
_NOME_NEL_LOG = {"cancella": "delete", "timeout": "mute"}

_sospese: BoundedCache[tuple[int, str], float] = BoundedCache(5000)
_ultimi: BoundedCache[tuple[int, int], deque] = BoundedCache(20_000)
_pause: BoundedCache[tuple, float] = BoundedCache(20_000)


@dataclass
class Bersaglio:
    """Su chi e dove agire. `membro` e `messaggio` mancano per gli eventi che non sono messaggi."""

    guild: discord.Guild
    motivo: str
    regola_chiave: str
    regola_nome: str
    membro: discord.Member | None = None
    messaggio: discord.Message | None = None
    canale: Any = None
    modificato: bool = False
    contatore: str | None = None  # il contatore della regola, per l'azione `azzera`
    canale_log_id: int | None = None  # il canale del log AutoMod scelto dal server
    rinviate: tuple = ()  # le sanzioni che aspettano lo staff (azione `decide_staff`)
    warn_consentito: Callable[[], bool] | None = None
    avvisa_staff: Callable[[str, int | None], Awaitable[None]] | None = None

    @property
    def motivo_audit(self) -> str:
        return f"AutoMod: {self.motivo}"[:MAX_MOTIVO]


def e_protetto(member: discord.Member) -> bool:
    """Mai sanzioni automatiche al proprietario del server né a chi ha `manage_guild` o `administrator`."""
    if member.guild.owner_id == member.id:
        return True
    return member.guild_permissions.administrator or member.guild_permissions.manage_guild


# ---------------------------------------------------------------- memoria con tetto

def _pausa_scaduta(chiave: tuple, secondi: float) -> bool:
    """True (e si segna) se è passata la pausa per questa chiave: serve a non ripetere avvisi, ping e DM."""
    adesso = time.monotonic()
    ultimo = _pause.get(chiave)
    if ultimo is not None and adesso - ultimo < secondi:
        return False
    _pause.set(chiave, adesso)
    return True


def sospesa(guild_id: int, tipo: str) -> bool:
    fino = _sospese.get((guild_id, tipo))
    return fino is not None and time.monotonic() < fino


def registra_messaggio(guild_id: int, user_id: int, canale_id: int, messaggio_id: int, ora: float | None = None) -> None:
    """Tiene gli ultimi messaggi di ogni utente (50, 1 ora) per `cancella_ultimi`, senza scorrere la cronologia."""
    coda = _ultimi.get((guild_id, user_id))
    if coda is None:
        coda = deque(maxlen=ULTIMI_PER_UTENTE)
        _ultimi.set((guild_id, user_id), coda)
    coda.append((canale_id, messaggio_id, ora if ora is not None else time.monotonic()))


def ultimi_da_cancellare(guild_id: int, user_id: int, n: int, minuti: int, adesso: float | None = None) -> dict[int, list[int]]:
    """{canale: [id messaggi]} degli ultimi `n` messaggi entro `minuti` minuti e meno di 14 giorni."""
    adesso = adesso if adesso is not None else time.monotonic()
    coda = _ultimi.get((guild_id, user_id)) or ()
    limite = min(minuti * 60, ULTIMI_VITA_S)
    scelti = [(c, m) for c, m, t in coda if adesso - t <= limite][-n:]
    fuori: dict[int, list[int]] = {}
    for canale_id, messaggio_id in scelti:
        if _eta_giorni(messaggio_id) < MAX_GIORNI_BLOCCO:
            fuori.setdefault(canale_id, []).append(messaggio_id)
    return fuori


def _eta_giorni(snowflake: int) -> float:
    creato = discord.utils.snowflake_time(snowflake)
    return (datetime.now(timezone.utc) - creato).total_seconds() / 86400


# ---------------------------------------------------------------- azioni

async def _cancella(a: Azione, b: Bersaglio) -> bool:
    if b.messaggio is None:
        return False
    try:
        await bot_roles.cancella_messaggio(b.messaggio)
    except discord.NotFound:
        return False
    return True


async def _cancella_ultimi(a: Azione, b: Bersaglio) -> bool:
    if b.membro is None:
        return False
    per_canale = ultimi_da_cancellare(b.guild.id, b.membro.id, a.get("n", 10), a.get("minuti", 10))
    fatto = False
    for canale_id, ids in per_canale.items():
        canale = b.guild.get_channel_or_thread(canale_id)
        if canale is None:
            continue
        oggetti = [canale.get_partial_message(i) for i in ids]
        try:
            if len(oggetti) == 1:
                await bot_roles.cancella_messaggio(oggetti[0])
            else:
                await bot_roles.cancella_messaggi(canale, oggetti)
            fatto = True
        except discord.NotFound:
            continue
    return fatto


def _testo_dm(b: Bersaglio, testo: str | None) -> discord.Embed:
    valori = {"utente": b.membro.display_name if b.membro else "", "canale": getattr(b.canale, "mention", ""),
              "regola": b.regola_nome, "server": b.guild.name}
    corpo = espandi_segnaposto(testo, valori) if testo else f"{b.guild.name}: {b.motivo}"
    return discord.Embed(title="Avviso dall'AutoMod", description=corpo[:1000], color=discord.Color.orange())


async def _dm(a: Azione, b: Bersaglio) -> bool:
    from cogs.moderation._shared import try_dm

    return b.membro is not None and await try_dm(b.membro, _testo_dm(b, a.get("testo")), guild_id=b.guild.id)


async def _warn(a: Azione, b: Bersaglio) -> bool:
    from cogs.moderation._shared import post_to_mod_log, try_dm
    from core.repositories.moderation_repo import moderation_repo

    if b.warn_consentito is not None and not b.warn_consentito():
        return False
    motivo = f"AutoMod: {b.motivo}"[:MAX_MOTIVO]
    numero = await moderation_repo.create_case(
        guild_id=b.guild.id, user_id=b.membro.id,
        moderator_id=b.guild.me.id if b.guild.me else b.membro.id, action_type="warn", reason=motivo,
    )
    embed = discord.Embed(title="⚠️ Warn automatico (AutoMod)", description=f"Caso #{numero} — {motivo}",
                          color=discord.Color.yellow())
    await try_dm(b.membro, embed)
    await post_to_mod_log(b.guild, embed)
    return True


async def _timeout(a: Azione, b: Bersaglio) -> bool:
    await bot_roles.isola(b.membro, timedelta(seconds=a.get("secondi")), reason=b.motivo_audit)
    return True


async def _mute_ruolo(a: Azione, b: Bersaglio) -> bool:
    from cogs.moderation.softban_mute import MUTE_ROLE_ACTION_TYPE, SCHEDULED_MUTE_EXPIRE, _get_or_create_mute_role
    from core.repositories.moderation_repo import moderation_repo

    ruolo = await _get_or_create_mute_role(b.guild)
    if ruolo is None:
        return False
    await bot_roles.aggiungi_ruolo(b.membro, ruolo, reason=b.motivo_audit)
    fine = discord.utils.utcnow() + timedelta(seconds=a.get("secondi"))
    await scheduler.cancel_for_user(b.guild.id, b.membro.id, SCHEDULED_MUTE_EXPIRE)
    numero = await moderation_repo.create_case(
        guild_id=b.guild.id, user_id=b.membro.id, moderator_id=b.guild.me.id if b.guild.me else b.membro.id,
        action_type=MUTE_ROLE_ACTION_TYPE, reason=b.motivo_audit, duration_seconds=a.get("secondi"),
    )
    await moderation_repo.save_mute_state(b.guild.id, b.membro.id, False, [], numero, fine)
    await scheduler.schedule(b.guild.id, b.membro.id, SCHEDULED_MUTE_EXPIRE, fine, {"caso": numero})
    return True


async def _dm_prima_dell_azione(b: Bersaglio, titolo: str):
    from cogs.moderation._shared import try_dm_message

    embed = discord.Embed(title=titolo, description=f"{b.guild.name}: {b.motivo}", color=discord.Color.orange())
    return await try_dm_message(b.membro, embed, guild_id=b.guild.id)


async def _kick(a: Azione, b: Bersaglio) -> bool:
    from cogs.moderation._shared import delete_dm

    dm = await _dm_prima_dell_azione(b, "Espulso dall'AutoMod")  # dopo, il bot non ha più un server in comune
    try:
        await bot_roles.espelli(b.membro, reason=b.motivo_audit)
    except discord.HTTPException:
        await delete_dm(dm)
        raise
    return True


async def _ban(a: Azione, b: Bersaglio) -> bool:
    from cogs.moderation._shared import delete_dm

    dm = await _dm_prima_dell_azione(b, "Bannato dall'AutoMod")
    motivo = b.motivo_audit
    try:
        await bot_roles.banna(b.guild, b.membro, reason=motivo, delete_message_seconds=0,
                              principale=lambda: b.membro.ban(reason=motivo, delete_message_seconds=0))
    except discord.HTTPException:
        await delete_dm(dm)
        raise
    return True


async def _ban_tempo(a: Azione, b: Bersaglio) -> bool:
    from cogs.moderation._shared import delete_dm
    from cogs.moderation.actions import SCHEDULED_TEMPBAN_EXPIRE, TEMPBAN_ACTION_TYPE
    from core.repositories.moderation_repo import moderation_repo

    secondi = a.get("giorni") * 86400
    dm = await _dm_prima_dell_azione(b, "Bannato a tempo dall'AutoMod")
    motivo = b.motivo_audit
    try:
        await bot_roles.banna(b.guild, b.membro, reason=motivo, delete_message_seconds=0,
                              principale=lambda: b.membro.ban(reason=motivo, delete_message_seconds=0))
    except discord.HTTPException:
        await delete_dm(dm)
        raise
    numero = await moderation_repo.create_case(
        guild_id=b.guild.id, user_id=b.membro.id, moderator_id=b.guild.me.id if b.guild.me else b.membro.id,
        action_type=TEMPBAN_ACTION_TYPE, reason=motivo, duration_seconds=secondi,
    )
    await moderation_repo.cancel_tempban_jobs(b.guild.id, b.membro.id)
    await scheduler.schedule(b.guild.id, b.membro.id, SCHEDULED_TEMPBAN_EXPIRE,
                             discord.utils.utcnow() + timedelta(seconds=secondi),
                             {"case_number": numero, "modo": "fuori"})
    return True


async def _ruolo(a: Azione, b: Bersaglio) -> bool:
    ruolo = b.guild.get_role(a.get("ruolo_id"))
    if ruolo is None:
        return False
    dai = a.get("op") == "dai"
    if dai == (ruolo in b.membro.roles):
        return False  # già così
    if dai:
        await bot_roles.aggiungi_ruolo(b.membro, ruolo, reason=b.motivo_audit)
    else:
        await bot_roles.togli_ruolo(b.membro, ruolo, reason=b.motivo_audit)
    if a.get("secondi"):  # a tempo: alla fine si fa il contrario
        await scheduler.schedule(b.guild.id, b.membro.id, AZIONE_RUOLO_FINE,
                                 discord.utils.utcnow() + timedelta(seconds=a.get("secondi")),
                                 {"ruolo_id": ruolo.id, "rimetti": not dai})
    return True


async def _nickname(a: Azione, b: Bersaglio) -> bool:
    nuovo = espandi_segnaposto(a.get("testo", ""), {"utente": b.membro.name})[:32] or None
    await b.membro.edit(nick=nuovo, reason=b.motivo_audit)
    return True


async def _slowmode(a: Azione, b: Bersaglio) -> bool:
    canale = b.canale
    if canale is None or not hasattr(canale, "slowmode_delay") or canale.slowmode_delay:
        return False  # non si tocca un canale che ha già uno slowmode
    await canale.edit(slowmode_delay=a.get("secondi"), reason=b.motivo_audit)
    await scheduler.schedule(b.guild.id, canale.id, AZIONE_SLOWMODE_FINE,
                             discord.utils.utcnow() + timedelta(seconds=a.get("durata_s")),
                             {"canale_id": canale.id, "valore": a.get("secondi")})
    return True


async def _permessi(a: Azione, b: Bersaglio) -> bool:
    """Solo modelli che tolgono: blocca la scrittura per un ruolo (o @everyone), sempre con ripristino."""
    obiettivo = b.guild.get_role(a.get("ruolo_id")) if a.get("ruolo_id") else b.guild.default_role
    canali = [b.guild.get_channel(i) for i in a.get("canali", ())] or [b.canale]
    fatto = False
    for canale in canali[:5]:
        if obiettivo is None or canale is None or not hasattr(canale, "overwrites_for"):
            continue
        regole = canale.overwrites_for(obiettivo)
        if regole.send_messages is False:
            continue
        prima = regole.send_messages
        regole.send_messages = False
        await canale.set_permissions(obiettivo, overwrite=regole, reason=b.motivo_audit)
        await scheduler.schedule(b.guild.id, canale.id, AZIONE_PERMESSI_FINE,
                                 discord.utils.utcnow() + timedelta(seconds=a.get("durata_s")),
                                 {"canale_id": canale.id, "ruolo_id": obiettivo.id, "prima": prima})
        fatto = True
    return fatto


async def _thread_archivia(a: Azione, b: Bersaglio) -> bool:
    canale = b.canale
    if not isinstance(canale, discord.Thread):
        return False
    await canale.edit(archived=True, reason=b.motivo_audit)
    return True


async def _thread_apri(a: Azione, b: Bersaglio) -> bool:
    if b.messaggio is None or isinstance(b.canale, discord.Thread):
        return False
    nome = espandi_segnaposto(a.get("nome"), {"utente": b.membro.name if b.membro else "", "regola": b.regola_nome})
    await b.messaggio.create_thread(name=nome[:100], reason=b.motivo_audit)
    return True


async def _avviso_canale(a: Azione, b: Bersaglio) -> bool:
    if b.canale is None or not _pausa_scaduta(("avviso", b.guild.id, b.membro.id if b.membro else 0, b.regola_chiave),
                                              PAUSA_AVVISO_S):
        return False
    valori = {"utente": b.membro.mention if b.membro else "", "canale": getattr(b.canale, "mention", ""),
              "regola": b.regola_nome, "server": b.guild.name}
    await b.canale.send(espandi_segnaposto(a.get("testo"), valori),
                        delete_after=a.get("dopo_s", 10), allowed_mentions=discord.AllowedMentions.none())
    return True


async def _log(a: Azione, b: Bersaglio) -> bool:
    """Il log c'è sempre (lo scrive il cog); qui solo il ping al ruolo, al massimo uno al minuto per regola e canale."""
    ruolo = a.get("ping_ruolo")
    if not ruolo or b.avvisa_staff is None:
        return False
    if not _pausa_scaduta(("ping", b.guild.id, b.regola_chiave, getattr(b.canale, "id", 0)), PAUSA_PING_S):
        return False
    await b.avvisa_staff(f"<@&{ruolo}> AutoMod: {b.regola_nome}", ruolo)
    return True


async def _dm_staff(a: Azione, b: Bersaglio) -> bool:
    from cogs.moderation._shared import try_dm

    if not _pausa_scaduta(("dmstaff", b.guild.id, b.regola_chiave), PAUSA_DM_STAFF_S):
        return False
    embed = discord.Embed(title=f"AutoMod: {b.regola_nome}", color=discord.Color.orange(),
                          description=f"{b.guild.name}: {b.motivo}"[:1000])
    if b.membro is not None:
        embed.add_field(name="Utente", value=f"{b.membro.mention} ({b.membro.id})")
    inviati = [await try_dm(discord.Object(id=u), embed, guild_id=b.guild.id) for u in a.get("utenti", ())]
    return any(inviati)


async def _decide_staff(a: Azione, b: Bersaglio) -> bool:
    """AMD-047: le sanzioni della regola aspettano il bottone di un moderatore (vedi core/automod_decisioni.py)."""
    from core.automod_decisioni import chiedi_allo_staff

    return await chiedi_allo_staff(b, list(b.rinviate))


async def _azzera(a: Azione, b: Bersaglio) -> bool:
    """AMD-061: azzera i contatori dell'utente (quelli scelti, o quello della regola) e, se serve, la scala."""
    from core.repositories.automod_advanced_repo import automod_advanced_repo
    from core.repositories.escalation_repo import escalation_repo

    nomi = list(a.get("contatori") or ([b.contatore] if b.contatore else []))
    fatto = False
    for nome in nomi:
        fatto = bool(await automod_advanced_repo.svuota_contatore_utente(b.guild.id, b.membro.id, nome)) or fatto
    if a.get("scala"):
        await escalation_repo.reset_violations(b.guild.id, b.membro.id)
        fatto = True
    return fatto


_FUNZIONI: dict[str, Callable[[Azione, Bersaglio], Awaitable[bool]]] = {
    "cancella": _cancella, "cancella_ultimi": _cancella_ultimi, "dm": _dm, "warn": _warn, "timeout": _timeout,
    "mute_ruolo": _mute_ruolo, "kick": _kick, "ban": _ban, "ban_tempo": _ban_tempo, "ruolo": _ruolo,
    "nickname": _nickname, "slowmode": _slowmode, "permessi": _permessi, "thread_archivia": _thread_archivia,
    "thread_apri": _thread_apri, "avviso_canale": _avviso_canale, "log": _log, "dm_staff": _dm_staff,
    "azzera": _azzera, "decide_staff": _decide_staff,
}


async def esegui_azioni(azioni: tuple[Azione, ...] | list[Azione], b: Bersaglio) -> tuple[str, ...]:
    """
    Esegue le azioni nell'ordine di D63 e restituisce i nomi di quelle DAVVERO eseguite (per il log).
    Un'azione che non si applica o fallisce non ferma le altre.
    """
    from core.automod_decisioni import RINVIABILI

    eseguite: list[str] = []
    protetto = b.membro is not None and e_protetto(b.membro)
    if any(a.t == "decide_staff" for a in azioni):  # le sanzioni aspettano lo staff; il resto parte subito
        b.rinviate = tuple(a for a in azioni if a.t in RINVIABILI) if not protetto else ()
        azioni = [a for a in azioni if a.t not in RINVIABILI]
    for azione in ordina_azioni(azioni):
        funzione = _FUNZIONI.get(azione.t)
        if funzione is None or sospesa(b.guild.id, azione.t):
            continue
        if azione.t in AZIONI_SULL_UTENTE and (b.membro is None or protetto):
            continue
        if azione.t in ("warn", "dm", "cancella_ultimi", "azzera") and b.membro is None:
            continue
        try:
            if await funzione(azione, b):
                eseguite.append(_NOME_NEL_LOG.get(azione.t, azione.t))
        except discord.Forbidden:
            await _sospendi(b, azione.t)
        except discord.HTTPException as errore:
            logger.info("AutoMod: azione %s non riuscita nel server %s: %s", azione.t, b.guild.id, errore)
    return tuple(eseguite)


async def _sospendi(b: Bersaglio, tipo: str) -> None:
    prima = sospesa(b.guild.id, tipo)
    _sospese.set((b.guild.id, tipo), time.monotonic() + SOSPENSIONE_S)
    if not prima and b.avvisa_staff is not None:
        try:
            await b.avvisa_staff(
                f"AutoMod: l'azione `{tipo}` non è permessa al bot, la sospendo per 10 minuti. "
                "Controlla i permessi e la posizione del ruolo del bot.", None)
        except discord.HTTPException:
            pass


# ---------------------------------------------------------------- fine delle azioni a tempo (scheduler)

async def gestisci_ruolo_fine(bot: discord.Client, guild_id: int, user_id: int, payload: dict) -> None:
    guild = bot.get_guild(guild_id)
    if guild is None:
        return
    membro = guild.get_member(user_id) or await _membro(guild, user_id)
    ruolo = guild.get_role(payload.get("ruolo_id", 0))
    if membro is None or ruolo is None:
        return
    if payload.get("rimetti"):
        await bot_roles.aggiungi_ruolo(membro, ruolo, reason="AutoMod: fine del ruolo a tempo")
    else:
        await bot_roles.togli_ruolo(membro, ruolo, reason="AutoMod: fine del ruolo a tempo")


async def _membro(guild: discord.Guild, user_id: int):
    try:
        return await guild.fetch_member(user_id)
    except discord.HTTPException:
        return None


async def gestisci_slowmode_fine(bot: discord.Client, guild_id: int, user_id: int, payload: dict) -> None:
    guild = bot.get_guild(guild_id)
    canale = guild.get_channel_or_thread(payload.get("canale_id", 0)) if guild else None
    if canale is not None and canale.slowmode_delay == payload.get("valore"):  # se un admin l'ha cambiato, resta
        await canale.edit(slowmode_delay=0, reason="AutoMod: fine dello slowmode a tempo")


async def gestisci_permessi_fine(bot: discord.Client, guild_id: int, user_id: int, payload: dict) -> None:
    guild = bot.get_guild(guild_id)
    canale = guild.get_channel(payload.get("canale_id", 0)) if guild else None
    ruolo = guild.get_role(payload.get("ruolo_id", 0)) if guild else None
    if canale is None or ruolo is None:
        return
    regole = canale.overwrites_for(ruolo)
    if regole.send_messages is not False:  # un admin l'ha già cambiato
        return
    regole.send_messages = payload.get("prima")
    await canale.set_permissions(ruolo, overwrite=None if regole.is_empty() else regole,
                                 reason="AutoMod: fine del blocco a tempo")
