"""
core/desktop_logic.py
=====================
Regole pure di iYokai Desktop (SPEC D.1, D.5, D.6): token personale (solo l'impronta si salva), parole chiave,
chi va avvisato per un messaggio, link per saltare al messaggio. Niente Discord e niente database qui.
Funzioni coperte: SPEC D.1, D.5, D.6 (#108)
"""

from __future__ import annotations

import hashlib
import re
import secrets
from collections.abc import Callable, Iterable

PREFISSO_TOKEN = "dsk_"
_TOKEN = re.compile(r"^dsk_[A-Za-z0-9_-]{43}$")

MAX_PAROLE = 10
MIN_PAROLA = 2
MAX_PAROLA = 30
MAX_TESTO_EVENTO = 140
MAX_EVENTI_PER_UTENTE = 500

TIPO_MENZIONE = "menzione"
TIPO_RISPOSTA = "risposta"
TIPO_PAROLA = "parola"
TIPI_EVENTO = (TIPO_MENZIONE, TIPO_RISPOSTA, TIPO_PAROLA, "promemoria", "assistenza", "staff")


class ErroreDesktop(Exception):
    """Un errore da dire alla persona: `chiave` è la chiave del catalogo."""

    def __init__(self, chiave: str) -> None:
        super().__init__(chiave)
        self.chiave = chiave


def nuovo_token() -> str:
    """Un token nuovo: si mostra una volta sola e non si salva."""
    return PREFISSO_TOKEN + secrets.token_urlsafe(32)


def impronta(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_ben_formato(token: str | None) -> bool:
    return bool(token) and bool(_TOKEN.match(token))


def token_dall_intestazione(intestazione: str | None) -> str | None:
    """Il token di `Authorization: Bearer …`, o None se manca o ha un aspetto diverso."""
    if not intestazione:
        return None
    parti = intestazione.split(" ", 1)
    if len(parti) != 2 or parti[0].lower() != "bearer":
        return None
    token = parti[1].strip()
    return token if token_ben_formato(token) else None


def normalizza_parole(testo: str) -> list[str]:
    """Le parole chiave da un testo con virgole o a capo: minuscole, senza doppioni. Troppe o storte = errore."""
    viste: list[str] = []
    for pezzo in re.split(r"[,\n]", testo or ""):
        parola = " ".join(pezzo.lower().split())
        if not parola:
            continue
        if not MIN_PAROLA <= len(parola) <= MAX_PAROLA:
            raise ErroreDesktop("app_desktop_parola_non_valida")
        if parola not in viste:
            viste.append(parola)
    if len(viste) > MAX_PAROLE:
        raise ErroreDesktop("app_desktop_troppe_parole")
    return viste


def testo_breve(testo: str | None) -> str:
    """Il testo del messaggio su una riga, corto (si conserva 90 giorni)."""
    riga = " ".join((testo or "").split())
    return riga if len(riga) <= MAX_TESTO_EVENTO else riga[: MAX_TESTO_EVENTO - 1] + "…"


def link_messaggio(guild_id: int | None, channel_id: int, message_id: int) -> str:
    """Il link che apre il messaggio nel client Discord (anche dal browser)."""
    return f"https://discord.com/channels/{guild_id if guild_id else '@me'}/{channel_id}/{message_id}"


def _contiene(testo: str, parola: str) -> bool:
    """La parola intera (non un pezzo di un'altra parola)."""
    return re.search(r"(?<!\w)" + re.escape(parola) + r"(?!\w)", testo) is not None


def chi_avvisare(
    *,
    autore_id: int,
    contenuto: str,
    menzionati: Iterable[int],
    risposta_a: int | None,
    attivi: dict[int, list[str]],
    vede: Callable[[int], bool],
) -> dict[int, str]:
    """
    Per un messaggio: {utente: tipo di avviso}. `attivi`: chi ha acceso gli avvisi con le sue parole chiave.
    `vede(utente)`: la persona è nel server e può vedere il canale (si guarda solo per chi sarebbe avvisato).
    Un solo avviso a persona: risposta, poi menzione, poi parola. Mai l'autore a se stesso.
    """
    candidati: dict[int, str] = {}
    if risposta_a is not None and risposta_a in attivi:
        candidati[risposta_a] = TIPO_RISPOSTA
    for utente in menzionati:
        if utente in attivi:
            candidati.setdefault(utente, TIPO_MENZIONE)
    minuscolo = (contenuto or "").lower()
    for utente, parole in attivi.items():
        if utente not in candidati and any(_contiene(minuscolo, p) for p in parole):
            candidati[utente] = TIPO_PAROLA
    return {u: tipo for u, tipo in candidati.items() if u != autore_id and vede(u)}
