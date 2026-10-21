"""
core/moderation_opzioni.py
==========================
Opzioni di moderazione del server, in un solo punto (D16): giorni di
messaggi cancellati al ban, durata predefinita del timeout, DM per tipo
di azione e ruoli immuni alla moderazione manuale.
Funzioni coperte: SPEC §5.13 (MOD-010, MOD-017, MOD-057, MOD-068)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.database import db

SETTING_GIORNI_BAN = "mod_ban_giorni_messaggi"
SETTING_DURATA_TIMEOUT = "mod_timeout_predefinito"
SETTING_DM_SPENTI = "mod_dm_spenti"
SETTING_RUOLI_IMMUNI = "mod_ruoli_immuni"

# Azioni che mandano un DM all'utente; per ognuna il server può spegnerlo.
AZIONI_CON_DM = ("warn", "kick", "ban", "tempban", "softban", "timeout", "mute")

MAX_RUOLI_IMMUNI = 25
# Timeout di Discord: da 1 minuto a 28 giorni.
MIN_TIMEOUT = 60
MAX_TIMEOUT = 28 * 86400


@dataclass(frozen=True)
class OpzioniModerazione:
    giorni_ban: int = 0
    durata_timeout: int | None = None
    dm_spenti: frozenset[str] = field(default_factory=frozenset)
    ruoli_immuni: tuple[int, ...] = ()


async def leggi(guild_id: int) -> OpzioniModerazione:
    giorni = await db.get_guild_setting(guild_id, SETTING_GIORNI_BAN, 0)
    durata = await db.get_guild_setting(guild_id, SETTING_DURATA_TIMEOUT)
    spenti = await db.get_guild_setting(guild_id, SETTING_DM_SPENTI, [])
    immuni = await db.get_guild_setting(guild_id, SETTING_RUOLI_IMMUNI, [])
    return OpzioniModerazione(
        giorni_ban=int(giorni) if isinstance(giorni, int) and 0 <= giorni <= 7 else 0,
        durata_timeout=durata if isinstance(durata, int) and MIN_TIMEOUT <= durata <= MAX_TIMEOUT else None,
        dm_spenti=frozenset(a for a in spenti if a in AZIONI_CON_DM),
        ruoli_immuni=tuple(r for r in immuni if isinstance(r, int)),
    )


async def imposta_giorni_ban(guild_id: int, giorni: int, autore_id: int) -> None:
    if not 0 <= giorni <= 7:
        raise ValueError("I giorni vanno da 0 a 7.")
    await db.set_guild_setting(guild_id, SETTING_GIORNI_BAN, giorni, changed_by=autore_id)


async def imposta_durata_timeout(guild_id: int, secondi: int | None, autore_id: int) -> None:
    """None toglie la durata predefinita."""
    if secondi is not None and not MIN_TIMEOUT <= secondi <= MAX_TIMEOUT:
        raise ValueError("La durata va da 1 minuto a 28 giorni.")
    await db.set_guild_setting(guild_id, SETTING_DURATA_TIMEOUT, secondi, changed_by=autore_id)


async def imposta_dm(guild_id: int, azione: str, attivo: bool, autore_id: int) -> None:
    if azione not in AZIONI_CON_DM:
        raise ValueError(f"Azione sconosciuta: {azione}")
    spenti = set((await leggi(guild_id)).dm_spenti)
    if attivo:
        spenti.discard(azione)
    else:
        spenti.add(azione)
    await db.set_guild_setting(
        guild_id, SETTING_DM_SPENTI, sorted(spenti), changed_by=autore_id
    )


async def dm_attivo(guild_id: int, azione: str) -> bool:
    return azione not in (await leggi(guild_id)).dm_spenti


async def cambia_ruolo_immune(guild_id: int, ruolo_id: int, aggiungi: bool, autore_id: int) -> str | None:
    """Aggiunge o toglie un ruolo immune. Restituisce l'errore da mostrare, o None."""
    immuni = list((await leggi(guild_id)).ruoli_immuni)
    if aggiungi:
        if ruolo_id in immuni:
            return "Il ruolo è già immune."
        if len(immuni) >= MAX_RUOLI_IMMUNI:
            return f"Al massimo {MAX_RUOLI_IMMUNI} ruoli immuni."
        immuni.append(ruolo_id)
    else:
        if ruolo_id not in immuni:
            return "Il ruolo non è tra gli immuni."
        immuni.remove(ruolo_id)
    await db.set_guild_setting(guild_id, SETTING_RUOLI_IMMUNI, immuni, changed_by=autore_id)
    return None


def motivo_immune(ruoli_immuni, ruoli_bersaglio, *, attore_proprietario: bool) -> str | None:
    """
    MOD-068: chi ha un ruolo immune non si modera a mano. Il proprietario
    del server resta libero (può sempre togliere il ruolo). None = si può.
    """
    if attore_proprietario or not ruoli_immuni:
        return None
    if set(ruoli_immuni) & set(ruoli_bersaglio):
        return "Ha un ruolo immune alla moderazione (lo decide il proprietario del server)."
    return None
