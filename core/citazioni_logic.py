"""
core/citazioni_logic.py
=======================
Citazioni del server: limiti, lettura e scrittura del file JSON, testo da mostrare, e quali comandi contano come
«dello staff» per il registro. Nessun accesso a Discord né al database.
Funzioni coperte: catalogo #128 UTL-206, 207, 222, 229 (D69, B16)
"""

from __future__ import annotations

import json
import re

MAX_TESTO = 1000
MAX_PER_SERVER = 500
MAX_BYTE_IMPORT = 1024 * 1024
MAX_RISULTATI = 10
_RADICI_STAFF = ("admin-", "mod-")
_RADICI_STAFF_ESATTE = frozenset({"admin", "mod", "security", "log"})


class ImportCitazioniErrato(ValueError):
    """Il file non si può leggere: il testo dell'errore è per chi ha scritto il comando."""


def pulisci_testo(testo: str) -> str:
    return re.sub(r"[ \t]+\n", "\n", testo).strip()[:MAX_TESTO]


def e_comando_staff(percorso: str) -> bool:
    """Un comando dello staff sta in un gruppo `admin-…` o `mod-…` (o in un gruppo dello staff senza trattino)."""
    radice = percorso.split(" ", 1)[0]
    return radice.startswith(_RADICI_STAFF) or radice in _RADICI_STAFF_ESATTE


def righe_in_json(righe: list[dict]) -> bytes:
    pulite = [{"testo": r["testo"], "autore_id": r["autore_id"], "link": r["link"]} for r in righe]
    return json.dumps({"citazioni": pulite}, ensure_ascii=False, indent=1).encode("utf-8")


def leggi_importazione(dati: bytes, posti: int) -> list[dict]:
    """Legge un file esportato da `righe_in_json`. Salta le righe sbagliate; non va oltre i `posti` liberi."""
    if len(dati) > MAX_BYTE_IMPORT:
        raise ImportCitazioniErrato("file_grande")
    try:
        radice = json.loads(dati.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ImportCitazioniErrato("file_illeggibile") from None
    elenco = radice.get("citazioni") if isinstance(radice, dict) else None
    if not isinstance(elenco, list):
        raise ImportCitazioniErrato("file_illeggibile")
    letti: list[dict] = []
    for voce in elenco:
        if len(letti) >= posti:
            break
        if not isinstance(voce, dict) or not isinstance(voce.get("testo"), str):
            continue
        testo = pulisci_testo(voce["testo"])
        autore = voce.get("autore_id")
        link = voce.get("link")
        if not testo:
            continue
        letti.append({
            "testo": testo,
            "autore_id": autore if isinstance(autore, int) and 0 < autore < 2**63 else None,
            "link": link[:200] if isinstance(link, str) and link.startswith("https://discord.com/channels/") else None,
        })
    return letti


def riga_citazione(riga: dict) -> str:
    """«testo» — <@autore> (#numero). Va mandata con le menzioni spente."""
    autore = f" — <@{riga['autore_id']}>" if riga.get("autore_id") else ""
    return f"“{riga['testo']}”{autore} (#{riga['id']})"
