"""
core/controllo_link_servizi.py
==============================
Servizi esterni facoltativi per il controllo dei link: Google Safe Browsing (v4 Lookup), Cloudflare (Intel sul
dominio), VirusTotal. Ognuno si spegne da solo se manca la chiave; ha un tetto di richieste al minuto e al giorno.
Le chiavi si leggono solo da core/config.py e non finiscono mai nei log (safe_http scrive l'indirizzo senza query).
PhishTank (iscrizioni chiuse) e URLScan.io (analisi lente e pubbliche) non si usano: vedi D112.
Funzioni coperte: SPEC §6.21 (AMD-030, D111, D112)
Dipende da: core/safe_http.py
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import deque
from dataclasses import dataclass

from core import safe_http

logger = logging.getLogger("iyokai.controllo_link")

SICURO = "sicuro"
SOSPETTO = "sospetto"
PERICOLOSO = "pericoloso"

_ID_CLOUDFLARE = re.compile(r"^[0-9a-f]{32}$")
_DOMINIO_SICURO = re.compile(r"^[a-z0-9.-]{1,253}$")
MAX_BYTE_RISPOSTA = 256 * 1024


@dataclass(frozen=True)
class Chiavi:
    google: str = ""
    cloudflare_token: str = ""
    cloudflare_account: str = ""
    virustotal: str = ""


def chiavi_da_config() -> Chiavi:
    """Le chiavi dal file centrale (core/config.py). Se la configurazione non si carica, nessun servizio."""
    try:
        from core.config import config

        return Chiavi(
            google=config.GOOGLE_SAFE_BROWSING_KEY, cloudflare_token=config.CLOUDFLARE_API_TOKEN,
            cloudflare_account=config.CLOUDFLARE_ACCOUNT_ID, virustotal=config.VIRUSTOTAL_API_KEY,
        )
    except Exception:  # noqa: BLE001  # test o avvio senza .env: servizi spenti
        return Chiavi()


class Tetto:
    """Quota di un servizio: richieste al minuto e al giorno. `consuma()` dice se si può chiamare ora."""

    def __init__(self, al_minuto: int, al_giorno: int) -> None:
        self.al_minuto, self.al_giorno = al_minuto, al_giorno
        self._minuto: deque[float] = deque()
        self._giorno: deque[float] = deque()

    def consuma(self, adesso: float | None = None) -> bool:
        t = time.monotonic() if adesso is None else adesso
        while self._minuto and t - self._minuto[0] >= 60:
            self._minuto.popleft()
        while self._giorno and t - self._giorno[0] >= 86400:
            self._giorno.popleft()
        if len(self._minuto) >= self.al_minuto or len(self._giorno) >= self.al_giorno:
            return False
        self._minuto.append(t)
        self._giorno.append(t)
        return True


# Sotto le quote gratuite: Safe Browsing 10.000/giorno, VirusTotal 4/minuto e 500/giorno, Cloudflare larga.
TETTI = {"google": Tetto(60, 9000), "cloudflare": Tetto(30, 3000), "virustotal": Tetto(4, 450)}


def _json(testo: str | None) -> dict | None:
    if not testo:
        return None
    try:
        dati = json.loads(testo)
    except ValueError:
        return None
    return dati if isinstance(dati, dict) else None


_CATEGORIE_GOOGLE = {
    "MALWARE": ("pericoloso", "malware"),
    "SOCIAL_ENGINEERING": ("pericoloso", "phishing"),
    "UNWANTED_SOFTWARE": ("sospetto", "software_indesiderato"),
    "POTENTIALLY_HARMFUL_APPLICATION": ("sospetto", "app_dannosa"),
}


async def google_safe_browsing(url: str, chiave: str, richiesta=safe_http.safe_richiesta) -> tuple[str, str] | None:
    """(livello, categoria) se Google segnala l'URL; ("sicuro", "") se non lo segnala; None se il servizio non risponde."""
    if not chiave or not TETTI["google"].consuma():
        return None
    corpo = {
        "client": {"clientId": "iyokai-bot", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": list(_CATEGORIE_GOOGLE), "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"], "threatEntries": [{"url": url[:2048]}],
        },
    }
    testo = await richiesta(
        f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={chiave}",
        metodo="POST", json_corpo=corpo, max_bytes=MAX_BYTE_RISPOSTA,
    )
    dati = _json(testo)
    if dati is None:
        return None
    peggiore = None
    for trovato in dati.get("matches") or ():
        livello, categoria = _CATEGORIE_GOOGLE.get(str(trovato.get("threatType")), ("sospetto", "altro"))
        if peggiore is None or livello == PERICOLOSO:
            peggiore = (livello, categoria)
    return peggiore or (SICURO, "")


async def cloudflare_intel(dominio: str, token: str, account: str, richiesta=safe_http.safe_richiesta) -> tuple[str, str] | None:
    """Cloudflare Intel sul dominio: tipi di rischio (phishing, malware...). None se spento o senza risposta."""
    if not token or not _ID_CLOUDFLARE.match(account or "") or not _DOMINIO_SICURO.match(dominio) or not TETTI["cloudflare"].consuma():
        return None
    testo = await richiesta(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/intel/domain?domain={dominio}",
        headers={"Authorization": f"Bearer {token}"}, max_bytes=MAX_BYTE_RISPOSTA,
    )
    dati = _json(testo)
    if dati is None or not dati.get("success", False):
        return None
    rischi = [str(r.get("name", "")).lower() for r in (dati.get("result") or {}).get("risk_types") or () if isinstance(r, dict)]
    for nome in rischi:
        if "phishing" in nome:
            return PERICOLOSO, "phishing"
        if "malware" in nome:
            return PERICOLOSO, "malware"
    return (SOSPETTO, rischi[0][:40]) if rischi else (SICURO, "")


async def virustotal(dominio: str, chiave: str, richiesta=safe_http.safe_richiesta) -> tuple[str, str] | None:
    """Verdetto dei motori di VirusTotal sul dominio: 3 o più «malevolo» = pericoloso, 1-2 = sospetto."""
    if not chiave or not _DOMINIO_SICURO.match(dominio) or not TETTI["virustotal"].consuma():
        return None
    testo = await richiesta(
        f"https://www.virustotal.com/api/v3/domains/{dominio}", headers={"x-apikey": chiave}, max_bytes=MAX_BYTE_RISPOSTA,
    )
    dati = _json(testo)
    if dati is None:
        return None
    try:
        stat = dati["data"]["attributes"]["last_analysis_stats"]
        cattivi = int(stat.get("malicious", 0))
        dubbi = int(stat.get("suspicious", 0))
    except (KeyError, TypeError, ValueError):
        return None
    if cattivi >= 3:
        return PERICOLOSO, "malware"
    return (SOSPETTO, "altro") if cattivi + dubbi >= 1 else (SICURO, "")
