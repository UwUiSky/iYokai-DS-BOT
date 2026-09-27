"""
core/clan_leaderboard_logic.py
==================================
Logica pura dell'annuncio automatico della classifica MENSILE di
gilda in "bacheca clan" (SPEC.md §15.10 — richiesta esplicita
dell'utente: "ogni mese, il bot pubblica in bacheca clan la top 3").
Il calcolo di QUALE mese annunciare è IDENTICO a quello
dell'annuncio vincitori personale (core.monthly_winners_logic:
previous_period_key/should_announce sono generici, non specifici
alla classifica personale) — riusati direttamente qui, non
duplicati. Solo il testo del podio cambia (clan invece di membri).

Nessuna rete o Discord qui dentro.
"""

from __future__ import annotations

from core.monthly_winners_logic import (
    format_period_label,
    previous_period_key,
    should_announce,
)

__all__ = [
    "format_period_label",
    "previous_period_key",
    "should_announce",
    "PODIUM_SIZE",
    "MEDALS",
    "format_clan_podium",
    "build_clan_announcement_text",
]

MEDALS = ("🥇", "🥈", "🥉")

PODIUM_SIZE = 3


def format_clan_podium(entries: list[tuple[str, str, int]]) -> str:
    """
    entries: lista di (tag, nome, xp_guadagnata) già ordinata dal
    repository (get_monthly_clan_leaderboard). Restituisce le righe
    del podio con medaglie, o un testo esplicito se nessuna gilda ha
    guadagnato XP quel mese (un annuncio vuoto senza spiegazione
    sembrerebbe un errore del bot — stessa scelta di
    monthly_winners_logic.format_podium).
    """
    if not entries:
        return "_Nessuna gilda ha guadagnato XP questo mese._"

    righe = []
    for posizione, (tag, nome, xp) in enumerate(entries[:PODIUM_SIZE]):
        righe.append(f"{MEDALS[posizione]} **[{tag}] {nome}** — **{xp}** XP")
    return "\n".join(righe)


def build_clan_announcement_text(
    period: str, top_clans: list[tuple[str, str, int]]
) -> tuple[str, str]:
    """(titolo, podio) — il chiamante li monta in un embed, qui
    restano testo puro."""
    titolo = f"🏆 Top 3 gilde di {format_period_label(period)}"
    return titolo, format_clan_podium(top_clans)
