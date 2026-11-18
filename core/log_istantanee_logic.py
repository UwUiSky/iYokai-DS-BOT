"""
core/log_istantanee_logic.py
============================
Logica pura delle istantanee di un canale consultabili sul pannello web (LOG-028): il segreto del link, chi può
vedere, quali righe entrano. Il segreto non si salva mai: solo la sua impronta. Il testo dei messaggi è già
quello del log (solo nomi dei file allegati, mai i file, D74); qui si pulisce e si taglia.
Funzioni coperte: SPEC §8.21 (LOG-028)
Dipende da: core/message_log_logic.py
"""

from __future__ import annotations

import hashlib
import re
import secrets
import unicodedata

from core.message_log_logic import MessaggioArchiviato
from core.testo_limiti import tronca

ACCESSI = ("gestori", "ruolo", "membri")
MESSAGGI_BASE = 100
MESSAGGI_MAX = 200
GIORNI_BASE = 3
GIORNI_MAX = 7
ATTIVE_MAX_PER_SERVER = 5
TESTO_RIGA_MAX = 2000
NOME_AUTORE_MAX = 100
BYTE_TOTALI_MAX = 1024 * 1024  # il testo di una istantanea
TOKEN_LUNGHEZZA = 43  # secrets.token_urlsafe(32)
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")


def nuovo_segreto() -> str:
    """Il segreto del link: 256 bit casuali."""
    return secrets.token_urlsafe(32)


def segreto_valido(segreto: str) -> bool:
    return bool(_TOKEN.fullmatch(segreto or ""))


def impronta(segreto: str) -> str:
    """Ciò che si salva al posto del segreto."""
    return hashlib.sha256(segreto.encode("utf-8")).hexdigest()


def puo_vedere(accesso: str, role_id: int | None, *, e_gestore: bool, e_membro: bool, ruoli_membro: frozenset[int]) -> bool:
    """
    Chi gestisce il server vede sempre. «gestori»: nessun altro. «ruolo»: chi è nel server e ha quel ruolo.
    «membri»: chi è nel server e ha il link (serve comunque l'accesso con Discord). Un valore sconosciuto: no.
    """
    if e_gestore:
        return True
    if accesso == "ruolo":
        return bool(e_membro and role_id is not None and role_id in ruoli_membro)
    if accesso == "membri":
        return e_membro
    return False


def _pulisci(testo: str, a_capo: bool) -> str:
    """Senza caratteri di controllo, di formato (inversioni di testo, invisibili) né a capo scorretti."""
    uscita = []
    for c in unicodedata.normalize("NFKC", testo):
        if c == "\n" and a_capo:
            uscita.append(c)
        elif c in "\r\t":
            uscita.append(" ")
        elif unicodedata.category(c)[0] != "C":
            uscita.append(c)
    return "".join(uscita)


def righe_istantanea(messaggi: list[MessaggioArchiviato], cancellati: list[MessaggioArchiviato]) -> list[dict]:
    """
    Le righe in ordine di tempo (per id), i cancellati di recente segnati. Si ferma a BYTE_TOTALI_MAX di testo.
    Ogni testo e nome è pulito e tagliato.
    """
    unite = [(m, False) for m in messaggi] + [(m, True) for m in cancellati]
    unite.sort(key=lambda x: x[0].message_id)
    righe, usati = [], 0
    for m, cancellato in unite:
        testo = tronca(_pulisci(m.testo, True), TESTO_RIGA_MAX)
        nome = tronca(_pulisci(m.author_nome, False).strip() or "sconosciuto", NOME_AUTORE_MAX)
        usati += len(testo.encode("utf-8")) + len(nome.encode("utf-8")) + 64
        if usati > BYTE_TOTALI_MAX:
            break
        righe.append({
            "message_id": m.message_id, "author_id": m.author_id, "autore_nome": nome,
            "quando": tronca(_pulisci(m.quando, False), 32), "testo": testo, "cancellato": cancellato,
        })
    return righe
