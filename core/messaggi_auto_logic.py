"""
core/messaggi_auto_logic.py
===========================
Logica senza Discord di `/admin-messaggi auto`: citazione dei link ai messaggi, correzione dei link
(x.com -> fixupx.com ...), pubblicazione degli annunci (10 all'ora per canale) e modelli dei messaggi fissi.
Funzioni coperte: catalogo #128 UTL-071, 072, 112, 155 (D69, B3)
"""

from __future__ import annotations

import re
from collections import deque

MAX_CITAZIONI = 3
MAX_LINK_CORRETTI = 3
MAX_CANALI_PUBBLICA = 25
PUBBLICAZIONI_ALL_ORA = 10  # limite di Discord per canale
FINESTRA_SECONDI = 3600
MODELLI_FISSI = ("regole", "benvenuto", "faq", "annunci", "eventi")

# Elenco proposto all'admin (U8): domini di terzi, che possono chiudere o cambiare padrone. Spenti di base.
CORREZIONI = {
    "x.com": "fixupx.com",
    "twitter.com": "fxtwitter.com",
    "instagram.com": "ddinstagram.com",
    "tiktok.com": "vxtiktok.com",
    "reddit.com": "rxddit.com",
    "pixiv.net": "phixiv.net",
    "bsky.app": "fxbsky.app",
}

_LINK_MESSAGGIO = re.compile(
    r"(?<![<\w])https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d{15,20})/(\d{15,20})/(\d{15,20})"
)
_LINK = re.compile(r"(?<![<\w@])(https?)://([A-Za-z0-9.-]+)(/[^\s<>]*)?")


def link_ai_messaggi(testo: str, guild_id: int) -> list[tuple[int, int]]:
    """(canale, messaggio) dei link dello stesso server, senza doppioni, al massimo 3."""
    viste: list[tuple[int, int]] = []
    for g, c, m in _LINK_MESSAGGIO.findall(testo or ""):
        if int(g) == guild_id and (int(c), int(m)) not in viste:
            viste.append((int(c), int(m)))
    return viste[:MAX_CITAZIONI]


def puo_citare(origine_nsfw: bool, destinazione_nsfw: bool, autore_vede_origine: bool) -> bool:
    """Solo chi può leggere il canale di origine; mai da un canale NSFW a uno che non lo è."""
    return autore_vede_origine and not (origine_nsfw and not destinazione_nsfw)


def etichetta_correzione(dominio: str) -> str:
    return f"{dominio}>{CORREZIONI[dominio]}"


def mappa_correzioni(voci: list[str]) -> dict[str, str]:
    """Da «dominio>sostituto» al dizionario; ignora ciò che non è nell'elenco proposto."""
    mappa = {}
    for v in voci:
        da, _, a = v.partition(">")
        if CORREZIONI.get(da) == a:
            mappa[da] = a
    return mappa


def link_corretti(testo: str, mappa: dict[str, str]) -> list[str]:
    """I link del testo il cui dominio è nella mappa, riscritti. Max 3. Quelli tra <> si lasciano stare."""
    if not mappa:
        return []
    fuori: list[str] = []
    for schema, host, percorso in _LINK.findall(testo or ""):
        h = host.casefold().removeprefix("www.")
        if h in mappa:
            nuovo = f"{schema}://{mappa[h]}{percorso or ''}"
            if nuovo not in fuori:
                fuori.append(nuovo)
    return fuori[:MAX_LINK_CORRETTI]


class LimitePubblicazioni:
    """Quante pubblicazioni ha già fatto un canale nell'ultima ora (il tetto di Discord è 10)."""

    def __init__(self) -> None:
        self._tempi: dict[int, deque[float]] = {}
        self._avvisati: dict[int, float] = {}

    def ammessa(self, canale_id: int, adesso: float) -> bool:
        coda = self._tempi.setdefault(canale_id, deque())
        while coda and adesso - coda[0] >= FINESTRA_SECONDI:
            coda.popleft()
        if len(coda) >= PUBBLICAZIONI_ALL_ORA:
            return False
        coda.append(adesso)
        return True

    def da_avvisare(self, canale_id: int, adesso: float) -> bool:
        """True una volta sola per finestra: l'avviso nei log non si ripete a ogni messaggio saltato."""
        ultimo = self._avvisati.get(canale_id)
        if ultimo is not None and adesso - ultimo < FINESTRA_SECONDI:
            return False
        self._avvisati[canale_id] = adesso
        return True

    def dimentica(self, canale_id: int) -> None:
        self._tempi.pop(canale_id, None)
        self._avvisati.pop(canale_id, None)


def chiave_modello(nome: str) -> str:
    return f"fissi_modello_{nome}"
