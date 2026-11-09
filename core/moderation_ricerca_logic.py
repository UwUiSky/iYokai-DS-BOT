"""
core/moderation_ricerca_logic.py
================================
Ricerche dello staff, senza Discord: ban per testo con cache di 5 minuti (MOD-107), membri per filtri con
esportazione CSV (MOD-108), codice di un invito (MOD-110).
Funzioni coperte: SPEC §5.3 (MOD-107, MOD-108, MOD-110)
Dipende da: google-re2 (le espressioni scritte dallo staff non possono bloccare il bot)
"""

from __future__ import annotations

import csv
import io
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.bounded_cache import BoundedCache

MAX_BAN_LETTI = 10_000
SECONDI_CACHE_BAN = 300
MAX_RISULTATI = 25
MAX_RIGHE_CSV = 50_000
MAX_BYTE_CSV = 9 * 1024 * 1024  # sotto i 10 MiB dei file di Discord
MAX_REGEX = 100
PREFISSO_REGEX = "re:"


@dataclass(frozen=True)
class VoceBan:
    user_id: int
    nome: str
    motivo: str | None


_cache_ban: BoundedCache[int, tuple[float, tuple[VoceBan, ...], bool]] = BoundedCache(200)


def svuota_cache() -> None:
    _cache_ban.clear()


async def leggi_ban(guild_id: int, iteratore, *, ora: float | None = None, forza: bool = False):
    """
    I ban del server come (voci, troncato). `iteratore` è un async iterator di ban (guild.bans()): si legge fino a
    MAX_BAN_LETTI voci e il risultato resta in cache 5 minuti. `forza` salta la cache.
    """
    adesso = time.monotonic() if ora is None else ora
    nota = _cache_ban.get(guild_id)
    if nota is not None and not forza and adesso - nota[0] < SECONDI_CACHE_BAN:
        return nota[1], nota[2]
    voci: list[VoceBan] = []
    troncato = False
    async for ban in iteratore:
        if len(voci) >= MAX_BAN_LETTI:
            troncato = True
            break
        voci.append(VoceBan(ban.user.id, ban.user.name, ban.reason))
    risultato = (adesso, tuple(voci), troncato)
    _cache_ban.set(guild_id, risultato)
    return risultato[1], troncato


def ban_in_cache(guild_id: int, ora: float | None = None):
    """I ban già letti di recente (anche senza il tetto di tempo per il completamento), o None."""
    nota = _cache_ban.get(guild_id)
    adesso = time.monotonic() if ora is None else ora
    return nota[1] if nota is not None and adesso - nota[0] < SECONDI_CACHE_BAN else None


def cerca_ban(voci, testo: str, massimo: int = MAX_RISULTATI) -> tuple[list[VoceBan], int]:
    """Le voci il cui nome, ID o motivo contengono `testo` (senza maiuscole): al più `massimo` e il totale."""
    ago = testo.strip().casefold()
    if not ago:
        return [], 0
    trovate = [v for v in voci if ago in v.nome.casefold() or ago == str(v.user_id) or ago in (v.motivo or "").casefold()]
    return trovate[:massimo], len(trovate)


def suggerimenti_unban(voci, current: str) -> list[VoceBan]:
    """Fino a 25 ban per il completamento di `unban user_id`: quelli che contengono quel che si scrive."""
    ago = current.strip().casefold()
    scelte = [v for v in voci if not ago or ago in v.nome.casefold() or str(v.user_id).startswith(ago)]
    return scelte[:MAX_RISULTATI]


def compila_nome(nome: str):
    """Il filtro sul nome: testo che contiene, oppure `re:<espressione>` (re2). ValueError se l'espressione non va."""
    nome = nome.strip()
    if nome.casefold().startswith(PREFISSO_REGEX):
        schema = nome[len(PREFISSO_REGEX):]
        if not schema or len(schema) > MAX_REGEX:
            raise ValueError(f"L'espressione va da 1 a {MAX_REGEX} caratteri.")
        import re2

        try:
            compilata = re2.compile("(?i)" + schema)
        except Exception as exc:  # re2.error non ha una base comune
            raise ValueError("L'espressione non è valida.") from exc
        return lambda testo: compilata.search(testo) is not None
    ago = nome.casefold()
    return lambda testo: ago in testo.casefold()


def filtra_membri(
    membri,
    *,
    nome: str | None = None,
    ruolo_id: int | None = None,
    in_vocale: bool | None = None,
    bot: bool | None = None,
    entrato_dopo: datetime | None = None,
    account_piu_giovane_di: timedelta | None = None,
    ora: datetime | None = None,
) -> list:
    """I membri che passano tutti i filtri dati (quelli vuoti non contano)."""
    ora = ora or datetime.now(timezone.utc)
    corrisponde = compila_nome(nome) if nome else None
    risultato = []
    for m in membri:
        if corrisponde and not any(corrisponde(t) for t in (m.name, m.display_name, getattr(m, "global_name", None) or "")):
            continue
        if ruolo_id is not None and ruolo_id not in {r.id for r in m.roles}:
            continue
        if in_vocale is not None and (m.voice is not None) != in_vocale:
            continue
        if bot is not None and m.bot != bot:
            continue
        if entrato_dopo is not None and (m.joined_at is None or m.joined_at < entrato_dopo):
            continue
        if account_piu_giovane_di is not None and ora - m.created_at > account_piu_giovane_di:
            continue
        risultato.append(m)
    return risultato


def _cella(valore) -> str:
    """Una cella CSV che un foglio di calcolo non esegue come formula."""
    testo = "" if valore is None else str(valore)
    return "'" + testo if testo[:1] in ("=", "+", "-", "@", "\t", "\r") else testo


def csv_membri(membri) -> tuple[bytes, int]:
    """Il CSV dei membri (tetto di righe e di byte) e quante righe ci sono."""
    out = io.StringIO()
    scrittore = csv.writer(out)
    scrittore.writerow(["id", "nome", "nome_visualizzato", "bot", "entrato_il", "account_creato_il", "ruoli"])
    righe = 0
    for m in membri[:MAX_RIGHE_CSV]:
        scrittore.writerow([
            m.id, _cella(m.name), _cella(m.display_name), int(bool(m.bot)),
            m.joined_at.isoformat() if m.joined_at else "", m.created_at.isoformat(), max(len(m.roles) - 1, 0),
        ])
        righe += 1
        if out.tell() > MAX_BYTE_CSV:
            break
    return out.getvalue().encode("utf-8"), righe


_CODICE_INVITO = re.compile(r"^[A-Za-z0-9-]{2,32}$")
_URL_INVITO = re.compile(r"(?:discord\.gg|discord(?:app)?\.com/invite)/([A-Za-z0-9-]{2,32})", re.IGNORECASE)


def codice_invito(testo: str) -> str | None:
    """Il codice da un invito scritto come codice o come link; None se non somiglia a un invito."""
    testo = testo.strip()
    trovato = _URL_INVITO.search(testo)
    if trovato:
        return trovato.group(1)
    return testo if _CODICE_INVITO.match(testo) else None
