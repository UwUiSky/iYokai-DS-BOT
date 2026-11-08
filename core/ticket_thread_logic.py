"""
core/ticket_thread_logic.py
===========================
Regole pure dei ticket come thread privati (TKT-031, TKT-032): tetto dei thread attivi, nome,
permessi che servono al bot nel canale padre. Niente oggetti Discord: il cog passa numeri e permessi.
Funzioni coperte: SPEC §13.25
"""

from __future__ import annotations

MAX_THREAD_ATTIVI = 1000  # Discord: thread attivi per server
MAX_NOME_THREAD = 100
ARCHIVIO_MINUTI = 10080  # 7 giorni: il massimo di Discord senza livello del server
TIPI = ("canale", "thread")
# Permesso -> nome in italiano, per dire all'admin cosa manca al bot nel canale padre.
PERMESSI_BOT: dict[str, str] = {
    "view_channel": "Vedere il canale",
    "create_private_threads": "Creare thread privati",
    "send_messages_in_threads": "Scrivere nei thread",
    "manage_threads": "Gestire i thread",
}


def controlla_thread(attivo: bool | None, canale_padre_id: int | None) -> None:
    """Accendere i ticket a thread senza un canale padre non ha senso: ValueError col testo per l'admin."""
    if attivo and canale_padre_id is None:
        raise ValueError("Per i ticket come thread scegli anche `canale_thread` (il canale dove nascono).")


def nome_thread(nome: str) -> str:
    """Il nome del thread: al massimo 100 caratteri, mai vuoto."""
    return (nome.strip() or "ticket")[:MAX_NOME_THREAD]


def tetto_raggiunto(attivi: int) -> bool:
    """Il server ha già 1.000 thread attivi: Discord non ne fa nascere altri."""
    return attivi >= MAX_THREAD_ATTIVI


def permessi_mancanti(permessi) -> list[str]:
    """I permessi del bot che mancano nel canale padre (nomi in italiano)."""
    return [nome for chiave, nome in PERMESSI_BOT.items() if not getattr(permessi, chiave, False)]


def chi_aggiungere(user_id: int, reperibili: list[int], massimo: int = 10) -> list[int]:
    """Chi entra subito nel thread: chi lo apre e i reperibili (senza doppioni, al massimo `massimo`)."""
    visti: dict[int, None] = {user_id: None}
    for uid in reperibili:
        if len(visti) > massimo:
            break
        visti.setdefault(uid, None)
    return list(visti)
