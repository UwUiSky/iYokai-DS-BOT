"""
core/strumenti_server_logic.py
==============================
Emoji e sticker aggiunti da un allegato o da un'emoji di un messaggio, thread e vocale: nomi validi, limiti di peso,
posti liberi per livello di boost, chi può entrare in un vocale. Nessun accesso alla rete.
Funzioni coperte: catalogo #128 UTL-209, 210, 211 (D69, B17)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_BYTE_EMOJI = 256 * 1024
MAX_BYTE_STICKER = 512 * 1024
_NOME_EMOJI = re.compile(r"^[A-Za-z0-9_]{2,32}$")
_EMOJI_PERSONALIZZATA = re.compile(r"<(a?):([A-Za-z0-9_]{2,32}):(\d{15,25})>")
TIPI_ESPRESSIONE = ("emoji", "sticker")
AZIONI_THREAD = ("crea", "archivia", "elimina")


@dataclass(frozen=True)
class EmojiTrovata:
    animata: bool
    nome: str
    id: int


def nome_emoji_valido(nome: str) -> bool:
    return bool(_NOME_EMOJI.match(nome))


def nome_sticker_valido(nome: str) -> bool:
    return 2 <= len(nome) <= 30


def trova_emoji(testo: str) -> EmojiTrovata | None:
    """La prima emoji personalizzata scritta nel testo."""
    trovata = _EMOJI_PERSONALIZZATA.search(testo or "")
    if trovata is None:
        return None
    return EmojiTrovata(trovata.group(1) == "a", trovata.group(2), int(trovata.group(3)))


def troppo_pesante(tipo: str, byte: int) -> bool:
    return byte > (MAX_BYTE_EMOJI if tipo == "emoji" else MAX_BYTE_STICKER)


def posti_emoji_liberi(guild, animata: bool) -> int:
    """Emoji ferme e animate hanno posti separati; il tetto dipende dal livello di boost."""
    usate = sum(1 for e in guild.emojis if e.animated == animata)
    return max(guild.emoji_limit - usate, 0)


def posti_sticker_liberi(guild) -> int:
    return max(guild.sticker_limit - len(guild.stickers), 0)


def puo_entrare_nel_vocale(permessi, canale) -> str | None:
    """None se può entrare; altrimenti la chiave del motivo. Il bot con `move_members` salta il limite di posti: lo si controlla qui."""
    if not (permessi.view_channel and permessi.connect):
        return "vai_vietato"
    limite = getattr(canale, "user_limit", 0) or 0
    if limite and len(canale.members) >= limite and not permessi.move_members:
        return "vai_pieno"
    return None
