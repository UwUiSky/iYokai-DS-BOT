"""
core/verify_vpn_dati.py
=======================
I dati locali per riconoscere VPN e proxy nella verifica web (D64): ASN di hosting e data center,
nodi di uscita Tor, reti di VPN e data center, fusi orari dei paesi, e la banca dati ASN (MMDB,
DB-IP «IP to ASN Lite», CC BY 4.0). Si leggono dalla cartella `VPN_DATI_CARTELLA` (di base `data/vpn`)
e si rileggono da soli quando i file cambiano (controllo al massimo ogni minuto). File assente o rotto:
quello strato resta vuoto, senza errori. `GEOIP_ASN_MMDB`: percorso della banca dati ASN.
Funzioni coperte: SPEC §4.2 (VPN e proxy, D64)
Dipende da: core/verify_vpn_logic.py, core/bounded_cache.py
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.bounded_cache import BoundedCache
from core.verify_vpn_logic import ElencoReti, asn_da_record, leggi_asn, leggi_fusi, leggi_nodi_tor

logger = logging.getLogger("iyokai.verify_vpn")

FILE_ASN = "asn_hosting.txt"
FILE_TOR = "tor_uscita.txt"
FILE_RETI_VPN = "reti_vpn.txt"
FILE_RETI_DATACENTER = "reti_datacenter.txt"
FILE_FUSI = "fuso_paesi.txt"
_FILE = (FILE_ASN, FILE_TOR, FILE_RETI_VPN, FILE_RETI_DATACENTER, FILE_FUSI)
INTERVALLO_CONTROLLO = 60.0  # secondi tra due controlli dei file
TETTO_CACHE_ASN = 4096


@dataclass(frozen=True)
class Dati:
    asn_hosting: frozenset[int] = frozenset()
    nodi_tor: frozenset[str] = frozenset()
    reti: ElencoReti = field(default_factory=ElencoReti)
    fusi: dict = field(default_factory=dict)


_dati: Dati | None = None
_firma: tuple = ()
_ultimo_controllo = 0.0
_fissi = False
_lettore_asn = None
_provato_asn = False
_cache_asn: BoundedCache[bytes, int] = BoundedCache(TETTO_CACHE_ASN)
_sale = secrets.token_bytes(16)  # la cache non tiene gli IP: solo un'impronta valida finché il processo vive


def azzera() -> None:
    """Per i test: torna allo stato iniziale."""
    global _dati, _firma, _ultimo_controllo, _fissi, _lettore_asn, _provato_asn
    _dati, _firma, _ultimo_controllo, _fissi = None, (), 0.0, False
    _lettore_asn, _provato_asn = None, False
    _cache_asn.clear()


def usa_dati(dati: Dati) -> None:
    """Per i test: dati già pronti, mai riletti dai file."""
    global _dati, _fissi
    _dati, _fissi = dati, True


def usa_lettore_asn(lettore) -> None:
    """Per i test: un lettore già pronto (con `get(ip)`)."""
    global _lettore_asn, _provato_asn
    _lettore_asn, _provato_asn = lettore, True
    _cache_asn.clear()


def cartella() -> Path:
    scelta = os.environ.get("VPN_DATI_CARTELLA", "").strip()
    return Path(scelta) if scelta else Path(__file__).resolve().parent.parent / "data" / "vpn"


def _testo(percorso: Path) -> str:
    try:
        return percorso.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _firma_file(base: Path) -> tuple:
    firma = []
    for nome in _FILE:
        try:
            stato = (base / nome).stat()
            firma.append((nome, stato.st_mtime_ns, stato.st_size))
        except OSError:
            firma.append((nome, 0, 0))
    return tuple(firma)


def ricarica() -> Dati:
    """Rilegge tutti i file adesso."""
    global _dati, _firma, _ultimo_controllo
    base = cartella()
    _firma = _firma_file(base)
    _ultimo_controllo = time.monotonic()
    reti = ElencoReti.da_testo(_testo(base / FILE_RETI_VPN) + "\n" + _testo(base / FILE_RETI_DATACENTER))
    _dati = Dati(
        asn_hosting=leggi_asn(_testo(base / FILE_ASN)),
        nodi_tor=leggi_nodi_tor(_testo(base / FILE_TOR)),
        reti=reti,
        fusi=leggi_fusi(_testo(base / FILE_FUSI)),
    )
    return _dati


def dati() -> Dati:
    if _dati is None:
        return ricarica()
    if not _fissi and time.monotonic() - _ultimo_controllo >= INTERVALLO_CONTROLLO:
        if _firma_file(cartella()) != _firma:
            return ricarica()
        _segna_controllo()
    return _dati


def _segna_controllo() -> None:
    global _ultimo_controllo
    _ultimo_controllo = time.monotonic()


# ------------------------------------------------------------ banca dati ASN
def _apri_asn():
    global _lettore_asn, _provato_asn
    if _provato_asn:
        return _lettore_asn
    _provato_asn = True
    percorso = os.environ.get("GEOIP_ASN_MMDB", "").strip()
    if not percorso:
        return None
    try:
        import maxminddb

        _lettore_asn = maxminddb.open_database(percorso)
    except Exception:  # file assente, rotto o libreria mancante: solo questo strato si spegne
        logger.warning("Banca dati ASN non utilizzabile: lo strato ASN della verifica resta spento.")
        _lettore_asn = None
    return _lettore_asn


def asn_attiva() -> bool:
    return _apri_asn() is not None


def asn_da_ip(ip) -> int | None:
    """L'ASN dell'IP (oggetto `ipaddress`), o None. In cache con tetto, senza tenere l'IP."""
    if ip is None:
        return None
    lettore = _apri_asn()
    if lettore is None:
        return None
    chiave = hashlib.blake2b(str(ip).encode(), key=_sale, digest_size=8).digest()
    trovato = _cache_asn.get(chiave)
    if trovato is not None:
        return trovato or None
    try:
        asn = asn_da_record(lettore.get(str(ip)))
    except Exception:
        return None  # un errore non si ricorda: la prossima volta si riprova
    _cache_asn.set(chiave, asn or 0)
    return asn
