"""
core/turni_logic.py
===================
Turni dei giochi per `/web turni` (#131, D70, B11): le rotazioni di Splatoon 3 (da splatoon3.ink, `safe_get`,
cache comune di 15 minuti) e i reset settimanali di World of Warcraft (calcolati, nessuna rete). Splatoon 2 non c'è:
la fonte non ha dati recenti. I tempi sono numeri epoch, mostrati come orari di Discord (ognuno nel suo fuso).
Funzioni coperte: SPEC §16 (FUN-071)
Dipende da: core/safe_http.py, core/repositories/cache_esterna_repo.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

URL_SPLATOON3 = "https://splatoon3.ink/data/schedules.json"
MAX_BYTE = 400_000
SECONDI_CACHE = 15 * 60
TURNI_PER_MODO = 2
GIOCHI = ("splatoon3", "wow")
# Reset settimanali di WoW: giorno della settimana (lunedì = 0) e ora UTC. Stati Uniti: martedì 15:00 UTC; Europa: mercoledì 04:00 UTC.
RESET_WOW = {"us": (1, 15), "eu": (2, 4)}


def _epoch(valore: object) -> int | None:
    if not isinstance(valore, str):
        return None
    try:
        return int(datetime.fromisoformat(valore.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _nome(valore: object, massimo: int = 60) -> str:
    return valore.strip()[:massimo] if isinstance(valore, str) else ""


def _turno(nodo: dict, impostazione: dict | None, adesso: int) -> dict | None:
    inizio, fine = _epoch(nodo.get("startTime")), _epoch(nodo.get("endTime"))
    if inizio is None or fine is None or fine <= adesso or not isinstance(impostazione, dict):
        return None
    mappe = [_nome(s.get("name")) for s in impostazione.get("vsStages") or [] if isinstance(s, dict)]
    regola = impostazione.get("vsRule") if isinstance(impostazione.get("vsRule"), dict) else {}
    if not mappe or not _nome(regola.get("name")):
        return None
    return {"inizio": inizio, "fine": fine, "regola": _nome(regola.get("name")), "mappe": [m for m in mappe if m][:3]}


def _nodi(dati: dict, chiave: str) -> list[dict]:
    blocco = dati.get(chiave)
    nodi = blocco.get("nodes") if isinstance(blocco, dict) else None
    return [n for n in nodi if isinstance(n, dict)] if isinstance(nodi, list) else []


def interpreta_splatoon(testo: str | None, adesso: int) -> dict | None:
    """{"modi": [{"id", "turni": [...]}], "salmon": [...]} con i prossimi turni; None se la risposta non è quella attesa."""
    try:
        dati = (json.loads(testo or "").get("data"))
    except (ValueError, AttributeError):
        return None
    if not isinstance(dati, dict):
        return None
    modi: dict[str, list[dict]] = {"regular": [], "serie": [], "open": [], "x": []}
    for nodo in _nodi(dati, "regularSchedules"):
        if (t := _turno(nodo, nodo.get("regularMatchSetting"), adesso)):
            modi["regular"].append(t)
    for nodo in _nodi(dati, "bankaraSchedules"):
        for imp in nodo.get("bankaraMatchSettings") or []:
            if isinstance(imp, dict) and (t := _turno(nodo, imp, adesso)):
                modi["serie" if imp.get("bankaraMode") == "CHALLENGE" else "open"].append(t)
    for nodo in _nodi(dati, "xSchedules"):
        if (t := _turno(nodo, nodo.get("xMatchSetting"), adesso)):
            modi["x"].append(t)
    salmon: list[dict] = []
    gruppo = dati.get("coopGroupingSchedule") if isinstance(dati.get("coopGroupingSchedule"), dict) else {}
    for nodo in _nodi(gruppo, "regularSchedules"):
        inizio, fine = _epoch(nodo.get("startTime")), _epoch(nodo.get("endTime"))
        imp = nodo.get("setting") if isinstance(nodo.get("setting"), dict) else {}
        mappa = _nome((imp.get("coopStage") or {}).get("name")) if isinstance(imp.get("coopStage"), dict) else ""
        if inizio is None or fine is None or fine <= adesso or not mappa:
            continue
        armi = [_nome(a.get("name")) for a in imp.get("weapons") or [] if isinstance(a, dict)]
        boss = _nome((imp.get("boss") or {}).get("name")) if isinstance(imp.get("boss"), dict) else ""
        salmon.append({"inizio": inizio, "fine": fine, "mappa": mappa, "boss": boss, "armi": [a for a in armi if a][:4]})
    risultato = {"modi": [{"id": k, "turni": v[:TURNI_PER_MODO]} for k, v in modi.items() if v], "salmon": salmon[:TURNI_PER_MODO]}
    return risultato if risultato["modi"] or risultato["salmon"] else None


def prossimo_reset(adesso: datetime, giorno: int, ora_utc: int) -> int:
    """L'epoch del prossimo reset settimanale (giorno: lunedì = 0). Se è questo istante esatto, il reset è fra 7 giorni."""
    adesso = adesso.astimezone(timezone.utc)
    candidato = (adesso + timedelta(days=(giorno - adesso.weekday()) % 7)).replace(hour=ora_utc, minute=0, second=0, microsecond=0)
    if candidato <= adesso:
        candidato += timedelta(days=7)
    return int(candidato.timestamp())


def reset_wow(adesso: datetime) -> dict[str, int]:
    return {zona: prossimo_reset(adesso, g, o) for zona, (g, o) in RESET_WOW.items()}


async def splatoon3(cache, adesso: int, scarica=None) -> dict | None:
    """I turni di Splatoon 3, dalla cache comune o dalla fonte; None se la fonte non risponde bene."""
    salvato = await cache.leggi("turni:splatoon3")
    if salvato is not None and (
        any(t["fine"] > adesso for m in salvato.get("modi", []) for t in m["turni"])
        or any(t["fine"] > adesso for t in salvato.get("salmon", []))
    ):
        return salvato
    if scarica is None:
        from core.safe_http import safe_get

        async def scarica(url: str) -> str | None:
            return await safe_get(url, max_bytes=MAX_BYTE)

    dati = interpreta_splatoon(await scarica(URL_SPLATOON3), adesso)
    if dati is not None:
        await cache.salva("turni:splatoon3", dati, SECONDI_CACHE)
    return dati
