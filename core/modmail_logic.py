"""
core/modmail_logic.py
=====================
Regole pure del ModMail (ticket via messaggio privato): a quale server
appartiene un DM, nome del canale, testo da inoltrare, limite di messaggi.
Nessun accesso a Discord né al database.
Funzioni coperte: SPEC §23 (NF-33)
"""

from __future__ import annotations

import re
import unicodedata
from collections import deque
from dataclasses import dataclass
from enum import Enum

MAX_DESCRIZIONE_EMBED = 4096
MAX_VALORE_CAMPO = 1024
MAX_NOME_CANALE = 100
MAX_MOTIVO_CHIUSURA = 500
MAX_RISPOSTA = 2000
MAX_SERVER_NEL_MENU = 25

# Al massimo 5 messaggi ogni 10 secondi per utente: oltre, i DM si ignorano.
DM_MAX_MESSAGGI = 5
DM_FINESTRA_SECONDI = 10.0
_MAX_UTENTI_TRACCIATI = 5000

PREFISSO_CANALE = "modmail-"

_NON_AMMESSI = re.compile(r"[^a-z0-9-]+")


class Esito(Enum):
    NESSUN_SERVER = "nessun_server"
    UN_SERVER = "un_server"
    SCEGLI_SERVER = "scegli_server"


@dataclass(frozen=True)
class Decisione:
    esito: Esito
    guild_ids: tuple[int, ...] = ()


def decidi_server(candidati: list[int]) -> Decisione:
    """
    Dove aprire la conversazione di un utente che non ne ha una aperta.
    `candidati`: server in cui è membro, col ModMail acceso e dove non è bloccato.
    """
    unici = tuple(dict.fromkeys(candidati))
    if not unici:
        return Decisione(Esito.NESSUN_SERVER)
    if len(unici) == 1:
        return Decisione(Esito.UN_SERVER, unici)
    return Decisione(Esito.SCEGLI_SERVER, unici[:MAX_SERVER_NEL_MENU])


def nome_canale(nome_utente: str, user_id: int) -> str:
    """`modmail-<nome>`: solo minuscole, cifre e trattini, al massimo 100 caratteri. Senza nome usa l'id."""
    ascii_ = unicodedata.normalize("NFKD", nome_utente).encode("ascii", "ignore").decode()
    pulito = _NON_AMMESSI.sub("-", ascii_.lower()).strip("-")
    pulito = re.sub(r"-{2,}", "-", pulito) or str(user_id)
    return (PREFISSO_CANALE + pulito)[:MAX_NOME_CANALE].rstrip("-")


def taglia(testo: str, massimo: int) -> str:
    testo = testo.strip()
    if len(testo) <= massimo:
        return testo
    return testo[: massimo - 1].rstrip() + "…"


def testo_inoltrato(contenuto: str) -> str:
    """Il testo dell'utente nell'embed dello staff, entro 4096 caratteri."""
    return taglia(contenuto, MAX_DESCRIZIONE_EMBED)


def elenco_allegati(nomi_e_url: list[tuple[str, str]]) -> str:
    """Link agli allegati, uno per riga, entro 1024 caratteri (un campo di embed)."""
    righe: list[str] = []
    totale = 0
    for nome, url in nomi_e_url:
        riga = f"[{taglia(nome, 60)}]({url})"
        if totale + len(riga) + 1 > MAX_VALORE_CAMPO:
            righe.append("…")
            break
        righe.append(riga)
        totale += len(riga) + 1
    return "\n".join(righe)


def messaggio_vuoto(contenuto: str, quanti_allegati: int) -> bool:
    return not contenuto.strip() and quanti_allegati == 0


def etichetta_firma(anonimo: bool, nome_staff: str, nome_server: str) -> str:
    """Come si presenta lo staff all'utente."""
    if anonimo:
        return taglia(f"Staff di {nome_server}", 256)
    return taglia(f"{nome_staff} · {nome_server}", 256)


class LimitatoreDM:
    """Finestra scorrevole per utente. L'orologio si passa da fuori (provabile senza attese)."""

    def __init__(self, massimo: int = DM_MAX_MESSAGGI, finestra: float = DM_FINESTRA_SECONDI) -> None:
        self._massimo = massimo
        self._finestra = finestra
        self._eventi: dict[int, deque[float]] = {}

    def consenti(self, user_id: int, adesso: float) -> bool:
        coda = self._eventi.setdefault(user_id, deque())
        while coda and adesso - coda[0] >= self._finestra:
            coda.popleft()
        if len(coda) >= self._massimo:
            return False
        coda.append(adesso)
        if len(self._eventi) > _MAX_UTENTI_TRACCIATI:
            self._pulisci(adesso)
        return True

    def _pulisci(self, adesso: float) -> None:
        for chiave in [k for k, c in self._eventi.items() if not c or adesso - c[-1] >= self._finestra]:
            del self._eventi[chiave]
