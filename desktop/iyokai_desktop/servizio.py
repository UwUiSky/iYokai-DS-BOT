"""
desktop/iyokai_desktop/servizio.py
==================================
Chiamate al servizio iYokai con il codice personale (`Authorization: Bearer`). Solo https (http sul proprio PC),
risposte al massimo di 1 MB, nessun reindirizzamento seguito, nessun invio del codice altrove.
Funzioni coperte: SPEC D.1, D.5-D.10
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .impostazioni import indirizzo_valido

MAX_RISPOSTA = 1024 * 1024
TEMPO_MASSIMO = 30


class ErroreServizio(Exception):
    """`codice`: la parola del servizio (es. token_non_valido) o rete_non_raggiungibile; `stato`: HTTP (0 = rete)."""

    def __init__(self, codice: str, stato: int = 0, extra: dict | None = None) -> None:
        super().__init__(f"{codice} ({stato})")
        self.codice, self.stato, self.extra = codice, stato, extra or {}


class _NessunReindirizzamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D102
        return None


def _apri_normale(richiesta: urllib.request.Request, tempo: float):
    return urllib.request.build_opener(_NessunReindirizzamento).open(richiesta, timeout=tempo)


class Servizio:
    def __init__(self, base: str, codice: str, apri=_apri_normale) -> None:
        self.base = indirizzo_valido(base)
        self._codice = codice
        self._apri = apri

    def _chiama(self, metodo: str, percorso: str, query: dict | None = None, corpo: dict | None = None, pubblico: bool = False):
        url = self.base + percorso + ("?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None}) if query else "")
        intestazioni = {"Accept": "application/json", "User-Agent": "iyokai-desktop"}
        if not pubblico:
            intestazioni["Authorization"] = f"Bearer {self._codice}"
        dati = None
        if corpo is not None:
            dati = json.dumps(corpo).encode("utf-8")
            intestazioni["Content-Type"] = "application/json"
        richiesta = urllib.request.Request(url, data=dati, method=metodo, headers=intestazioni)
        try:
            with self._apri(richiesta, TEMPO_MASSIMO + float(query.get("attesa", 0) if query else 0)) as risposta:
                grezzo = risposta.read(MAX_RISPOSTA + 1)
        except urllib.error.HTTPError as errore:
            grezzo, stato = errore.read(MAX_RISPOSTA + 1), errore.code
            try:
                extra = json.loads(grezzo)
            except ValueError:
                extra = {}
            codice = extra.get("errore") or extra.get("esito") or f"http_{stato}"
            raise ErroreServizio(str(codice), stato, extra if isinstance(extra, dict) else {}) from None
        except (urllib.error.URLError, OSError, TimeoutError):
            raise ErroreServizio("rete_non_raggiungibile") from None
        if len(grezzo) > MAX_RISPOSTA:
            raise ErroreServizio("risposta_troppo_grande")
        try:
            risultato = json.loads(grezzo)
        except ValueError:
            raise ErroreServizio("risposta_non_valida") from None
        if not isinstance(risultato, dict):
            raise ErroreServizio("risposta_non_valida")
        return risultato

    def io(self) -> dict:
        return self._chiama("GET", "/api/desktop/io")

    def server(self) -> list[dict]:
        return self._chiama("GET", "/api/desktop/server").get("server", [])

    def eventi(self, dopo: int = 0, tipo: str | None = None, attesa: int = 0, limite: int = 50) -> list[dict]:
        risposta = self._chiama("GET", "/api/desktop/eventi", {"dopo": dopo, "tipo": tipo, "attesa": attesa, "limite": limite})
        return risposta.get("eventi", [])

    def storico(self) -> dict:
        return self._chiama("GET", "/api/desktop/storico")

    def risposte(self) -> list[dict]:
        return self._chiama("GET", "/api/desktop/risposte").get("risposte", [])

    def traduci(self, testo: str, lingua: str) -> str:
        return str(self._chiama("POST", "/api/desktop/traduci", corpo={"testo": testo, "lingua": lingua}).get("testo", ""))

    def radio(self) -> dict:
        return self._chiama("GET", "/api/desktop/radio")

    def staff_azioni(self, server: int) -> list[dict]:
        return self._chiama("GET", "/api/desktop/staff/azioni", {"server": server}).get("azioni", [])

    def staff_azione(self, server: int, azione: str, **dati) -> str:
        """Ritorna il codice dell'esito (ok o il motivo del rifiuto). Il servizio controlla i permessi veri."""
        try:
            return str(self._chiama("POST", "/api/desktop/staff/azione", corpo={"server": server, "azione": azione, **dati}).get("esito"))
        except ErroreServizio as errore:
            if "esito" in errore.extra:
                return str(errore.extra["esito"])
            raise
