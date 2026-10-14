"""
core/moderation_bulk_logic.py
=============================
Azioni di moderazione su più utenti insieme: lettura dell'elenco (ID o
menzioni) e riepilogo dell'esito. Senza Discord.
Funzioni coperte: SPEC §5.1 (MOD-002…006)
"""

from __future__ import annotations

import re

# Utenti al massimo in un comando: ognuno costa una o due chiamate a Discord.
MAX_UTENTI_MASSA = 50
# Testo dell'opzione con gli utenti: 50 menzioni da 22 caratteri più separatori.
MAX_TESTO_UTENTI = 1500

_ID = re.compile(r"(?<!\d)(\d{15,20})(?!\d)")


def leggi_utenti(testo: str) -> tuple[list[int], bool]:
    """
    Gli ID utente nel testo (menzioni o numeri, separati come si vuole),
    senza doppioni e nell'ordine scritto. Il secondo valore è True se
    l'elenco superava MAX_UTENTI_MASSA ed è stato tagliato.
    """
    visti: list[int] = []
    for grezzo in _ID.findall(testo or ""):
        uid = int(grezzo)
        if uid not in visti:
            visti.append(uid)
    return visti[:MAX_UTENTI_MASSA], len(visti) > MAX_UTENTI_MASSA


def riepilogo(fatti: list[str], saltati: list[str], limite: int = 3900) -> str:
    """Testo del riepilogo: chi è stato toccato e chi è stato saltato, con il motivo."""
    righe = [f"✅ {len(fatti)} fatti"] + [f"• {r}" for r in fatti]
    if saltati:
        righe += [f"⏭️ {len(saltati)} saltati"] + [f"• {r}" for r in saltati]
    testo = "\n".join(righe)
    return testo if len(testo) <= limite else testo[: limite - 1] + "…"
