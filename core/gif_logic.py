"""
core/gif_logic.py
=================
Regole delle GIF di azione senza Discord: chi può fare l'azione a chi (bot, sé stessi, privacy del
bersaglio) e le frasi di accompagnamento.
Funzioni coperte: SPEC §16 (FUN-110..135, 137; #131)
Dipende da: core/repositories/gif_privacy_repo.py
"""

from __future__ import annotations

from core.gif_catalogo import Voce
from core.i18n import t

MAX_TESTO = 200  # testo libero accanto alla GIF di reazione


async def esito_azione(repo, autore_id: int, bersaglio_id: int, bersaglio_e_bot: bool) -> str | None:
    """None se l'azione si può fare, altrimenti la chiave del testo che spiega perché no."""
    if bersaglio_e_bot:
        return "gif_bot"
    if autore_id == bersaglio_id:
        return "gif_te_stesso"
    if await repo.e_bloccato(bersaglio_id, autore_id):
        return "gif_bloccata"
    return None


def frase(voce: Voce, lingua: str, autore: str, bersaglio: str = "", testo: str | None = None) -> str:
    """La frase pubblica («X abbraccia Y»). Il testo libero va dopo, mai dentro la frase."""
    base = t(voce.chiave_frase, lingua, autore=autore, bersaglio=bersaglio)
    return f"{base}\n{testo.strip()[:MAX_TESTO]}" if testo and testo.strip() else base
