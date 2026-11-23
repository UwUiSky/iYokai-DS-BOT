"""
core/everyone_programmati.py
============================
Messaggi programmati con @everyone o @here (UTL-110, D124). Possono usarli solo il proprietario del server o chi ha
«Menziona @everyone». Il permesso si rilegge AL MOMENTO DELL'INVIO (non solo alla creazione): se chi ha programmato
l'ha perso, il messaggio parte senza la menzione. Ogni server ha un tetto di invii con menzione al giorno
(limite `everyone_al_giorno`, per livello). `allowed_mentions` ha `everyone=True` solo quando tutte le regole passano.
Funzioni coperte: UTL-110
Dipende da: core/migrations/0912_everyone_programmati.sql, core/piani.py
"""

from __future__ import annotations

import enum
import re
from datetime import datetime, timezone

import discord

_MENZIONE = re.compile(r"@(everyone|here)\b")


class Esito(enum.Enum):
    NESSUNA_MENZIONE = "nessuna_menzione"  # il testo non ha @everyone né @here
    AMMESSA = "ammessa"
    SENZA_PERMESSO = "senza_permesso"  # chi ha programmato non può più (o non ha mai potuto)
    TETTO_RAGGIUNTO = "tetto_raggiunto"  # troppi invii oggi in questo server


def contiene_menzione_di_massa(testo: str) -> bool:
    return bool(_MENZIONE.search(testo or ""))


def puo_usare_everyone(guild, user_id: int) -> bool:
    """Proprietario del server, o membro con «Menziona @everyone» (o amministratore), riletto adesso dalla cache."""
    if guild is None or not user_id:
        return False
    if guild.owner_id == user_id:
        return True
    membro = guild.get_member(user_id)
    if membro is None:
        return False
    permessi = membro.guild_permissions
    return bool(permessi.administrator or permessi.mention_everyone)


async def _prenota(guild_id: int, massimo: int) -> bool:
    """Conta un invio di oggi se c'è posto (atomico: una riga, un solo UPDATE condizionato)."""
    from core.database import db

    giorno = datetime.now(timezone.utc).date()
    riga = await db.pool.fetchval(
        """
        INSERT INTO everyone_invii (guild_id, giorno, conteggio) VALUES ($1, $2, 1)
        ON CONFLICT (guild_id, giorno) DO UPDATE SET conteggio = everyone_invii.conteggio + 1
            WHERE everyone_invii.conteggio < $3
        RETURNING conteggio
        """,
        guild_id, giorno, massimo,
    ) if massimo > 0 else None
    return riga is not None


async def restituisci(guild_id: int) -> None:
    """Se l'invio è fallito dopo la prenotazione, il posto torna libero."""
    from core.database import db

    await db.pool.execute(
        "UPDATE everyone_invii SET conteggio = GREATEST(conteggio - 1, 0) WHERE guild_id = $1 AND giorno = $2",
        guild_id, datetime.now(timezone.utc).date(),
    )


async def decidi(guild, user_id: int, testo: str, bot=None) -> Esito:
    """
    Al momento dell'invio: la menzione di massa è ammessa? Se sì, il posto di oggi è già prenotato (da restituire
    con `restituisci` se poi l'invio fallisce).
    """
    if not contiene_menzione_di_massa(testo):
        return Esito.NESSUNA_MENZIONE
    if not puo_usare_everyone(guild, user_id):
        return Esito.SENZA_PERMESSO
    from core import piani

    massimo = await piani.limite_server_sicuro(guild.id, "everyone_al_giorno", bot)
    return Esito.AMMESSA if await _prenota(guild.id, massimo) else Esito.TETTO_RAGGIUNTO


def menzioni(ping_ruoli: bool, esito: Esito) -> discord.AllowedMentions:
    """everyone=True solo se l'esito è AMMESSA; i ruoli come prima (D12)."""
    return discord.AllowedMentions(
        everyone=esito is Esito.AMMESSA, roles=bool(ping_ruoli), users=True, replied_user=False
    )


def testo_senza_menzione(testo: str) -> str:
    """Se la menzione non è ammessa, il testo parte lo stesso ma @everyone e @here diventano testo inerte."""
    return _MENZIONE.sub(lambda m: "@​" + m.group(1), testo or "")
