"""
core/giveaway_fine.py
=====================
Fine di un giveaway: annuncio dei vincitori (con il bottone «Riepilogo»), ruolo premio, messaggio privato
ai vincitori e riga nel canale di log. Lo usano il worker alla scadenza e il menu «Riestrai giveaway».
Funzioni coperte: SPEC §15.5 (NF-28), catalogo UTL-116, 120, 131, 132, 133
"""

from __future__ import annotations

import asyncio
import logging

import discord

from core.giveaway_logic import riempi
from core.i18n import t

logger = logging.getLogger("iyokai.giveaway_fine")

PAUSA_TRA_MESSAGGI_PRIVATI = 0.5  # secondi: i vincitori sono al massimo 50


def testo_annuncio(giveaway, vincitori: list[int], lingua: str, *, riestrazione: bool = False) -> str:
    """Il messaggio finale. Il premio è testo libero: i ping li decide `allowed_mentions` (solo i vincitori)."""
    if not vincitori:
        return t("giveaway_fine_nessuno", lingua, premio=giveaway.prize)
    menzioni = ", ".join(f"<@{uid}>" for uid in vincitori)
    if riestrazione:
        return t("giveaway_riestratto", lingua, menzioni=menzioni, premio=giveaway.prize)
    return t("giveaway_fine_vincitori", lingua, menzioni=menzioni, premio=giveaway.prize)


async def _membro(guild, user_id: int):
    membro = guild.get_member(user_id)
    if membro is not None:
        return membro
    try:
        return await guild.fetch_member(user_id)
    except discord.HTTPException:
        return None


async def dai_ruolo_premio(guild, giveaway, vincitori: list[int]) -> tuple[int, int]:
    """Dà il ruolo premio ai vincitori. Ritorna (riusciti, falliti); il ruolo che non c'è più non è un errore."""
    if giveaway.ruolo_premio is None or not vincitori:
        return 0, 0
    ruolo = guild.get_role(giveaway.ruolo_premio)
    if ruolo is None:
        return 0, len(vincitori)
    riusciti = falliti = 0
    for uid in vincitori:
        membro = await _membro(guild, uid)
        try:
            if membro is None:
                raise discord.NotFound(_RispostaFinta(), "membro uscito")
            await membro.add_roles(ruolo, reason=f"Premio del giveaway {giveaway.id}")
            riusciti += 1
        except discord.HTTPException:
            falliti += 1
    return riusciti, falliti


class _RispostaFinta:
    status = 404
    reason = "membro uscito"


async def avvisa_vincitori(guild, giveaway, vincitori: list[int], testo_admin: str | None, lingua: str) -> int:
    """Messaggio privato ai vincitori (solo se il server ha scritto il testo). Ritorna quanti l'hanno ricevuto."""
    if not testo_admin or not vincitori:
        return 0
    testo = riempi(testo_admin, premio=giveaway.prize, server=getattr(guild, "name", ""))[:1000]
    inviati = 0
    for uid in vincitori:
        membro = await _membro(guild, uid)
        if membro is not None:
            try:
                await membro.send(testo, allowed_mentions=discord.AllowedMentions.none())
                inviati += 1
            except discord.HTTPException:
                pass  # messaggi privati chiusi: non è un errore
        await asyncio.sleep(PAUSA_TRA_MESSAGGI_PRIVATI)
    return inviati


async def scrivi_nel_log(guild, canale_log_id: int | None, giveaway, vincitori: list[int], lingua: str,
                         *, premio_dato: tuple[int, int], riestrazione: bool) -> None:
    if canale_log_id is None:
        return
    canale = guild.get_channel(canale_log_id)
    if not isinstance(canale, discord.abc.Messageable):
        return
    righe = [
        t("giveaway_log_vincitori", lingua, vincitori=", ".join(f"<@{u}>" for u in vincitori) or "-"),
    ]
    if giveaway.ruolo_premio is not None:
        righe.append(t("giveaway_log_ruolo", lingua, riusciti=premio_dato[0], falliti=premio_dato[1]))
    embed = discord.Embed(
        title=t("giveaway_log_titolo_riestrazione" if riestrazione else "giveaway_log_titolo", lingua, id=giveaway.id),
        description=f"**{giveaway.prize[:200]}**\n" + "\n".join(righe), color=0x5865F2,
    )
    try:
        await canale.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        logger.warning("Giveaway %s: log nel canale %s non scritto", giveaway.id, canale_log_id)


async def concludi(
    canale, guild, giveaway, vincitori: list[int], opzioni, lingua: str, *, vista=None, riestrazione: bool = False
) -> None:
    """Annuncia i vincitori e poi fa il resto (ruolo, messaggi privati, log). Ogni passo che fallisce non ferma gli altri."""
    try:
        # Si avvisano solo i vincitori: il premio è testo libero (@everyone, ruoli).
        await canale.send(
            testo_annuncio(giveaway, vincitori, lingua, riestrazione=riestrazione),
            allowed_mentions=discord.AllowedMentions(
                users=[discord.Object(id=uid) for uid in vincitori], roles=False, everyone=False
            ),
            **({"view": vista} if vista is not None else {}),
        )
    except discord.HTTPException:
        logger.warning(
            "Impossibile annunciare la fine del giveaway %s nel canale %s.", giveaway.id, giveaway.channel_id
        )
    if guild is None or not hasattr(guild, "get_role"):
        return
    premio = await dai_ruolo_premio(guild, giveaway, vincitori)
    await avvisa_vincitori(guild, giveaway, vincitori, opzioni.msg_dm, lingua)
    await scrivi_nel_log(guild, opzioni.canale_log, giveaway, vincitori, lingua, premio_dato=premio, riestrazione=riestrazione)
