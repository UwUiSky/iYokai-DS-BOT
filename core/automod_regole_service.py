"""
core/automod_regole_service.py
==============================
Punto unico (D16) per leggere e scrivere le regole AutoMod: usato dai comandi, dal pannello e dal futuro sito.
Tiene in cache le regole di ogni server (invalidata a ogni salvataggio) e controlla i tetti.
Funzioni coperte: SPEC §6 (AMD-029..061, AMD-067), D63
"""

from __future__ import annotations

import logging
from dataclasses import replace

from core.automod_regole_logic import (
    MAX_REGOLE_PERSONALI,
    MAX_REGOLE_PERSONALI_PREMIUM,
    Azione,
    Regola,
    RegolaNonValida,
    azioni_dai_nomi_vecchi,
    regola_da_json,
    regola_a_json,
)
from core.bounded_cache import BoundedCache
from core.repositories.automod_regole_repo import automod_regole_repo

logger = logging.getLogger(__name__)

_cache: BoundedCache[int, tuple[Regola, ...]] = BoundedCache(2000)


def svuota_cache(guild_id: int | None = None) -> None:
    if guild_id is None:
        _cache.clear()
    else:
        _cache.delete(guild_id)


async def regole_del_server(guild_id: int) -> tuple[Regola, ...]:
    trovate = _cache.get(guild_id)
    if trovate is None:
        try:
            trovate = tuple(await automod_regole_repo.elenca(guild_id))
        except Exception:  # i filtri di base devono girare anche se la tabella delle regole ha un problema
            logger.exception("AutoMod: regole del server %s non leggibili, uso le impostazioni di base.", guild_id)
            return ()
        _cache.set(guild_id, trovate)
    return trovate


async def regola_effettiva(guild_id: int, chiave: str, azioni_di_prima: tuple[Azione, ...] = ()) -> Regola:
    """La riga del server, o la regola di base di un filtro (con le azioni di partenza date dal chiamante)."""
    for r in await regole_del_server(guild_id):
        if r.chiave == chiave:
            return r
    return Regola(chiave=chiave, tipo="filtro", nome=chiave[:32], guild_id=guild_id, azioni=azioni_di_prima)


async def azioni_del_filtro(
    guild_id: int, chiave: str, nomi_di_partenza: tuple[str, ...], mute_secondi: int
) -> tuple[Azione, ...]:
    """Azioni di un filtro: la riga se esiste, altrimenti quelle di partenza (con la durata di mute del server)."""
    for r in await regole_del_server(guild_id):
        if r.chiave == chiave:
            return r.azioni
    return azioni_dai_nomi_vecchi(nomi_di_partenza, mute_secondi)


async def salva(guild_id: int, regola: Regola, autore_id: int | None, *, premium: bool = False) -> Regola:
    """Controlla (rilegge dal JSON: stessi tetti di sempre), poi scrive. Una regola personale nuova prende il suo numero."""
    pulita = regola_da_json({**regola_a_json(regola), "id": regola.id, "guild_id": guild_id})
    esistente = next((r for r in await regole_del_server(guild_id) if r.chiave == pulita.chiave), None)
    nuovo_id = None
    if pulita.tipo == "personale":
        if esistente is None:
            tetto = MAX_REGOLE_PERSONALI_PREMIUM if premium else MAX_REGOLE_PERSONALI
            if await automod_regole_repo.conta_personali(guild_id) >= tetto:
                raise RegolaNonValida(f"al massimo {tetto} regole personali per server")
    await automod_regole_repo.salva(guild_id, pulita, autore_id, nuovo_id)
    svuota_cache(guild_id)
    return replace(pulita, guild_id=guild_id)


async def crea_personale(guild_id: int, regola: Regola, autore_id: int | None, *, premium: bool = False) -> Regola:
    """Una regola personale nuova: la chiave `p:<id>` si assegna qui."""
    numero = await automod_regole_repo.prossimo_id()
    nuova = replace(regola, chiave=f"p:{numero}", tipo="personale")
    pulita = regola_da_json({**regola_a_json(nuova), "guild_id": guild_id})
    tetto = MAX_REGOLE_PERSONALI_PREMIUM if premium else MAX_REGOLE_PERSONALI
    if await automod_regole_repo.conta_personali(guild_id) >= tetto:
        raise RegolaNonValida(f"al massimo {tetto} regole personali per server")
    await automod_regole_repo.salva(guild_id, pulita, autore_id, numero)
    svuota_cache(guild_id)
    return pulita


async def elimina(guild_id: int, chiave: str) -> bool:
    fatto = await automod_regole_repo.elimina(guild_id, chiave)
    svuota_cache(guild_id)
    return fatto


async def attiva_gruppo(guild_id: int, gruppo: str, attiva: bool) -> int:
    """Accende o spegne tutte le regole del gruppo (AMD-067). Restituisce quante ne ha cambiate."""
    cambiate = await automod_regole_repo.imposta_gruppo(guild_id, gruppo, attiva)
    svuota_cache(guild_id)
    return cambiate


async def imposta_azioni_filtro(
    guild_id: int, chiave: str, nomi: tuple[str, ...], mute_secondi: int, autore_id: int | None
) -> Regola:
    """`actions-set`: scrive le azioni di un filtro con i nomi di prima (delete, warn, mute, kick, ban)."""
    base = await regola_effettiva(guild_id, chiave)
    return await salva(guild_id, replace(base, tipo="filtro", azioni=azioni_dai_nomi_vecchi(nomi, mute_secondi)), autore_id)


async def cambia_durata_mute(guild_id: int, vecchio: int, nuovo: int) -> None:
    """`mute-duration`: i timeout uguali al valore di prima seguono il nuovo; quelli scelti a mano restano."""
    await automod_regole_repo.cambia_timeout(guild_id, vecchio, nuovo)
    svuota_cache(guild_id)


async def livello_di(guild_id: int, user_id: int) -> int:
    """Il livello di chi scrive (0 se non ha ancora livello). Si chiama solo se una regola lo chiede."""
    return await automod_regole_repo.livello_di(guild_id, user_id) or 0
