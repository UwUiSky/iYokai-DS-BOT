"""
core/giveaway_logic.py
======================
Logica pura del giveaway: scelta dei vincitori (anche con più biglietti per
alcuni ruoli), requisiti di partecipazione (livello, ruolo, messaggi, ruolo
che li salta) e testi dell'annuncio. random.Random è iniettato dal
chiamante, così l'estrazione è provabile con un seme fisso.
Funzioni coperte: SPEC §15.5, §23.6 (NF-28)
"""

from __future__ import annotations

import random

MAX_PREMIO_GIVEAWAY = 200
MAX_INGRESSI_EXTRA = 20
MAX_MESSAGGI_RICHIESTI = 100_000
MAX_MODELLI_PER_SERVER = 25


def pick_winners_pesati(
    entries: list[tuple[int, int]], winners_count: int, rng: random.Random
) -> list[int]:
    """
    Estrae i vincitori: ogni partecipante ha tanti biglietti quanti ne dice
    la coppia (utente, biglietti). Un utente vince una volta sola: dopo ogni
    estrazione i suoi biglietti escono dall'urna.
    """
    urna = [(uid, max(1, biglietti)) for uid, biglietti in entries]
    vincitori: list[int] = []
    while urna and len(vincitori) < winners_count:
        scelto = rng.choices(range(len(urna)), weights=[b for _, b in urna])[0]
        vincitori.append(urna.pop(scelto)[0])
    return vincitori


def biglietti_di(user_role_ids: set[int], bonus_role_id: int | None, bonus_entries: int) -> int:
    """Quanti biglietti ha chi entra: uno, più quelli extra se ha il ruolo."""
    if bonus_role_id is not None and bonus_role_id in user_role_ids:
        return 1 + max(0, bonus_entries)
    return 1


def requisiti_mancanti(
    user_level: int,
    user_role_ids: set[int],
    min_level: int,
    required_role_id: int | None,
    messages: int = 0,
    min_messages: int = 0,
    bypass_role_ids: set[int] | frozenset[int] = frozenset(),
) -> list[str]:
    """I requisiti che all'utente mancano, già scritti per il messaggio di rifiuto."""
    if user_role_ids & set(bypass_role_ids):
        return []
    mancanti = []
    if user_level < min_level:
        mancanti.append(f"livello {min_level}")
    if required_role_id is not None and required_role_id not in user_role_ids:
        mancanti.append(f"il ruolo <@&{required_role_id}>")
    if messages < min_messages:
        mancanti.append(f"{min_messages} messaggi (ne hai {messages})")
    return mancanti


def righe_requisiti(giveaway) -> list[str]:
    """Le righe dell'annuncio sui requisiti e sui biglietti (giveaway: oggetto con i campi dell'archivio)."""
    requisiti = []
    if giveaway.min_level > 0:
        requisiti.append(f"livello **{giveaway.min_level}**")
    if giveaway.required_role_id is not None:
        requisiti.append(f"ruolo <@&{giveaway.required_role_id}>")
    if giveaway.min_messages > 0:
        requisiti.append(f"**{giveaway.min_messages}** messaggi da quando parte")
    righe = []
    if requisiti:
        righe.append(f"Requisiti: {', '.join(requisiti)}")
    if giveaway.bypass_role_id is not None:
        righe.append(f"Salta i requisiti: <@&{giveaway.bypass_role_id}>")
    if giveaway.bonus_role_id is not None and giveaway.bonus_entries > 0:
        righe.append(
            f"<@&{giveaway.bonus_role_id}>: **{1 + giveaway.bonus_entries}** ingressi invece di 1"
        )
    return righe


def descrizione_giveaway(giveaway) -> str:
    """Il testo sotto il titolo dell'annuncio, uguale per il comando e per il worker."""
    testo = (
        f"Vincitori: **{giveaway.winners_count}**\n"
        f"Termina: <t:{int(giveaway.ends_at.timestamp())}:R>"
    )
    righe = righe_requisiti(giveaway)
    return testo + ("\n" + "\n".join(righe) if righe else "")


def titolo_giveaway(premio: str) -> str:
    """Il titolo dell'annuncio, entro i 256 caratteri di un titolo di embed."""
    return f"🎉 Giveaway: {premio}"[:256]
