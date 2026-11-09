"""
core/leveling_azzera_logic.py
=============================
Logica pura per azzerare gli XP (copia di sicurezza, azzeramento di chi esce o viene bannato,
blocco al proprietario) e per la diagnosi «perché non prendo XP». Niente oggetti discord.py.
Funzioni coperte: SPEC §15 (LIV-068, 069, 070, 071, 075; catalogo #124)
"""

from __future__ import annotations

from dataclasses import dataclass

GIORNI_COPIA = 30  # quanto vive una copia di sicurezza
MAX_COPIE_SERVER = 2  # copie dell'azzeramento di tutto il server: la nuova e la precedente
MAX_COPIE_ELENCO = 25  # tetto delle scelte di un menu
MAX_MOTIVO = 512
MAX_NOME_SERVER = 100  # tetto del nome di un server su Discord
SECONDI_ATTESA_BAN = 3  # chi esce e poi risulta bannato: si aspetta l'evento del ban


def nome_confermato(scritto: str, nome_server: str) -> bool:
    """Il nome scritto a mano è quello del server (spazi e maiuscole non contano)."""
    scritto = " ".join(scritto.split()).casefold()
    return bool(scritto) and scritto == " ".join(nome_server.split()).casefold()


def rifiutato_dal_blocco(bloccato: bool, user_id: int, owner_id: int | None) -> bool:
    """
    LIV-071: con il blocco acceso solo il proprietario del server (`guild.owner_id`, non l'owner
    del bot) può usare il comando. Punto unico, usato dai comandi e dal futuro pannello web.
    """
    return bloccato and (owner_id is None or user_id != owner_id)


def deve_azzerare(azzera_su: str, evento: str) -> bool:
    """LIV-070: `evento` è «uscita» o «ban»; `azzera_su` è la scelta del server."""
    return azzera_su == "entrambi" or azzera_su == evento


@dataclass(frozen=True)
class Verifica:
    """Un controllo della diagnosi: `ok` vero = non è questo il motivo."""

    chiave: str
    ok: bool
    valore: int = 0


def diagnosi_xp(
    *,
    modulo_attivo: bool,
    in_blacklist: bool,
    e_bot: bool,
    canale_escluso: bool,
    ruolo_escluso: bool,
    attesa_secondi: int,
    livello: int,
    max_level: int,
) -> list[Verifica]:
    """LIV-075: i controlli che l'XP testuale fa davvero, nello stesso ordine."""
    controlli: list[Verifica] = []
    if e_bot:
        controlli.append(Verifica("bot", False))
    controlli += [
        Verifica("modulo", modulo_attivo),
        Verifica("blacklist", not in_blacklist),
        Verifica("canale", not canale_escluso),
        Verifica("ruolo", not ruolo_escluso),
        Verifica("attesa", attesa_secondi <= 0, max(attesa_secondi, 0)),
        Verifica("tetto", not (max_level and livello >= max_level), max_level),
    ]
    return controlli
