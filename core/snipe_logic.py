"""
core/snipe_logic.py
=======================
Logica pura per Snipe ed Editsnipe (SPEC.md §14.9, §14.10), Reactionsnipe
(§14.11) e Ghost ping detection (§14.12) — solo stringhe, numeri e date,
niente discord.py.

Snipe ed Editsnipe mostrano il testo del messaggio: servono il Message
Content Intent (acceso, D9). Restano in memoria per pochi minuti e non
vengono mai scritti su disco. Reactionsnipe e Ghost ping non leggono il
testo: usano emoji, autore e l'elenco dei membri menzionati, che Discord
manda sempre.
Funzioni coperte: SPEC §14.9-§14.12 (NF-03, M 5.9)
"""

from __future__ import annotations

from datetime import datetime

SNIPE_TTL_SECONDS = 5 * 60
DESCRIZIONE_MAX = 4096
# Un'azione del registro di controllo vale se è di pochi secondi fa (LIM-31).
AUDIT_FINESTRA_SECONDI = 10


def scaduto(creato: datetime, adesso: datetime, ttl: int = SNIPE_TTL_SECONDS) -> bool:
    """True se il messaggio ricordato ha più di `ttl` secondi."""
    return (adesso - creato).total_seconds() > ttl


def testo_snipe(content: str, nomi_allegati: list[str]) -> str:
    """Il testo da mostrare: contenuto (tagliato a 4096) e allegati; mai vuoto."""
    parti = [content] if content else []
    if nomi_allegati:
        parti.append("📎 " + ", ".join(nomi_allegati))
    testo = "\n".join(parti) or "*(nessun testo)*"
    if len(testo) > DESCRIZIONE_MAX:
        testo = testo[: DESCRIZIONE_MAX - 1] + "…"
    return testo


def cancellato_da_altri(
    voci: list[tuple[int | None, int | None, int | None, float]],
    author_id: int,
    channel_id: int,
) -> bool:
    """
    True se il registro di controllo dice che un messaggio dell'autore è stato
    cancellato in quel canale da qualcun altro (un moderatore) poco fa.
    Ogni voce è (chi ha cancellato, di chi era il messaggio, canale, secondi fa).
    """
    return any(
        eseguito_da is not None
        and eseguito_da != author_id
        and bersaglio == author_id
        and canale == channel_id
        and eta <= AUDIT_FINESTRA_SECONDI
        for eseguito_da, bersaglio, canale, eta in voci
    )


def is_ghost_ping_candidate(
    mentioned_user_ids: list[int], mentions_everyone: bool, author_is_bot: bool
) -> bool:
    """
    Un messaggio va tracciato per il ghost ping se menziona almeno
    un utente (o @everyone/@here) e non è stato scritto da un bot
    (i messaggi automatici del bot stesso, o di altri bot, non
    contano come "ghost ping" di un membro).
    """
    if author_is_bot:
        return False
    return bool(mentioned_user_ids) or mentions_everyone
