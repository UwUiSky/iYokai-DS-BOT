"""
core/json_log_formatter.py
=============================
Formatter JSON per il logging strutturato (SPEC.md §1.7). Nessuna
nuova dipendenza: `logging.Formatter` è di libreria standard, qui
c'è solo un `format()` che produce una riga JSON invece di testo
libero — pensato per essere interrogabile da strumenti (grep su un
campo, un futuro dashboard di log) invece che solo leggibile a occhio.

Il file di log SCRITTO su disco usa questo formatter; l'output su
stdout (che `systemd`/`journalctl` cattura comunque) resta nel
formato testuale leggibile precedente — le due cose convivono, non
si sostituiscono a vicenda (vedi main.py, setup_logging()).
"""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """
    Una riga JSON per ogni record di log, con i campi essenziali:
    timestamp (UTC, ISO 8601), livello, nome del logger, messaggio
    già interpolato (non la stringa grezza con i placeholder %s), e
    — se presente — il traceback completo dell'eccezione.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exception"] = "".join(
                traceback.format_exception(*record.exc_info)
            )

        return json.dumps(payload, ensure_ascii=False)
