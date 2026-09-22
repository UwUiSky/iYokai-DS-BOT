"""
core/monthly_winners_logic.py
=================================
Logica pura dell'annuncio automatico dei vincitori a fine mese
(SPEC.md §15.11). La classifica mensile esiste già (period_key in
core/leveling_logic.py, top_xp_period/top_coins_period nel
repository accettano già un periodo arbitrario) — qui solo: calcolare
QUALE mese annunciare, e costruire il testo.

Nessuna rete o Discord qui dentro.
"""

from __future__ import annotations

from datetime import datetime, timezone

from core.leveling_logic import period_key

# Condivisa con /leaderboard (cogs/leveling/leveling.py) — un solo
# punto che definisce le medaglie del podio.
MEDALS = ("🥇", "🥈", "🥉")

PODIUM_SIZE = 3

MESI_ITALIANI = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)


def previous_period_key(now: datetime | None = None) -> str:
    """
    Il period_key del mese PRECEDENTE a `now` — quello appena
    concluso, da annunciare. Gestisce il passaggio d'anno
    (gennaio 2027 -> "2026-12").
    """
    moment = now or datetime.now(timezone.utc)
    if moment.month == 1:
        return f"{moment.year - 1:04d}-12"
    return f"{moment.year:04d}-{moment.month - 1:02d}"


def should_announce(last_announced_period: str | None, now: datetime | None = None) -> bool:
    """
    Vero se il mese appena concluso non è ancora stato annunciato.
    Idempotente per costruzione: il periodo annunciato viene salvato
    nel database, quindi un riavvio del bot (o più tick nella stessa
    giornata) non produce annunci doppi — l'annuncio arriva UNA volta
    per mese, al primo tick utile dopo la mezzanotte UTC del primo
    giorno del mese.
    """
    return last_announced_period != previous_period_key(now)


def format_period_label(period: str) -> str:
    """ "2026-09" -> "settembre 2026" (per il titolo dell'annuncio)."""
    anno, mese = period.split("-")
    return f"{MESI_ITALIANI[int(mese) - 1]} {anno}"


def format_podium(entries: list[tuple[int, int]], unit: str) -> str:
    """
    entries: lista di (user_id, amount) già ordinata dal repository.
    Restituisce le righe del podio con medaglie, o un testo esplicito
    se nessuno ha partecipato quel mese (un annuncio vuoto senza
    spiegazione sembrerebbe un errore del bot).
    """
    if not entries:
        return "_Nessuna attività registrata questo mese._"

    righe = []
    for posizione, (user_id, amount) in enumerate(entries[:PODIUM_SIZE]):
        righe.append(f"{MEDALS[posizione]} <@{user_id}> — **{amount}** {unit}")
    return "\n".join(righe)


def build_announcement_text(
    period: str,
    top_xp: list[tuple[int, int]],
    top_coins: list[tuple[int, int]],
) -> tuple[str, str, str]:
    """(titolo, podio_xp, podio_coin) — il chiamante li monta in un
    embed, qui restano testo puro."""
    titolo = f"🏆 Vincitori di {format_period_label(period)}"
    return titolo, format_podium(top_xp, "XP"), format_podium(top_coins, "coin")
