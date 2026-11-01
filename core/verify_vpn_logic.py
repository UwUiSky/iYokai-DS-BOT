"""
core/verify_vpn_logic.py
========================
VPN e proxy nella verifica web (D64), senza rete né Discord: IP controllabili, elenchi di reti
(IPv4 e IPv6), ASN, nodi Tor, intestazioni di proxy, fuso orario del browser e la regola che decide.
Un segnale forte blocca; uno debole (fuso, intestazione Via) da solo no, due insieme sì.
Gli IP privati, locali e riservati non si controllano mai: un test o una rete di casa non è bloccata.
Funzioni coperte: SPEC §4.2 (VPN e proxy, D64)
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

METODO_ASN = "asn"
METODO_TOR = "tor"
METODO_ELENCO = "elenco"
METODO_INTESTAZIONI = "intestazioni"
METODO_SERVIZIO = "servizio"
METODO_FUSO = "fuso"
METODO_VIA = "via"

METODI_FORTI = (METODO_ASN, METODO_TOR, METODO_ELENCO, METODO_INTESTAZIONI, METODO_SERVIZIO)
METODI_DEBOLI = (METODO_FUSO, METODO_VIA)
TUTTI_I_METODI = METODI_FORTI + METODI_DEBOLI

_ASN_MASSIMO = 4294967295
_FUSO = re.compile(r"^[A-Za-z][A-Za-z0-9_+\-]*(/[A-Za-z0-9_+\-]+){0,2}$")
FUSO_MAX = 64


# ---------------------------------------------------------------- indirizzi
def ip_controllabile(ip) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """L'indirizzo, solo se è pubblico. Privato, locale, riservato, storto o vuoto: None."""
    if not isinstance(ip, str) or not ip.strip():
        return None
    try:
        indirizzo = ipaddress.ip_address(ip.strip())
    except ValueError:
        return None
    if isinstance(indirizzo, ipaddress.IPv6Address) and indirizzo.ipv4_mapped is not None:
        indirizzo = indirizzo.ipv4_mapped  # ::ffff:1.2.3.4 è l'indirizzo IPv4 1.2.3.4
    if (not indirizzo.is_global or indirizzo.is_multicast or indirizzo.is_reserved
            or indirizzo.is_loopback or indirizzo.is_link_local or indirizzo.is_unspecified):
        return None
    return indirizzo


# ------------------------------------------------------------- elenco di reti
class ElencoReti:
    """Reti IPv4 e IPv6. Per ogni lunghezza di prefisso un insieme: la ricerca costa al massimo 33 o 129 controlli."""

    def __init__(self, reti: Iterable[ipaddress.IPv4Network | ipaddress.IPv6Network] = ()) -> None:
        self._per_versione: dict[int, dict[int, set[int]]] = {4: {}, 6: {}}
        self._totale = 0
        for rete in reti:
            gruppo = self._per_versione[rete.version].setdefault(rete.prefixlen, set())
            chiave = int(rete.network_address) >> (rete.max_prefixlen - rete.prefixlen)
            if chiave not in gruppo:
                gruppo.add(chiave)
                self._totale += 1

    @classmethod
    def da_testo(cls, testo: str) -> ElencoReti:
        """Una rete (o un indirizzo) per riga; `#` e `;` aprono un commento; le righe storte si ignorano."""
        reti = []
        for riga in testo.splitlines():
            riga = riga.split("#", 1)[0].split(";", 1)[0].strip()
            if not riga:
                continue
            try:
                reti.append(ipaddress.ip_network(riga, strict=False))
            except ValueError:
                continue
        return cls(reti)

    def __len__(self) -> int:
        return self._totale

    def contiene(self, ip) -> bool:
        if ip is None:
            return False
        massimo = ip.max_prefixlen
        valore = int(ip)
        for lunghezza, gruppo in self._per_versione[ip.version].items():
            if (valore >> (massimo - lunghezza)) in gruppo:
                return True
        return False


# --------------------------------------------------------------- ASN e Tor
def leggi_asn(testo: str) -> frozenset[int]:
    """Gli ASN di un file: una riga per ASN («123», «AS123») o un CSV che inizia con l'ASN."""
    risultato = set()
    for riga in testo.splitlines():
        riga = riga.split("#", 1)[0].strip()
        if not riga:
            continue
        primo = riga.split(",", 1)[0].strip().strip('"').upper().removeprefix("AS").strip()
        if primo.isdigit() and 0 < int(primo) <= _ASN_MASSIMO:
            risultato.add(int(primo))
    return frozenset(risultato)


def asn_da_record(record) -> int | None:
    """L'ASN dal record MMDB (DB-IP o GeoLite2 ASN). Nient'altro del record viene letto."""
    if not isinstance(record, dict):
        return None
    numero = record.get("autonomous_system_number")
    if isinstance(numero, int) and not isinstance(numero, bool) and 0 < numero <= _ASN_MASSIMO:
        return numero
    return None


def leggi_nodi_tor(testo: str) -> frozenset[str]:
    """Gli IP di uscita Tor, uno per riga, in forma normale (IPv6 compreso)."""
    risultato = set()
    for riga in testo.splitlines():
        riga = riga.split("#", 1)[0].strip()
        try:
            risultato.add(str(ipaddress.ip_address(riga)))
        except ValueError:
            continue
    return frozenset(risultato)


def ip_in_nodi_tor(ip, nodi: frozenset[str]) -> bool:
    return ip is not None and str(ip) in nodi


# ----------------------------------------------------- intestazioni di proxy
def segnali_intestazioni(remoto, intestazioni: Mapping[str, str], fidati: frozenset[str]) -> tuple[str, ...]:
    """
    Cosa dicono le intestazioni mandate dal client. Contano solo se la connessione arriva da un
    indirizzo pubblico che NON è un nostro proxy fidato: dal proxy fidato le scriviamo noi, e da una
    rete locale (reverse proxy non dichiarato) bloccherebbero tutti.
    `X-Forwarded-For` e `Forwarded` = proxy (forte); `Via` da solo = indizio debole.
    """
    if ip_controllabile(remoto) is None or (isinstance(remoto, str) and remoto in fidati):
        return ()
    presenti = {str(k).lower(): str(v).strip() for k, v in intestazioni.items()}
    segnali = []
    if presenti.get("x-forwarded-for") or presenti.get("forwarded"):
        segnali.append(METODO_INTESTAZIONI)
    if presenti.get("via"):
        segnali.append(METODO_VIA)
    return tuple(segnali)


# --------------------------------------------------------------- fuso orario
def fuso_pulito(valore) -> str | None:
    """Il nome del fuso mandato dal browser (es. «Europe/Rome»), solo se ha la forma di un nome tz."""
    if not isinstance(valore, str):
        return None
    valore = valore.strip()
    return valore if 0 < len(valore) <= FUSO_MAX and _FUSO.match(valore) else None


def leggi_fusi(testo: str) -> dict[str, frozenset[str]]:
    """Il file «fuso<TAB>paesi»: i paesi (codici di 2 lettere, virgola) di ogni fuso."""
    fusi = {}
    for riga in testo.splitlines():
        if riga.lstrip().startswith("#") or "\t" not in riga:
            continue
        nome, paesi = (parte.strip() for parte in riga.split("\t", 1))
        elenco = frozenset(p.strip().upper() for p in paesi.split(",") if re.fullmatch(r"[A-Za-z]{2}", p.strip()))
        if fuso_pulito(nome) and elenco:
            fusi[nome] = elenco
    return fusi


def fuso_incoerente(fuso, paese_ip, fusi: Mapping[str, frozenset[str]]) -> bool:
    """True solo se il fuso è noto, il paese dell'IP è noto e il fuso non appartiene a quel paese."""
    nome = fuso_pulito(fuso)
    if nome is None or not isinstance(paese_ip, str) or not paese_ip:
        return False
    paesi = fusi.get(nome)
    return paesi is not None and paese_ip.upper() not in paesi


# ------------------------------------------------------------------ decisione
@dataclass(frozen=True)
class Rilevazione:
    bloccato: bool
    metodi: tuple[str, ...] = ()


def decidi(forti: Iterable[str], deboli: Iterable[str]) -> Rilevazione:
    """Un segnale forte blocca. Senza forti servono almeno due segnali deboli diversi."""
    forti = tuple(dict.fromkeys(forti))
    deboli = tuple(dict.fromkeys(deboli))
    metodi = forti + deboli
    return Rilevazione(bloccato=bool(forti) or len(deboli) >= 2, metodi=metodi)


def testo_metodi(metodi: Iterable[str]) -> str:
    return ",".join(metodi)
