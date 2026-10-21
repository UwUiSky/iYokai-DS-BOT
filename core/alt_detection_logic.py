"""
core/alt_detection_logic.py
===========================
Verifica su pagina web e riconoscimento degli account doppi, senza rete né
Discord: il link firmato che il bot dà al membro, le impronte (mai l'IP in
chiaro) e il livello di somiglianza tra due account.
Funzioni coperte: SPEC §4.2, §4.3 (NF-21)

Privacy (D19, NF-04): l'impronta è un HMAC-SHA256 con un sale segreto del bot
e l'id del server. Lo stesso IP dà impronte diverse in server diversi: chi
legge il database non può né risalire all'IP né collegare due server.
Il confronto avviene solo dentro lo stesso server. Le impronte scadono dopo
`GIORNI_IMPRONTE` (lavoro giornaliero, `core/data_registry.py`). Nessun ban
automatico: il bot avvisa lo staff.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import time
from dataclasses import dataclass

DURATA_LINK_SECONDI = 15 * 60
GIORNI_IMPRONTE = 30
GIORNI_DOPPI = 90
MAX_TOKEN = 200
MAX_TESTO_BROWSER = 512

TIPO_IP = "ip"
TIPO_BROWSER = "browser"

LIVELLO_ALTO = "alto"  # stessa rete e stesso browser
LIVELLO_MEDIO = "medio"  # stessa rete IPv6 (/64), browser diverso
LIVELLO_BASSO = "basso"  # stesso IPv4, browser diverso
_ORDINE_LIVELLI = {LIVELLO_ALTO: 0, LIVELLO_MEDIO: 1, LIVELLO_BASSO: 2}


def _firma(chiave: str, testo: str) -> str:
    return hmac.new(chiave.encode("utf-8"), testo.encode("utf-8"), hashlib.sha256).hexdigest()


# ------------------------------------------------------------------ link
def crea_token(chiave: str, guild_id: int, user_id: int, adesso: float | None = None) -> str:
    """Il pezzo finale del link `/verifica/<token>`: vale per un membro di un server, 15 minuti."""
    scade = int((adesso if adesso is not None else time.time()) + DURATA_LINK_SECONDI)
    corpo = f"{guild_id}-{user_id}-{scade}"
    return f"{corpo}-{_firma(chiave, 'verifica:' + corpo)[:40]}"


def leggi_token(chiave: str, token: str | None, adesso: float | None = None) -> tuple[int, int] | None:
    """(server, membro) se il token è nostro e non è scaduto, altrimenti None."""
    if not token or len(token) > MAX_TOKEN:
        return None
    parti = token.split("-")
    if len(parti) != 4 or not all(p.isdigit() for p in parti[:3]):
        return None
    guild_id, user_id, scade, firma = parti
    corpo = f"{guild_id}-{user_id}-{scade}"
    if not hmac.compare_digest(_firma(chiave, "verifica:" + corpo)[:40], firma):
        return None
    if int(scade) < (adesso if adesso is not None else time.time()):
        return None
    return int(guild_id), int(user_id)


def url_verifica(url_pubblico: str, token: str) -> str:
    return f"{url_pubblico.rstrip('/')}/verifica/{token}"


def csrf_verifica(chiave: str, token: str) -> str:
    """Il campo nascosto del modulo della pagina: legato al link, niente da salvare."""
    return _firma(chiave, "verifica-csrf:" + token)


# -------------------------------------------------------------- impronte
# Un IP interno è quello di un proxy non dichiarato (WEB_PANEL_TRUSTED_PROXY) o di Docker:
# uguale per tutti, farebbe di ogni membro il «doppio» di ogni altro. Non fa impronta.
_RETI_INTERNE = tuple(
    ipaddress.ip_network(r)
    for r in (
        "0.0.0.0/8", "10.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16",
        "::/128", "::1/128", "fc00::/7", "fe80::/10",
    )
)


def rete(ip: str) -> str | None:
    """
    La parte dell'IP che identifica la connessione: l'IPv4 intero, il /64
    per l'IPv6 (la stessa casa cambia spesso la seconda metà). None se non è
    un IP o se è un IP interno (proxy o rete locale).
    """
    try:
        indirizzo = ipaddress.ip_address(ip.strip())
    except ValueError:
        return None
    if isinstance(indirizzo, ipaddress.IPv6Address) and indirizzo.ipv4_mapped is not None:
        indirizzo = indirizzo.ipv4_mapped
    if any(indirizzo in r for r in _RETI_INTERNE if r.version == indirizzo.version):
        return None
    if isinstance(indirizzo, ipaddress.IPv6Address):
        return str(ipaddress.IPv6Network(f"{indirizzo}/64", strict=False).network_address) + "/64"
    return str(indirizzo)


def e_ipv4(ip: str) -> bool:
    """La rete dell'IP è un IPv4 intero (anche scritto come IPv6 «::ffff:»)."""
    parte_rete = rete(ip)
    return parte_rete is not None and "/" not in parte_rete


def impronta(chiave: str, guild_id: int, tipo: str, valore: str) -> str:
    """HMAC con il sale del bot e il server: mai reversibile, mai uguale tra due server."""
    return _firma(chiave, f"impronta:{guild_id}:{tipo}:{valore}")


def impronte_richiesta(
    chiave: str, guild_id: int, ip: str, user_agent: str | None, lingua: str | None
) -> dict[str, str]:
    """Le impronte di chi apre la pagina. L'IP non esce mai da questa funzione."""
    risultato: dict[str, str] = {}
    parte_rete = rete(ip)
    if parte_rete is not None:
        risultato[TIPO_IP] = impronta(chiave, guild_id, TIPO_IP, parte_rete)
    browser = f"{(user_agent or '')[:MAX_TESTO_BROWSER]}|{(lingua or '')[:64]}"
    if browser != "|":
        risultato[TIPO_BROWSER] = impronta(chiave, guild_id, TIPO_BROWSER, browser)
    return risultato


# ---------------------------------------------------------------- doppi
@dataclass(frozen=True)
class Doppio:
    altro_user_id: int
    livello: str


def valuta_doppi(uguali: list[tuple[int, str]], user_id: int, *, ipv4: bool = False) -> list[Doppio]:
    """
    `uguali`: (altro membro, tipo di impronta uguale). Solo la stessa rete fa
    un doppio: il browser da solo è troppo comune (stesso telefono, stessa
    versione). Stessa rete + stesso browser = livello alto.

    Scelta (r8): lo stesso IPv4 da solo resta «basso». Un IPv4 è spesso di
    molte persone insieme (CGNAT dei telefoni, scuole, uffici, famiglie):
    da solo non dice che è la stessa persona. Un /64 IPv6 è di norma una sola
    casa, quindi da solo vale «medio». `ipv4`: la rete di chi si verifica
    adesso è un IPv4 (`e_ipv4`), quindi anche quella uguale lo è.
    """
    tipi: dict[int, set[str]] = {}
    for altro, tipo in uguali:
        if altro != user_id:
            tipi.setdefault(altro, set()).add(tipo)
    solo_rete = LIVELLO_BASSO if ipv4 else LIVELLO_MEDIO
    doppi = [
        Doppio(altro, LIVELLO_ALTO if TIPO_BROWSER in trovati else solo_rete)
        for altro, trovati in tipi.items()
        if TIPO_IP in trovati
    ]
    return sorted(doppi, key=lambda d: (_ORDINE_LIVELLI[d.livello], d.altro_user_id))


def testo_avviso(member_mention: str, member_id: int, doppi: list[Doppio], limite: int = 10) -> str:
    """Il messaggio per lo staff (≤ 4096 caratteri: al massimo `limite` righe)."""
    righe = [
        f"- <@{d.altro_user_id}> (`{d.altro_user_id}`): somiglianza **{d.livello}**"
        for d in doppi[:limite]
    ]
    if len(doppi) > limite:
        righe.append(f"- … e altri {len(doppi) - limite}")
    return (
        f"{member_mention} (`{member_id}`) si è verificato dalla pagina web con la stessa connessione di:\n"
        + "\n".join(righe)
        + "\nNessuna azione automatica: controlla tu. Elenco completo con `/security alt elenco`."
    )
