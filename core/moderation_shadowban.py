"""
core/moderation_shadowban.py
============================
Lo shadowban (D127): il membro perde i suoi ruoli, riceve il ruolo «Shadowban» che nega la vista su ogni canale
tranne due dedicati (uno di testo e uno vocale, visibili solo agli shadowbannati e agli admin) e li riprende al
rilascio, a mano o alla scadenza. Lo stato (con i ruoli tolti) si scrive prima di toccare il membro, con una chiave
unica: due shadowban insieme sulla stessa persona ne fanno passare uno solo. Come la quarantena (MOD-016).
Funzioni coperte: D127, D136 (shadowban), CFG-024 (azione «shadowban»)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import discord

from core.moderation_quarantena import ruoli_da_salvare
from core.repositories.moderation_repo import moderation_repo
from core.security_quarantine import _blocco

logger = logging.getLogger("iyokai.moderation.shadowban")

SCHEDULED_SHADOWBAN_FINE = "moderation_shadowban_end"
CASO_SHADOWBAN = "shadowban"
MAX_DURATA_SECONDI = 365 * 86400
NOME_RUOLO = "Shadowban"
NOME_CANALE_TESTO = "shadowban"
NOME_CANALE_VOCALE = "Shadowban"
# Il bot deve poter gestire i ruoli (toglierli e ridarli) e i canali (blocco e canali dedicati).
PERMESSI_BOT = ("manage_roles", "manage_channels")
# Come per il mute a ruolo: tetto di canali per giro e pausa tra i gruppi (limite di Discord sui permessi).
MAX_CANALI_BLOCCO = 500
GRUPPO_BLOCCO = 8
PAUSA_BLOCCO = 0.4


def permessi_bot_mancanti(guild: discord.Guild) -> list[str]:
    """I permessi che servono al bot e che non ha (controllati prima di toccare qualcosa)."""
    permessi = guild.me.guild_permissions
    return [p for p in PERMESSI_BOT if not getattr(permessi, p, False)]


def bersaglio_ammesso(member: discord.Member) -> bool:
    """Mai il proprietario del server, mai il bot, mai chi sta sopra il bot (o alla pari)."""
    guild = member.guild
    if member.id == guild.owner_id or member.id == guild.me.id:
        return False
    return member.top_role.position < guild.me.top_role.position


@dataclass(frozen=True)
class Preparazione:
    ruolo: discord.Role
    canale_testo: discord.TextChannel
    canale_vocale: discord.VoiceChannel | discord.StageChannel


@dataclass(frozen=True)
class EsitoShadowban:
    riuscita: bool
    caso: int | None = None
    gia: bool = False  # la persona era già in shadowban: non si è fatto niente
    ruoli_non_tolti: bool = False
    permessi_mancanti: tuple[str, ...] = ()
    ruoli_salvati: tuple[int, ...] = ()


def _permessi_ruolo_testo() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)


def _permessi_ruolo_vocale() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)


async def _imposta_canale_dedicato(canale, ruolo: discord.Role, testo: bool) -> None:
    """Visibile solo al ruolo shadowban (e a chi ha «Amministratore»): @everyone non lo vede."""
    motivo = "Shadowban: canale dedicato"
    await canale.set_permissions(canale.guild.default_role, view_channel=False, reason=motivo)
    await canale.set_permissions(
        ruolo, overwrite=_permessi_ruolo_testo() if testo else _permessi_ruolo_vocale(), reason=motivo
    )


def _canale_valido(guild: discord.Guild, canale_id: int | None, tipi: tuple):
    canale = guild.get_channel(canale_id) if canale_id else None
    return canale if isinstance(canale, tipi) else None


async def prepara(
    guild: discord.Guild,
    testo: discord.TextChannel | None = None,
    vocale: discord.VoiceChannel | discord.StageChannel | None = None,
) -> Preparazione | None:
    """
    Il ruolo e i due canali dedicati: usa quelli scelti dallo staff (`testo`, `vocale`) o quelli già salvati e
    crea ciò che manca. None se Discord rifiuta la creazione del ruolo o dei canali. Il blocco sugli altri canali
    si mette con `blocca_canali`. Una sola preparazione alla volta per server.
    """
    async with _blocco(guild.id):
        cfg = await moderation_repo.get_shadowban_config(guild.id)
        try:
            ruolo = guild.get_role(cfg["ruolo_id"]) if cfg["ruolo_id"] else None
            if ruolo is None:
                ruolo = await guild.create_role(name=NOME_RUOLO, reason="Shadowban: ruolo creato da iYokai")
            scelto_testo = testo or _canale_valido(guild, cfg["canale_testo_id"], (discord.TextChannel,))
            scelto_vocale = vocale or _canale_valido(
                guild, cfg["canale_vocale_id"], (discord.VoiceChannel, discord.StageChannel)
            )
            if scelto_testo is None:
                scelto_testo = await guild.create_text_channel(
                    NOME_CANALE_TESTO, reason="Shadowban: canale dedicato",
                    overwrites={
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        ruolo: _permessi_ruolo_testo(),
                        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
                    },
                )
            elif testo is not None:
                await _imposta_canale_dedicato(scelto_testo, ruolo, True)
            if scelto_vocale is None:
                scelto_vocale = await guild.create_voice_channel(
                    NOME_CANALE_VOCALE, reason="Shadowban: canale dedicato",
                    overwrites={
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                        ruolo: _permessi_ruolo_vocale(),
                        guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, move_members=True),
                    },
                )
            elif vocale is not None:
                await _imposta_canale_dedicato(scelto_vocale, ruolo, False)
        except discord.HTTPException:
            logger.warning("Shadowban: ruolo o canali dedicati non preparati (server %s).", guild.id)
            return None
        await moderation_repo.salva_shadowban_config(guild.id, ruolo.id, scelto_testo.id, scelto_vocale.id)
        return Preparazione(ruolo, scelto_testo, scelto_vocale)


def visibile_a_tutti(canale) -> bool:
    """True se @everyone vede il canale (nessun divieto esplicito): scegliendolo come dedicato lo si nasconderebbe."""
    return canale.overwrites_for(canale.guild.default_role).view_channel is not False


def _ha_blocco(canale, ruolo: discord.Role) -> bool:
    return canale.overwrites_for(ruolo).view_channel is False


async def _blocca_canale(canale, ruolo: discord.Role) -> bool:
    try:
        await canale.set_permissions(ruolo, view_channel=False, reason="Shadowban: blocco della vista")
    except discord.HTTPException:
        logger.warning("Shadowban: blocco non messo sul canale %s (server %s).", canale.id, canale.guild.id)
        return False
    return True


async def blocca_canali(guild: discord.Guild, prep: Preparazione) -> tuple[int, int]:
    """
    Nega la vista al ruolo su ogni canale tranne i due dedicati. Al massimo 500 canali, a gruppi con una pausa;
    un canale che rifiuta non ferma gli altri. Restituisce (sistemati, falliti).
    """
    dedicati = {prep.canale_testo.id, prep.canale_vocale.id}
    da_fare = [c for c in guild.channels if c.id not in dedicati and not _ha_blocco(c, prep.ruolo)][:MAX_CANALI_BLOCCO]
    fatti = falliti = 0
    for inizio in range(0, len(da_fare), GRUPPO_BLOCCO):
        gruppo = da_fare[inizio : inizio + GRUPPO_BLOCCO]
        esiti = await asyncio.gather(*(_blocca_canale(c, prep.ruolo) for c in gruppo))
        fatti += sum(esiti)
        falliti += len(esiti) - sum(esiti)
        if inizio + GRUPPO_BLOCCO < len(da_fare):
            await asyncio.sleep(PAUSA_BLOCCO)
    return fatti, falliti


async def _sposta_nel_vocale(member: discord.Member, prep: Preparazione) -> None:
    """Chi è in un vocale finisce in quello dedicato (un errore qui non annulla lo shadowban)."""
    if getattr(getattr(member, "voice", None), "channel", None) is None:
        return
    try:
        await member.move_to(prep.canale_vocale, reason="Shadowban")
    except discord.HTTPException:
        logger.warning("Shadowban: spostamento in vocale non riuscito per %s.", member.id)


async def metti(member: discord.Member, motivo: str, moderatore_id: int, fine) -> EsitoShadowban:
    """
    Mette in shadowban. Lo stato con i ruoli tolti si scrive prima; se la persona era già dentro non si tocca
    niente (`gia`). Se Discord rifiuta, lo stato si cancella: nessun caso, nessun ruolo perso.
    """
    guild = member.guild
    mancanti = permessi_bot_mancanti(guild)
    if mancanti or not bersaglio_ammesso(member):
        return EsitoShadowban(False, permessi_mancanti=tuple(mancanti))
    prep = await prepara(guild)
    if prep is None:
        return EsitoShadowban(False)
    salvati = ruoli_da_salvare(member, prep.ruolo.id)
    if not await moderation_repo.prenota_shadowban(guild.id, member.id, salvati, fine, moderatore_id):
        return EsitoShadowban(False, gia=True)
    await blocca_canali(guild, prep)
    motivo = motivo[:512]
    non_tolti = False
    try:
        restano = [r for r in member.roles if r.managed and not r.is_default()]
        try:
            await member.edit(roles=restano + [prep.ruolo], reason=motivo)
        except discord.HTTPException:
            logger.warning("Shadowban: ruoli non tolti a %s, do solo il ruolo.", member.id)
            non_tolti = True
            await member.add_roles(prep.ruolo, reason=motivo)
    except discord.HTTPException:
        await moderation_repo.elimina_shadowban(guild.id, member.id)
        return EsitoShadowban(False)
    caso = await moderation_repo.create_case(
        guild.id, member.id, moderatore_id, CASO_SHADOWBAN, motivo,
        duration_seconds=None if fine is None else max(1, int((fine - discord.utils.utcnow()).total_seconds())),
    )
    await moderation_repo.collega_caso_shadowban(guild.id, member.id, caso)
    await _sposta_nel_vocale(member, prep)
    return EsitoShadowban(True, caso, ruoli_non_tolti=non_tolti, ruoli_salvati=tuple(salvati))


async def in_shadowban(guild_id: int, user_id: int) -> bool:
    """True se la persona ha uno shadowban in corso (usato da chi dà ruoli in automatico)."""
    return await moderation_repo.get_shadowban(guild_id, user_id) is not None


async def ruoli_negati(member: discord.Member) -> bool:
    """
    True se a questa persona non si danno ruoli in automatico o su sua richiesta (shadowban in corso). Se il
    database non risponde si lascia passare: un errore di lettura non deve bloccare ruoli a tutto il server.
    """
    try:
        return await in_shadowban(member.guild.id, member.id)
    except Exception:  # noqa: BLE001 - fallisce aperto, vedi docstring
        logger.debug("Shadowban: stato non letto per %s, ruoli non negati.", getattr(member, "id", None), exc_info=True)
        return False


async def add_roles_se_libero(member: discord.Member, *ruoli, reason: str | None = None, **kw) -> bool:
    """
    Come `member.add_roles`, ma non dà niente a chi è in shadowban (un ruolo che fa «vedere un canale» scavalcherebbe
    il blocco). Per i ruoli dati da automatismi o su richiesta dell'utente; le azioni dello staff usano `add_roles`.
    True se ha chiamato Discord, False se ha saltato.
    """
    if await ruoli_negati(member):
        return False
    await member.add_roles(*ruoli, reason=reason, **kw)
    return True


async def togli(guild: discord.Guild, member: discord.Member, motivo: str, chi_id: int) -> bool | None:
    """
    Toglie lo shadowban e ridà i ruoli salvati (solo quelli che il bot può ridare oggi). True se fatto, False se
    Discord rifiuta (lo stato resta, si può riprovare), None se il membro non era in shadowban.
    """
    from cogs.moderation._tempban_modes import ruoli_da_riprendere

    stato = await moderation_repo.get_shadowban(guild.id, member.id)
    if stato is None:
        return None
    cfg = await moderation_repo.get_shadowban_config(guild.id)
    ridati = ruoli_da_riprendere(guild, list(stato["ruoli"]))
    attuali = [r for r in member.roles if not r.is_default() and r.id != cfg["ruolo_id"]]
    try:
        await member.edit(roles=attuali + [r for r in ridati if r not in attuali], reason=motivo[:512])
    except discord.HTTPException:
        logger.warning("Shadowban non tolto a %s (server %s).", member.id, guild.id)
        return False
    if stato["case_number"] is not None:
        await moderation_repo.revoke_case(guild.id, stato["case_number"], chi_id)
    await moderation_repo.elimina_shadowban(guild.id, member.id)
    return True
