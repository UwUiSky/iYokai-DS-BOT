"""
core/verify_vpn.py
==================
VPN e proxy nella verifica web (D64): mette insieme gli strati e dice se bloccare e con quale metodo.
Prima i controlli locali (ASN di hosting, nodi Tor, reti di VPN e data center, intestazioni di proxy,
fuso orario), poi, solo se nessuno ha già deciso e c'è una chiave, il servizio esterno.
L'IP vive solo in questa chiamata: la cache del servizio usa un'impronta, non si salva niente.
Funzioni coperte: SPEC §4.2 (VPN e proxy, D64)
Dipende da: core/verify_vpn_logic.py, core/verify_vpn_dati.py, core/verify_vpn_esterno.py, core/geoip_paesi.py
"""

from __future__ import annotations

import hashlib
import hmac

from core import geoip_paesi, verify_vpn_dati, verify_vpn_esterno
from core import verify_vpn_logic as logica


def impronta_ip(ip: str, chiave: str) -> str:
    """HMAC dell'IP con la chiave del pannello: serve solo da chiave di cache, non si può invertire."""
    return hmac.new(chiave.encode(), ip.encode(), hashlib.sha256).hexdigest()[:32]


async def rileva(
    ip: str, *, segnali_intestazioni: tuple[str, ...] = (), fuso: str | None = None, chiave: str = ""
) -> logica.Rilevazione:
    indirizzo = logica.ip_controllabile(ip)
    if indirizzo is None:
        return logica.Rilevazione(False)  # privato, locale o storto: mai bloccato
    dati = verify_vpn_dati.dati()
    forti: list[str] = []
    deboli: list[str] = []
    asn = verify_vpn_dati.asn_da_ip(indirizzo)
    if asn is not None and asn in dati.asn_hosting:
        forti.append(logica.METODO_ASN)
    if logica.ip_in_nodi_tor(indirizzo, dati.nodi_tor):
        forti.append(logica.METODO_TOR)
    if dati.reti.contiene(indirizzo):
        forti.append(logica.METODO_ELENCO)
    for segnale in segnali_intestazioni:
        (forti if segnale in logica.METODI_FORTI else deboli).append(segnale)
    if logica.fuso_incoerente(fuso, geoip_paesi.paese_da_ip(str(indirizzo)), dati.fusi):
        deboli.append(logica.METODO_FUSO)
    if not forti:
        servizio = verify_vpn_esterno.servizio()
        if servizio is not None and await servizio.controlla(str(indirizzo), impronta_ip(str(indirizzo), chiave)) is True:
            forti.append(logica.METODO_SERVIZIO)
    return logica.decidi(forti, deboli)
