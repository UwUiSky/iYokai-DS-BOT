"""
core/immagini_qr_logic.py
=========================
Giudizio sul testo di un QR letto da un'immagine (D62): login con QR di Discord, siti di phishing,
accorciatori che nascondono la meta, link con frasi da truffa (finti regali Nitro e giveaway, in piu'
lingue: data/automod/truffe_*.txt) verso siti non ufficiali. Logica pura.
Funzioni coperte: SPEC §6 (D62)
Dipende da: core/phishing_logic.py
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from core import phishing_logic as ph

CARTELLA_TRUFFE = Path(__file__).resolve().parent.parent / "data" / "automod"
MAX_FRASI = 2000

QR_LOGIN = "qr_login_discord"
QR_PHISHING = "qr_phishing"
QR_ACCORCIATORE = "qr_accorciatore"
QR_TRUFFA = "qr_schema_truffa"

# Il QR di accesso di Discord porta a discord.com/ra/<codice>: chi lo scansiona con l'app dell'utente collega
# l'account del truffatore... al contrario, chi lo mostra vuole far entrare il truffatore nell'account della vittima.
_LOGIN_QR = re.compile(r"(?:^|[/.])discord(?:app)?\.com/ra/[\w-]+", re.IGNORECASE)


@lru_cache(maxsize=1)
def frasi_truffa() -> tuple[str, ...]:
    """Le frasi di tutti i file truffe_*.txt (le lingue si aggiungono con un file)."""
    frasi: list[str] = []
    try:
        for file in sorted(CARTELLA_TRUFFE.glob("truffe_*.txt")):
            for riga in file.read_text(encoding="utf-8").splitlines():
                riga = riga.split("#", 1)[0].strip().lower()
                if riga:
                    frasi.append(riga)
    except OSError:
        return ()
    return tuple(frasi[:MAX_FRASI])


@lru_cache(maxsize=1)
def _lista_phishing() -> frozenset[str]:
    return ph.carica_lista_locale()


def giudica_qr(testo: str) -> str | None:
    """Il codice del motivo se il testo del QR e' una truffa, altrimenti None."""
    if not isinstance(testo, str) or not testo.strip():
        return None
    testo = testo.strip()[:2000]
    if _LOGIN_QR.search(testo):
        return QR_LOGIN
    domini = ph.domini_nel_testo(testo)
    if not domini:
        return None
    if ph.e_phishing(domini, _lista_phishing()):
        return QR_PHISHING
    if ph.e_accorciatore(domini):
        return QR_ACCORCIATORE
    minuscolo = testo.lower()
    if any(frase in minuscolo for frase in frasi_truffa()) and not all(ph._ufficiale(d) for d in domini):
        return QR_TRUFFA
    return None


def giudica_qr_lista(testi: list[str]) -> str | None:
    """Il primo motivo trovato tra i QR di un'immagine."""
    for t in testi:
        motivo = giudica_qr(t)
        if motivo:
            return motivo
    return None
