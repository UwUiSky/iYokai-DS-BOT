"""
core/moderation_casi_esterni_logic.py
=====================================
Dal registro di controllo di Discord al caso di moderazione: ban, kick e
timeout fatti dal menu di Discord o da altri bot entrano nei casi del server
(se il server lo ha acceso con `/mod opzioni imposta casi_esterni:`).
Funzioni coperte: SPEC §5.2 (MOD-047)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

SETTING_CASI_ESTERNI = "mod_casi_esterni"
MOTIVO_PREDEFINITO = "Azione fatta fuori da iYokai (registro di controllo di Discord)"
MAX_MOTIVO = 512
# Tipi di caso che un'azione esterna può aprire (l'unban chiude, non apre).
ACTION_TYPE_POSSIBILI = ("ban", "kick", "timeout")


@dataclass(frozen=True)
class CasoEsterno:
    tipo: str  # ban | kick | timeout | unban
    motivo: str
    durata_secondi: int | None = None


def caso_da_voce(
    azione: str,
    motivo: str | None,
    *,
    timeout_fino: datetime | None = None,
    ora: datetime | None = None,
) -> CasoEsterno | None:
    """
    `azione` è il nome dell'azione del registro (ban, kick, unban, member_update).
    member_update conta solo se mette un timeout (`timeout_fino` nel futuro).
    Qualsiasi altra voce non è una sanzione: None.
    """
    testo = (motivo or "").strip()[:MAX_MOTIVO] or MOTIVO_PREDEFINITO
    if azione in ("ban", "kick", "unban"):
        return CasoEsterno(azione, testo)
    if azione == "member_update" and timeout_fino is not None and ora is not None and timeout_fino > ora:
        return CasoEsterno("timeout", testo, int((timeout_fino - ora).total_seconds()))
    return None
