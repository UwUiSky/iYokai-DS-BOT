"""
core/moderation_dm.py
=====================
Un solo punto per il messaggio privato che l'utente riceve con una sanzione (M6): titolo, server, moderatore,
caso, durata e motivo. Lo usano i comandi di moderazione e l'AutoMod. Il server può nascondere il nome del
moderatore (`mod_anonimo`, MOD-050) e scrivere un testo suo per ogni azione con i segnaposto {server} {motivo}
{durata} {moderatore} (MOD-059). Log e casi tengono sempre il nome vero.
Funzioni coperte: SPEC §5.13 (MOD-050, MOD-059)
"""

from __future__ import annotations

import logging
import re

import discord

from core import moderation_opzioni
from core.i18n import testo_guild

logger = logging.getLogger("iyokai.moderation_dm")

MAX_TESTO_DM = 1500
MAX_DESCRIZIONE = 4096
MAX_CAMPO = 1024
_SEGNAPOSTO = re.compile(r"\{(server|motivo|durata|moderatore)\}")


def espandi(testo: str, valori: dict[str, str]) -> str:
    """Sostituisce {server} {motivo} {durata} {moderatore}; un segnaposto senza valore diventa vuoto."""
    return _SEGNAPOSTO.sub(lambda m: valori.get(m.group(1), ""), testo)


def durata_a_parole(secondi: int | None) -> str:
    """«1 ora», «3 giorni», «90 minuti»: per il testo del DM; vuoto se non c'è durata."""
    if not secondi:
        return ""
    for valore, singolare, plurale in ((86400, "giorno", "giorni"), (3600, "ora", "ore"), (60, "minuto", "minuti")):
        if secondi >= valore and secondi % valore == 0:
            numero = secondi // valore
            return f"{numero} {singolare if numero == 1 else plurale}"
    return f"{secondi} secondi"


async def costruisci(
    guild: discord.Guild,
    azione: str,
    *,
    titolo: str,
    colore: discord.Color,
    moderatore: discord.abc.User | None,
    motivo: str,
    caso: int | None = None,
    durata_s: int | None = None,
    extra: tuple[tuple[str, str], ...] = (),
) -> discord.Embed:
    """L'embed del DM per `azione`. `moderatore` None = l'AutoMod o il bot. Rispetta anonimato e testo del server."""
    try:
        opzioni = await moderation_opzioni.leggi(guild.id)
    except Exception:  # un database che non risponde non deve fermare un kick o un ban: DM di base, moderatore nascosto
        logger.warning("Opzioni del DM non lette per il server %s: messaggio di base.", guild.id, exc_info=True)
        opzioni = moderation_opzioni.OpzioniModerazione(anonimo=True)
    if opzioni.anonimo or moderatore is None:
        chi = await testo_guild(guild, "modm_staff_di", server=guild.name)
    else:
        chi = moderatore.mention
    durata = durata_a_parole(durata_s)
    embed = discord.Embed(title=titolo[:256], color=colore)
    personale = opzioni.dm_testi.get(azione)
    if personale:
        valori = {"server": guild.name, "motivo": motivo, "durata": durata, "moderatore": chi}
        embed.description = espandi(personale, valori)[:MAX_DESCRIZIONE]
    embed.add_field(name=await testo_guild(guild, "modm_server"), value=guild.name[:MAX_CAMPO], inline=True)
    embed.add_field(name=await testo_guild(guild, "modm_moderatore"), value=chi[:MAX_CAMPO], inline=True)
    if caso is not None:
        embed.add_field(name=await testo_guild(guild, "modm_caso"), value=f"#{caso}", inline=True)
    if durata:
        embed.add_field(name=await testo_guild(guild, "modm_durata"), value=durata, inline=True)
    for nome, valore in extra:
        embed.add_field(name=nome[:256], value=valore[:MAX_CAMPO], inline=False)
    embed.add_field(name=await testo_guild(guild, "modm_motivo"), value=(motivo or await testo_guild(guild, "modm_nessun_motivo"))[:MAX_CAMPO], inline=False)
    return embed
