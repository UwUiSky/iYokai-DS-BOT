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
import re

import discord

from core.i18n import t

MAX_PREMIO_GIVEAWAY = 200
MAX_INGRESSI_EXTRA = 20
MAX_MESSAGGI_RICHIESTI = 100_000
MAX_MODELLI_PER_SERVER = 25
PARTECIPANTI_PER_PAGINA = 20
MAX_RUOLI_ESCLUSI = 25
MAX_BOTTONE_TESTO = 80
MAX_MSG_CONFERMA = 500
MAX_MSG_DM = 1000
MAX_PIXEL_IMMAGINE = 16_000_000
MAX_BYTE_IMMAGINE = 8 * 1024 * 1024
COLORE_PREDEFINITO = 0x5865F2


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


def righe_requisiti(giveaway, lingua: str = "it") -> list[str]:
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
    escluso = getattr(giveaway, "ruolo_escluso", None)
    if escluso is not None:
        righe.append(t("giveaway_riga_escluso", lingua, ruolo=f"<@&{escluso}>"))
    premio = getattr(giveaway, "ruolo_premio", None)
    if premio is not None:
        righe.append(t("giveaway_riga_ruolo_premio", lingua, ruolo=f"<@&{premio}>"))
    return righe


def descrizione_giveaway(giveaway, lingua: str = "it") -> str:
    """Il testo sotto il titolo dell'annuncio, uguale per il comando e per il worker."""
    testo = (
        f"Vincitori: **{giveaway.winners_count}**\n"
        f"Termina: <t:{int(giveaway.ends_at.timestamp())}:R>"
    )
    righe = righe_requisiti(giveaway, lingua)
    return testo + ("\n" + "\n".join(righe) if righe else "")


def titolo_giveaway(premio: str) -> str:
    """Il titolo dell'annuncio, entro i 256 caratteri di un titolo di embed."""
    return f"🎉 Giveaway: {premio}"[:256]


def parse_colore(testo: str) -> int | None:
    """«#RRGGBB» (anche senza #) in numero; None se non è un colore."""
    m = re.fullmatch(r"#?([0-9A-Fa-f]{6})", (testo or "").strip())
    return int(m.group(1), 16) if m else None


def colore_annuncio(giveaway, opzioni) -> int:
    """Colore del giveaway, se no quello del server, se no il predefinito."""
    scelto = getattr(giveaway, "colore", None)
    if scelto is None:
        scelto = getattr(opzioni, "colore", None)
    return COLORE_PREDEFINITO if scelto is None else scelto


def embed_annuncio(giveaway, opzioni, lingua: str = "it") -> discord.Embed:
    """L'embed dell'annuncio, uguale per il comando, il worker e la modifica."""
    embed = discord.Embed(
        title=titolo_giveaway(giveaway.prize),
        description=descrizione_giveaway(giveaway, lingua),
        color=colore_annuncio(giveaway, opzioni),
    )
    if getattr(giveaway, "immagine_url", None):
        embed.set_image(url=giveaway.immagine_url)
    return embed


def ruoli_esclusi_di(giveaway, opzioni) -> set[int]:
    """Chi ha uno di questi ruoli non partecipa: quello del giveaway più quelli del server."""
    ruoli = set(getattr(opzioni, "ruoli_esclusi", ()) or ())
    if getattr(giveaway, "ruolo_escluso", None) is not None:
        ruoli.add(giveaway.ruolo_escluso)
    return ruoli


def riempi(testo: str, **valori: str) -> str:
    """Sostituisce {nome} nei testi scritti dall'admin. Segnaposto sconosciuti restano com'erano: niente format()."""
    for nome, valore in valori.items():
        testo = testo.replace("{" + nome + "}", str(valore))
    return testo


def pagine_partecipanti(totale: int, per_pagina: int = PARTECIPANTI_PER_PAGINA) -> int:
    return max(1, (totale + per_pagina - 1) // per_pagina)


def righe_partecipanti(ids: list[int], primo_numero: int = 1) -> str:
    return "\n".join(f"{n}. <@{uid}>" for n, uid in enumerate(ids, primo_numero))


def motivo_ruolo_non_assegnabile(
    *, posizione_ruolo: int, gestito: bool, di_base: bool, posizione_bot: int, bot_puo_gestire_ruoli: bool
) -> str | None:
    """Perché il bot non può dare il ruolo premio (chiave del catalogo), None se può."""
    if di_base or gestito:
        return "giveaway_ruolo_premio_non_valido"
    if not bot_puo_gestire_ruoli:
        return "giveaway_ruolo_premio_manca_permesso"
    if posizione_ruolo >= posizione_bot:
        return "giveaway_ruolo_premio_troppo_alto"
    return None


def motivo_immagine_non_valida(content_type: str | None, larghezza: int | None, altezza: int | None, byte: int) -> str | None:
    """Chiave del catalogo se l'allegato non va come immagine del giveaway, None se va."""
    if not (content_type or "").startswith("image/"):
        return "giveaway_immagine_non_valida"
    if byte > MAX_BYTE_IMMAGINE or (larghezza or 0) * (altezza or 0) > MAX_PIXEL_IMMAGINE:
        return "giveaway_immagine_troppo_grande"
    return None
