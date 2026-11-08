"""
core/moderation_motivi.py
=========================
Motivi pronti di moderazione: il server ne tiene fino a 25 (nome fino a 32 caratteri, testo fino a 512) e li
richiama dal completamento del campo «motivo». Il valore scelto è `#m<id>`; il testo vero si legge dal database.
Una piccola cache per server (3 secondi) evita una query a ogni tasto premuto.
Funzioni coperte: SPEC §5.9 (MOD-113, MOD-116)
"""

from __future__ import annotations

import re
import time

from core.repositories.moderation_repo import moderation_repo

MAX_MOTIVI = 25
MAX_NOME = 32
MIN_TESTO = 3
MAX_TESTO = 512
SECONDI_CACHE = 3
_VALORE = re.compile(r"^#m([1-9][0-9]{0,17})$")

_cache: dict[int, tuple[float, list[dict]]] = {}


def id_da_valore(valore: str) -> int | None:
    """L'id di un motivo pronto da un valore `#m<id>`; None se il testo è un motivo scritto a mano."""
    trovato = _VALORE.match(valore.strip()) if valore else None
    return int(trovato.group(1)) if trovato else None


def etichetta(motivo: dict) -> str:
    """Nome e inizio del testo, al massimo 100 caratteri (limite del completamento di Discord)."""
    return f"{motivo['nome']}: {motivo['testo']}"[:100]


def suggerimenti(elenco: list[dict], scritto: str) -> list[tuple[str, str]]:
    """(nome, valore) dei motivi che contengono `scritto` nel nome o nel testo; al massimo 25."""
    cerca = scritto.strip().casefold()
    righe = [m for m in elenco if not cerca or cerca in m["nome"].casefold() or cerca in m["testo"].casefold()]
    return [(etichetta(m), f"#m{m['id']}") for m in righe[:MAX_MOTIVI]]


async def elenco(guild_id: int) -> list[dict]:
    adesso = time.monotonic()
    voce = _cache.get(guild_id)
    if voce is not None and adesso - voce[0] < SECONDI_CACHE:
        return voce[1]
    righe = await moderation_repo.list_motivi(guild_id)
    _cache[guild_id] = (adesso, righe)
    return righe


async def aggiungi(guild_id: int, nome: str, testo: str, autore_id: int) -> int:
    """Aggiunge un motivo pronto e ne dà l'id. ValueError (codice) se qualcosa non va."""
    nome, testo = nome.strip(), testo.strip()
    if not 1 <= len(nome) <= MAX_NOME:
        raise ValueError("nome")
    if not MIN_TESTO <= len(testo) <= MAX_TESTO:
        raise ValueError("testo")
    if await moderation_repo.count_motivi(guild_id) >= MAX_MOTIVI:
        raise ValueError("tetto")
    nuovo = await moderation_repo.add_motivo(guild_id, nome, testo, autore_id)
    if nuovo is None:
        raise ValueError("doppio")
    _cache.pop(guild_id, None)
    return nuovo


async def togli(guild_id: int, nome: str) -> bool:
    tolto = await moderation_repo.delete_motivo(guild_id, nome.strip())
    _cache.pop(guild_id, None)
    return tolto


async def espandi(guild_id: int, valore: str) -> str:
    """Se `valore` è un motivo pronto (`#m<id>`) dà il suo testo, altrimenti lo stesso valore."""
    motivo_id = id_da_valore(valore)
    if motivo_id is None:
        return valore
    for m in await elenco(guild_id):
        if m["id"] == motivo_id:
            return m["testo"]
    return valore
