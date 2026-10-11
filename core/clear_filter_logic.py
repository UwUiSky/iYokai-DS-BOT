"""
core/clear_filter_logic.py
==========================
Filtri di /mod clear, scritti come funzione semplice sui dati di un
messaggio: si provano senza Discord.
Funzioni coperte: SPEC §5.7 (MOD-069, 071, 073-079, 083, 084, 086)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_LINK = re.compile(r"https?://\S+", re.IGNORECASE)
_INVITO = re.compile(
    r"(?:discord\.gg|discord(?:app)?\.com/invite)/[\w-]+", re.IGNORECASE
)


@dataclass(frozen=True)
class FiltriClear:
    autore_id: int | None = None
    solo_bot: bool = False
    solo_persone: bool = False
    solo_allegati: bool = False
    contiene: str | None = None
    non_contiene: str | None = None
    solo_link: bool = False
    solo_inviti: bool = False
    solo_embed: bool = False
    solo_menzioni: bool = False
    ruolo_id: int | None = None
    salta_fissati: bool = False


def messaggio_passa(msg, filtri: FiltriClear) -> bool:
    """True se il messaggio va cancellato: deve rispettare tutti i filtri attivi."""
    testo = (msg.content or "").lower()
    if filtri.salta_fissati and getattr(msg, "pinned", False):
        return False
    if filtri.autore_id is not None and msg.author.id != filtri.autore_id:
        return False
    # Un webhook conta come bot: non è una persona.
    e_bot = bool(msg.author.bot) or getattr(msg, "webhook_id", None) is not None
    if filtri.solo_bot and not e_bot:
        return False
    if filtri.solo_persone and e_bot:
        return False
    if filtri.solo_allegati and not msg.attachments:
        return False
    if filtri.contiene and filtri.contiene.lower() not in testo:
        return False
    if filtri.non_contiene and filtri.non_contiene.lower() in testo:
        return False
    if filtri.solo_link and not _LINK.search(msg.content or ""):
        return False
    if filtri.solo_inviti and not _INVITO.search(msg.content or ""):
        return False
    if filtri.solo_embed and not msg.embeds:
        return False
    if filtri.solo_menzioni and not (msg.mentions or getattr(msg, "role_mentions", None)):
        return False
    if filtri.ruolo_id is not None:
        ruoli = getattr(msg.author, "roles", [])
        if not any(r.id == filtri.ruolo_id for r in ruoli):
            return False
    return True


def descrivi_filtri(filtri: FiltriClear) -> str:
    """Riassunto breve dei filtri attivi, per il log."""
    parti = []
    if filtri.autore_id:
        parti.append(f"autore {filtri.autore_id}")
    for nome, attivo in (
        ("solo bot", filtri.solo_bot),
        ("solo persone", filtri.solo_persone),
        ("solo allegati", filtri.solo_allegati),
        ("solo link", filtri.solo_link),
        ("solo inviti", filtri.solo_inviti),
        ("solo embed", filtri.solo_embed),
        ("solo menzioni", filtri.solo_menzioni),
        ("salta fissati", filtri.salta_fissati),
    ):
        if attivo:
            parti.append(nome)
    if filtri.contiene:
        parti.append(f"contiene «{filtri.contiene}»")
    if filtri.non_contiene:
        parti.append(f"non contiene «{filtri.non_contiene}»")
    if filtri.ruolo_id:
        parti.append(f"ruolo {filtri.ruolo_id}")
    return ", ".join(parti) or "nessun filtro"
