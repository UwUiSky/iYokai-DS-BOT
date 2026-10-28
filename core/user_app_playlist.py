"""
core/user_app_playlist.py
=========================
Playlist personali di iYokai App e «cosa ascolto» (SPEC B.8, C17, C18): il nome e il brano si controllano
qui, senza Discord. I testi delle canzoni non si copiano (diritti): si dà il link di ricerca.
Funzioni coperte: SPEC B.8 (C17, C18; #107)
Dipende da: core/user_app_risposte.py, core/user_app_strumenti.py
"""

from __future__ import annotations

from urllib.parse import quote_plus

from core.user_app_risposte import normalizza_nome
from core.user_app_strumenti import ErroreStrumento

MAX_BRANO = 100


def nome_playlist(nome: str) -> str:
    """Il nome come si salva (stesse regole delle risposte). Non valido = ErroreStrumento."""
    try:
        return normalizza_nome(nome)
    except ErroreStrumento as errore:
        raise ErroreStrumento("app_playlist_nome_non_valido") from errore


def pulisci_brano(brano: str) -> str:
    """Il brano su una riga sola, da 1 a 100 caratteri. Altro = ErroreStrumento."""
    pulito = " ".join((brano or "").split())
    if not pulito or len(pulito) > MAX_BRANO:
        raise ErroreStrumento("app_playlist_brano_non_valido")
    return pulito


def link_testo(titolo: str) -> str:
    """Dove cercare il testo del brano (ricerca, non copia)."""
    return "https://genius.com/search?q=" + quote_plus(titolo[:MAX_BRANO])


def righe_playlist(brani: list[str]) -> str:
    """Elenco numerato, tagliato per stare in una descrizione di embed."""
    testo = "\n".join(f"{n}. {b}" for n, b in enumerate(brani, 1))
    return testo[:4000]
