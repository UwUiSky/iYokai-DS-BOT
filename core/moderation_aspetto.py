"""
core/moderation_aspetto.py
==========================
Colore e icona di ogni tipo di caso nel log di moderazione, scelti dal server (MOD-053). Una sola chiave di
impostazione (`mod_aspetto_casi`, dizionario tipo -> {colore, icona}); il tipo si riconosce dal titolo del riquadro
(«🔨 Ban», «⏳ Tempban»…). Cambia solo l'aspetto del riquadro nel log: niente cambia nelle sanzioni.
Funzioni coperte: MOD-053
"""

from __future__ import annotations

import re

import discord

SETTING_ASPETTO = "mod_aspetto_casi"
TIPI = ("warn", "timeout", "mute", "kick", "ban", "tempban", "softban", "isolamento", "quarantena")
_EMOJI_PERSONALIZZATA = re.compile(r"<a?:\w{2,32}:\d{15,25}>")


def icona_valida(icona) -> bool:
    return isinstance(icona, str) and bool(icona.strip()) and (
        len(icona.strip()) <= 8 or bool(_EMOJI_PERSONALIZZATA.fullmatch(icona.strip()))
    )


def pulita(valore) -> dict[str, dict]:
    """Le scelte del server senza i valori strani (tipi o colori fuori limite, icone troppo lunghe)."""
    if not isinstance(valore, dict):
        return {}
    risultato = {}
    for tipo, scelta in valore.items():
        if tipo not in TIPI or not isinstance(scelta, dict):
            continue
        voce = {}
        colore = scelta.get("colore")
        if isinstance(colore, int) and not isinstance(colore, bool) and 0 <= colore <= 0xFFFFFF:
            voce["colore"] = colore
        if icona_valida(scelta.get("icona")):
            voce["icona"] = scelta["icona"].strip()
        if voce:
            risultato[tipo] = voce
    return risultato


def tipo_da_titolo(titolo: str | None) -> str | None:
    """«🔨 Ban in massa» -> «ban»; «🔇 Mute (ruolo)» -> «mute». None se non è un tipo noto."""
    parole = re.sub(r"^[^\w]+", "", titolo or "").lower().split()
    return parole[0] if parole and parole[0] in TIPI else None


def applica(embed: discord.Embed, scelte: dict[str, dict]) -> discord.Embed:
    """Una copia del riquadro con il colore e l'icona scelti per il suo tipo (o lo stesso riquadro se non ci sono)."""
    tipo = tipo_da_titolo(embed.title)
    voce = scelte.get(tipo) if tipo else None
    if not voce:
        return embed
    copia = embed.copy()
    if "colore" in voce:
        copia.colour = discord.Colour(voce["colore"])
    if "icona" in voce and copia.title:
        resto = re.sub(r"^[^\w]+", "", copia.title)
        copia.title = f"{voce['icona']} {resto}"[:256]
    return copia
