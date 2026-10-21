"""
core/redacted_access_log.py
================================
AccessLogger di aiohttp che non scrive mai un segreto nei log dei
server web (SEC-9): il token di un webhook custom
(POST /webhook/<token>), il link della verifica web (/verifica/<token>,
che con l'IP accanto collegherebbe l'IP a un membro) e la query string del callback OAuth2 del
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
# Il link della verifica web (pannello, NF-21) porta server e membro: accanto all'IP del log
# sarebbe l'IP in chiaro di una persona.
PREFISSI_REDATTI = (WEBHOOK_PATH_PREFIX, "/verifica/")


def redact_path(path: str) -> str:
    """
    Sostituisce con "***" la parte sensibile del percorso: tutto ciò
    che segue "/webhook/" (il token che identifica canale e server di
    destinazione) e ciò che segue "/verifica/" (pannello web). Qualunque
    altro percorso resta invariato — nessun altro endpoint ha segreti nel PERCORSO (il
    callback OAuth2 li ha solo nella query string, mai scritta da
    RedactedAccessLogger in nessun caso).
    """
    for prefisso in PREFISSI_REDATTI:
        if path.startswith(prefisso):
            return prefisso + "***"
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
