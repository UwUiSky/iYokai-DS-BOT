"""
core/phishing_azione_logic.py
=============================
Azione in più sul filtro phishing (timeout, kick o ban), spenta di base. Solo logica pura:
lo scudo (staff, proprietario, chi sta sopra il bot) lo applica il motore unico di core/automod_azioni.py.
Funzioni coperte: SPEC SIC-041
"""

from __future__ import annotations

from core.automod_regole_logic import MAX_MOTIVO, MAX_TIMEOUT_S, Azione, azione_da_json

SCELTE = ("timeout", "kick", "ban")


def azione_extra(scelta: str, timeout_secondi: int) -> Azione | None:
    """L'azione scelta dal server; None se la funzione è spenta o il nome non è noto."""
    if scelta == "timeout":
        return azione_da_json({"t": "timeout", "secondi": min(max(int(timeout_secondi), 1), MAX_TIMEOUT_S)})
    if scelta in ("kick", "ban"):
        return azione_da_json({"t": scelta})
    return None


def aggiungi_extra(azioni: tuple[Azione, ...], scelta: str, timeout_secondi: int) -> tuple[Azione, ...]:
    """Le azioni della regola più quella in più, senza doppioni dello stesso tipo."""
    extra = azione_extra(scelta, timeout_secondi)
    if extra is None or any(a.t == extra.t for a in azioni):
        return tuple(azioni)
    return (*azioni, extra)


def motivo_extra(dettaglio: str) -> str:
    """Il motivo scritto nel caso di moderazione: al massimo 512 caratteri."""
    return f"AutoMod: link di phishing. {dettaglio}"[:MAX_MOTIVO]
