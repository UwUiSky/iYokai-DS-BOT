"""
core/config_history_logic.py
============================
Storico delle modifiche alla configurazione: filtri, vista «prima / dopo» e CSV (CFG-004, CFG-005, #122).
Logica pura, provabile senza Discord. La lettura con i filtri è `db.get_config_history_filtrato`.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone

TIPI_MODIFICA = ("module", "setting", "reset", "import")
MAX_RIGHE_CSV = 5000
_FORMATI_DATA = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")
_INIZIO_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def leggi_data(testo: str | None) -> datetime | None:
    """«2026-10-14» o «14/10/2026» (mezzanotte UTC). None per vuoto o non valida."""
    if not testo or not testo.strip():
        return None
    for formato in _FORMATI_DATA:
        try:
            return datetime.strptime(testo.strip(), formato).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def fine_giornata(giorno: datetime) -> datetime:
    """Il filtro «fino al» include tutto quel giorno."""
    return giorno + timedelta(days=1)


def _cella_sicura(valore: object) -> str:
    """Un valore scelto dagli utenti non deve diventare una formula in un foglio di calcolo."""
    testo = "" if valore is None else str(valore)
    return "'" + testo if testo.startswith(_INIZIO_FORMULA) else testo


def _json(valore: object) -> str:
    return json.dumps(valore, ensure_ascii=False, sort_keys=True, default=str)


def csv_storico(voci) -> bytes:
    """CSV (UTF-8 con BOM, per Excel) con al massimo `MAX_RIGHE_CSV` righe, dalla più recente."""
    uscita = io.StringIO()
    scrittore = csv.writer(uscita, lineterminator="\n")
    scrittore.writerow(["id", "data_utc", "autore", "tipo", "chiave", "prima", "dopo"])
    for voce in list(voci)[:MAX_RIGHE_CSV]:
        scrittore.writerow(
            [
                voce.id,
                voce.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                voce.changed_by or "",
                voce.change_type,
                _cella_sicura(voce.key_name),
                _cella_sicura(_json(voce.old_value)),
                _cella_sicura(_json(voce.new_value)),
            ]
        )
    return b"\xef\xbb\xbf" + uscita.getvalue().encode("utf-8")


def dettaglio_prima_dopo(voce, massimo: int = 900) -> str:
    """La vista «prima / dopo» di una voce, in due blocchi di codice sotto il limite di Discord."""

    def blocco(valore: object) -> str:
        testo = _json(valore).replace("```", "'''")
        return "```json\n" + (testo if len(testo) <= massimo else testo[: massimo - 1] + "…") + "\n```"

    autore = f"<@{voce.changed_by}>" if voce.changed_by else "sconosciuto"
    return (
        f"**#{voce.id}** · {voce.change_type} · `{voce.key_name[:100]}` · {autore} · "
        f"<t:{int(voce.created_at.timestamp())}:f>\n**Prima**\n{blocco(voce.old_value)}\n**Dopo**\n{blocco(voce.new_value)}"
    )
