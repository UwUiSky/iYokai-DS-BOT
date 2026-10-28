"""
core/automod_parole_opzioni.py
==============================
Impostazioni del filtro delle parole vietate (AMD-014), in un solo punto (D16):
lista di base accesa o spenta, parole proprie del server, parole lecite e
controllo dei nomi. Le liste stanno nelle impostazioni del server.
Funzioni coperte: SPEC §6 (AMD-014)
"""

from __future__ import annotations

from dataclasses import dataclass

from core.automod_parole_logic import (
    Filtro,
    Trovato,
    costruisci,
    costruisci_sospette,
    e_voce_di_base,
    pulisci_voce,
    trova,
)
from core.database import db as _db
from core.odio_libreria_service import libreria_odio

# Chiave della violazione nei filtri lato bot (azioni, log, etichette).
VIOLATION_PAROLE_VIETATE = "parole_vietate"

SETTING_BASE = "automod_parole_base"
SETTING_PROPRIE = "automod_parole_proprie"
SETTING_LECITE = "automod_parole_lecite"
SETTING_NICK = "automod_parole_nick"

MAX_VOCI = 100
MAX_LUNGHEZZA_VOCE = 60

LISTA_PROPRIE = "proprie"
LISTA_LECITE = "lecite"
_CHIAVI = {LISTA_PROPRIE: SETTING_PROPRIE, LISTA_LECITE: SETTING_LECITE}


@dataclass(frozen=True)
class OpzioniParole:
    base: bool = True
    proprie: tuple[str, ...] = ()
    lecite: tuple[str, ...] = ()
    nick: bool = True


def _voci(valore) -> tuple[str, ...]:
    if not isinstance(valore, list):
        return ()
    return tuple(v for v in valore if isinstance(v, str) and 0 < len(v) <= MAX_LUNGHEZZA_VOCE)[:MAX_VOCI]


async def leggi(guild_id: int, archivio=None) -> OpzioniParole:
    """`archivio`: chi legge le impostazioni (di base `db`)."""
    db = archivio or _db
    base = await db.get_guild_setting(guild_id, SETTING_BASE, True)
    nick = await db.get_guild_setting(guild_id, SETTING_NICK, True)
    return OpzioniParole(
        base=base if isinstance(base, bool) else True,
        proprie=_voci(await db.get_guild_setting(guild_id, SETTING_PROPRIE, [])),
        lecite=_voci(await db.get_guild_setting(guild_id, SETTING_LECITE, [])),
        nick=nick if isinstance(nick, bool) else True,
    )


async def filtro_del_server(guild_id: int, archivio=None) -> tuple[Filtro, OpzioniParole]:
    opzioni = await leggi(guild_id, archivio)
    globali = await libreria_odio.globali() if opzioni.base else ()  # D35: varianti approvate di tutti i server
    return costruisci(opzioni.base, (*opzioni.proprie, *globali), opzioni.lecite), opzioni


async def filtro_sospette(guild_id: int, archivio=None) -> tuple[Filtro, OpzioniParole]:
    """D35: filtro delle parole sospette (da giudicare con l'AI); con la lista di base spenta e' vuoto."""
    opzioni = await leggi(guild_id, archivio)
    if not opzioni.base:
        return costruisci(False), opzioni
    return costruisci_sospette(await libreria_odio.candidate(guild_id), opzioni.lecite), opzioni


async def imposta_base(guild_id: int, attiva: bool, conferma: bool, autore_id: int) -> None:
    """Spegnere la lista di base chiede la conferma esplicita."""
    if not attiva and not conferma:
        raise ValueError("Per spegnere la lista di base serve la conferma esplicita.")
    await _db.set_guild_setting(guild_id, SETTING_BASE, attiva, changed_by=autore_id)


async def imposta_nick(guild_id: int, attivo: bool, autore_id: int) -> None:
    await _db.set_guild_setting(guild_id, SETTING_NICK, attivo, changed_by=autore_id)


async def aggiungi_voce(guild_id: int, lista: str, voce: str, autore_id: int) -> bool:
    """True se aggiunta, False se c'era gia'. ValueError se la voce non va bene."""
    voce = voce.strip()
    if len(voce) > MAX_LUNGHEZZA_VOCE or pulisci_voce(voce) is None:
        raise ValueError("La voce deve avere almeno 3 lettere e al massimo 60 caratteri.")
    if lista == LISTA_LECITE and e_voce_di_base(voce):
        raise ValueError("È un insulto della lista di base: non può diventare lecito. Per spegnere la base usa `/automod odio base`.")
    attuali = list(getattr(await leggi(guild_id), lista))
    if voce.casefold() in (a.casefold() for a in attuali):
        return False
    if len(attuali) >= MAX_VOCI:
        raise ValueError(f"La lista è piena: al massimo {MAX_VOCI} voci.")
    attuali.append(voce)
    await _db.set_guild_setting(guild_id, _CHIAVI[lista], attuali, changed_by=autore_id)
    return True


async def rimuovi_voce(guild_id: int, lista: str, voce: str, autore_id: int) -> bool:
    attuali = list(getattr(await leggi(guild_id), lista))
    resto = [a for a in attuali if a.casefold() != voce.strip().casefold()]
    if len(resto) == len(attuali):
        return False
    await _db.set_guild_setting(guild_id, _CHIAVI[lista], resto, changed_by=autore_id)
    return True


async def trova_nel_testo(guild_id: int, testo: str, archivio=None) -> Trovato | None:
    """La voce vietata trovata nel testo (lista di base e liste del server), o None."""
    filtro, _ = await filtro_del_server(guild_id, archivio)
    return trova(testo, filtro)
