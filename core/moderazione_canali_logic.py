"""
core/moderazione_canali_logic.py
================================
Regole semplici per canali, nomi e nuovi arrivati: slowmode lungo (oltre le 6 ore di Discord), canali di una
categoria, nickname, chi è entrato da poco. Nessun accesso a Discord.
Funzioni coperte: SPEC §5.6 (MOD-098, 099, 100), MOD-101, MOD-007
"""

from __future__ import annotations

from datetime import datetime, timedelta

from core.duration_logic import parse_duration

MAX_SLOWMODE_NATIVO = 21600  # 6 ore: il massimo di Discord
MAX_SLOWMODE_LUNGO = 7 * 86400
MAX_CANALI_CATEGORIA = 50
MAX_CANALI_LUNGHI = 50
MAX_NICK = 32
MAX_ENTRATI = 200
SECONDI_FRA_AVVISI = 600  # un avviso al massimo ogni 10 minuti per utente


def secondi_slowmode_lungo(testo: str) -> int:
    """I secondi di uno slowmode lungo (da oltre 6 ore a 7 giorni). ValueError se fuori misura o non è una durata."""
    secondi = parse_duration(testo)
    if secondi <= MAX_SLOWMODE_NATIVO or secondi > MAX_SLOWMODE_LUNGO:
        raise ValueError("lungo")
    return secondi


def deve_cancellare(ultimo: datetime | None, adesso: datetime, secondi: int) -> bool:
    """True se l'ultimo messaggio dell'utente è troppo recente per lo slowmode lungo."""
    return ultimo is not None and adesso - ultimo < timedelta(seconds=secondi)


def puo_avvisare(ultimo_avviso: float | None, adesso: float) -> bool:
    return ultimo_avviso is None or adesso - ultimo_avviso >= SECONDI_FRA_AVVISI


def canali_della_categoria(categoria) -> list:
    """I canali di testo della categoria, al massimo MAX_CANALI_CATEGORIA."""
    return list(categoria.text_channels)[:MAX_CANALI_CATEGORIA]


def nickname_valido(nuovo: str | None) -> bool:
    return nuovo is not None and 1 <= len(nuovo) <= MAX_NICK


def entrati_da_poco(membri, minuti: int, adesso: datetime) -> tuple[list, int]:
    """
    I membri entrati negli ultimi `minuti` minuti, i più recenti per primi, al massimo MAX_ENTRATI;
    il secondo valore dice quanti restano fuori dal tetto. Chi non ha la data di ingresso si ignora.
    """
    limite = adesso - timedelta(minutes=minuti)
    recenti = sorted((m for m in membri if m.joined_at is not None and m.joined_at >= limite), key=lambda m: m.joined_at, reverse=True)
    scelti = recenti[:MAX_ENTRATI]
    return scelti, len(recenti) - len(scelti)
