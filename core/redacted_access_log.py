"""
core/redacted_access_log.py
================================
AccessLogger di aiohttp che non scrive mai un segreto nei log dei
server web (SEC-9): il token di un webhook custom
(POST /webhook/<token>) e la query string del callback OAuth2 del
restore (?code=...&state=...) — l'access log di default di aiohttp
scrive il percorso E la query per intero.
Funzioni coperte: SPEC §10.8, §11.11 (SEC-9)
Dipende da: usato da core/custom_webhook_server.py e
core/restore_web_server.py, passato come access_log_class a
web.AppRunner.
"""

from __future__ import annotations

from aiohttp.abc import AbstractAccessLogger

WEBHOOK_PATH_PREFIX = "/webhook/"


def redact_path(path: str) -> str:
    """
    Sostituisce con "***" la parte sensibile del percorso: tutto ciò
    che segue "/webhook/" (il token che identifica canale e server di
    destinazione). Qualunque altro percorso resta invariato — nessun
    altro endpoint di questi due server ha segreti nel PERCORSO (il
    callback OAuth2 li ha solo nella query string, mai scritta da
    RedactedAccessLogger in nessun caso).
    """
    if path.startswith(WEBHOOK_PATH_PREFIX):
        return WEBHOOK_PATH_PREFIX + "***"
    return path


class RedactedAccessLogger(AbstractAccessLogger):
    """
    Logga IP del chiamante, metodo, percorso redatto, stato della
    risposta e tempo impiegato — MAI la query string (dove passano
    "code"/"state" nel callback OAuth2) e MAI il token grezzo di un
    webhook custom nel percorso.
    """

    def log(self, request, response, time: float) -> None:
        percorso = redact_path(request.path)
        self.logger.info(
            '%s "%s %s" %s %.6fs',
            request.remote,
            request.method,
            percorso,
            response.status,
            time,
        )
