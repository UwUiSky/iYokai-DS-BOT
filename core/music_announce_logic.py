"""
core/music_announce_logic.py
============================
Annuncio «ora in riproduzione» e copertina del brano: scelta dell'indirizzo
della copertina (solo https, corto), embed del brano, pausa tra due annunci.
Funzioni coperte: SPEC §9.x, catalogo MUS-057, MUS-058, MUS-060
Dipende da: niente di Discord a parte `discord.Embed`.
"""

from __future__ import annotations

import time

import discord

from core.music_logic import format_duration, truncate_title

MAX_LUNGHEZZA_COPERTINA = 300
PAUSA_ANNUNCI_SECONDI = 3.0  # al massimo un annuncio ogni 3 secondi per server


def copertina_sicura(url) -> str | None:
    """MUS-060: l'indirizzo della copertina se è https e corto; altrimenti None.

    Non lo scarichiamo noi: lo mostra Discord. Un indirizzo che non sia https
    (o con spazi) non entra nell'embed.
    """
    if not isinstance(url, str):
        return None
    testo = url.strip()
    if not testo.lower().startswith("https://") or len(testo) > MAX_LUNGHEZZA_COPERTINA:
        return None
    if any(c.isspace() or ord(c) < 32 for c in testo):
        return None
    return testo


def embed_brano(traccia, titolo_in_testa: str = "🎵") -> discord.Embed:
    """MUS-060: l'embed di un brano, con la copertina se c'è."""
    righe = []
    autore = getattr(traccia, "author", None)
    if autore:
        righe.append(truncate_title(str(autore), 100))
    if not getattr(traccia, "is_stream", False):
        righe.append(format_duration(getattr(traccia, "length", 0) or 0))
    embed = discord.Embed(
        title=truncate_title(f"{titolo_in_testa} {getattr(traccia, 'title', '')}"),
        description=" · ".join(righe) or None,
        color=discord.Color.blurple(),
    )
    copertina = copertina_sicura(getattr(traccia, "artwork", None))
    if copertina:
        embed.set_thumbnail(url=copertina)
    return embed


class PausaAnnunci:
    """Un annuncio ogni PAUSA_ANNUNCI_SECONDI per server; segna prima di ogni await (MUS-057)."""

    def __init__(self) -> None:
        self._ultimo: dict[int, float] = {}

    def puo_annunciare(self, guild_id: int, adesso: float | None = None) -> bool:
        adesso = time.monotonic() if adesso is None else adesso
        if adesso - self._ultimo.get(guild_id, -1e9) < PAUSA_ANNUNCI_SECONDI:
            return False
        self._ultimo[guild_id] = adesso
        return True
