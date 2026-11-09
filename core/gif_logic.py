"""
core/gif_logic.py
=================
Regole delle GIF di azione senza Discord: chi può fare l'azione a chi (bot, sé stessi, privacy del
bersaglio) e le frasi di accompagnamento.
Funzioni coperte: SPEC §16 (FUN-110..135, 137; #131)
Dipende da: core/repositories/gif_privacy_repo.py
"""

from __future__ import annotations

import hashlib
import re

from core.gif_catalogo import Voce
from core.gif_fonti import FONTI_RICERCA, categoria_sfw
from core.i18n import t

MAX_TESTO = 200  # testo libero accanto alla GIF di reazione
MAX_RICERCA = 50
TEMI_RICERCA = {"anime": "anime", "gaming": "video game", "animali": "animals", "meme": "meme", "cibo": "food"}


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


def voce_di_ricerca(testo: str, tema: str | None = None) -> Voce | None:
    """La «voce» per `/gif cerca`: solo la ricerca libera dei servizi con chiave. None se il testo è vuoto o per adulti."""
    pulito = re.sub(r"\s+", " ", (testo or "").strip())[:MAX_RICERCA]
    if tema in TEMI_RICERCA:
        pulito = f"{pulito} {TEMI_RICERCA[tema]}"[: MAX_RICERCA + 12]
    if not pulito or not categoria_sfw(pulito):
        return None
    impronta = hashlib.sha1(pulito.casefold().encode("utf-8")).hexdigest()[:12]
    return Voce(f"cerca-{impronta}", "", "cerca", {}, (), pulito, {})


def ricerca_disponibile(nomi_fonti) -> bool:
    """Vero se almeno una fonte accesa sa cercare testo libero (oggi: Giphy con la sua chiave)."""
    return any(n in FONTI_RICERCA for n in nomi_fonti)
